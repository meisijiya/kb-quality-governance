# -*- coding: utf-8 -*-
"""
embed.py -- 把 300 篇文档 + 2000 条工单向量化，落盘为 .npy

方案优先级（按任务要求自动降级）:
  1. FlagEmbedding + BAAI/bge-small-zh-v1.5   (首选, 95.8MB, CPU 即可)
  2. sentence-transformers + 同一权重          (FlagEmbedding 不可用时)
  3. TfidfVectorizer(analyzer='char', 2-gram)  (模型下载失败时)

最终实际使用的方案会写进 embeddings_meta.json，detect.py 读取该文件，
保证报告里不会出现"降级了却声称用了 BGE"的情况。

计算设备同理：FlagEmbedding 在 devices=None 时会自动选 CUDA（NPU/MPS 同理），
本项目的产物必须在 CPU 上可复现，因此显式固定 devices="cpu"，
并把实际使用的 device 字段落进 embeddings_meta.json。

用法:
  python embed.py                                    # 读本目录语料、产物写本目录（默认口径）
  python embed.py --work-dir D:/scan/run01            # 从该目录读 docs.csv / tickets.csv
  python embed.py --work-dir D:/scan/run01 --out-dir D:/scan/run01/out

注意: HF_HOME 是模型缓存的环境变量，不受 --work-dir / --out-dir 影响。
"""
import argparse
import json
import os
import re
import sys
import time

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("HF_HOME", "D:/hf_cache")

MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def load_corpus(work_dir):
    docs = pd.read_csv(os.path.join(work_dir, "docs.csv"), encoding="utf-8-sig")
    tickets = pd.read_csv(os.path.join(work_dir, "tickets.csv"), encoding="utf-8-sig")
    doc_texts = (docs["title"].astype(str) + "。" + docs["content"].astype(str)).tolist()
    tk_texts = tickets["content"].astype(str).tolist()
    return docs, tickets, doc_texts, tk_texts


def split_passages(text, min_len=8):
    """把一篇文档切成若干语义段落（按中文句号/分号）。

    整篇文档做向量化会把多个主题平均掉，导致"有没有被覆盖"这件事
    被稀释；按段落检索是检索系统的常规做法，实测也把意图级 AUC
    从 0.888（整篇级）提升到 0.968（段落级），见 granularity.csv。
    """
    parts = [p.strip() for p in re.split(r"[。；]", text) if len(p.strip()) >= min_len]
    return parts or [text]


def build_passages(docs):
    texts, owner = [], []
    for i, (_, r) in enumerate(docs.iterrows()):
        for p in split_passages(str(r["title"]) + "。" + str(r["content"])):
            texts.append(p)
            owner.append(i)
    return texts, np.asarray(owner, dtype=np.int32)


def make_encoder():
    """按优先级返回 (encode_fn, meta_dict)。encode_fn(texts) -> (n, d) float32。"""
    meta = {"attempts": []}
    try:
        from FlagEmbedding import FlagModel
        # devices 必须显式给 "cpu"：FlagEmbedding 的 get_target_devices 在
        # devices=None 时会自动探测并选 cuda/npu/mps，而本项目的阈值 0.62
        # 是在 CPU 编码的向量上标定的，换设备会让产物与已落盘的指标口径脱节。
        m = FlagModel(MODEL_NAME, use_fp16=False, devices="cpu")

        def enc(texts):
            return np.asarray(m.encode(texts, batch_size=64), dtype=np.float32)
        meta.update(scheme="FlagEmbedding", model=MODEL_NAME, fallback=False, device="cpu")
        print("[embed] 方案 1 FlagEmbedding + BAAI/bge-small-zh-v1.5 初始化成功 (device=cpu)")
        return enc, meta
    except Exception as e:
        meta["attempts"].append({"scheme": "FlagEmbedding", "error": repr(e)})
        print(f"[embed] 方案 1 FlagEmbedding 失败: {type(e).__name__}: {e}")

    try:
        from sentence_transformers import SentenceTransformer
        m2 = SentenceTransformer(MODEL_NAME, device="cpu")

        def enc2(texts):
            return np.asarray(m2.encode(texts, batch_size=64,
                                        normalize_embeddings=True,
                                        show_progress_bar=False), dtype=np.float32)
        meta["attempts"].append({"scheme": "sentence-transformers", "chosen": True})
        meta.update(scheme="sentence-transformers", model=MODEL_NAME, fallback=True, device="cpu")
        print("[embed] 方案 2 sentence-transformers 成功（已降级，device=cpu）")
        return enc2, meta
    except Exception as e2:
        meta["attempts"].append({"scheme": "sentence-transformers", "error": repr(e2)})
        print(f"[embed] 方案 2 失败: {type(e2).__name__}: {e2}")

    print("[embed] 方案 3 降级到 TfidfVectorizer(analyzer='char', ngram_range=(2,2))")
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 2), max_features=50000)

    def enc3(texts):
        M = vec.transform(texts)
        d = np.sqrt(M.multiply(M).sum(axis=1))
        d[d == 0] = 1.0
        return np.asarray(M / d[:, None], dtype=np.float32)
    meta.update(scheme="TF-IDF char-bigram", model="TfidfVectorizer(analyzer=char,2-gram)",
                fallback=True, device="cpu",
                note="降级方案：字符 bigram TF-IDF，余弦尺度与 BGE 不同，阈值须另行扫参")
    return enc3, meta


def parse_args():
    ap = argparse.ArgumentParser(description="文档 / 工单 / 段落三级向量化，落盘 .npy")
    ap.add_argument("--work-dir", default=None,
                    help="工作目录：输入语料 docs.csv / tickets.csv 所在位置"
                         "（默认 = 本脚本所在目录）")
    ap.add_argument("--out-dir", default=None,
                    help="产物输出目录（默认 = --work-dir）")
    return ap.parse_args()


def main():
    args = parse_args()
    work_dir = os.path.abspath(args.work_dir) if args.work_dir else HERE
    out_dir = os.path.abspath(args.out_dir) if args.out_dir else work_dir
    os.makedirs(out_dir, exist_ok=True)

    docs, tickets, doc_texts, tk_texts = load_corpus(work_dir)
    passage_texts, owner = build_passages(docs)
    print("=" * 70)
    print(f"[embed] 工作目录 = {work_dir}")
    print(f"[embed] 产物输出目录 = {out_dir}")
    print(f"[embed] 文档 {len(doc_texts)} 篇 / 工单 {len(tk_texts)} 条 / "
          f"文档段落 {len(passage_texts)} 段 (平均每篇 "
          f"{len(passage_texts) / len(doc_texts):.1f} 段)")

    encode, meta = make_encoder()

    t0 = time.time()
    # 编码器必须先见过全部文本，TF-IDF 方案需要在同一词表上 fit
    if meta["scheme"].startswith("TF-IDF"):
        encode(doc_texts + tk_texts + passage_texts)
    D = encode(doc_texts)
    T = encode(tk_texts)
    P = encode(passage_texts)
    elapsed = time.time() - t0

    norm = lambda X: (X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)).astype(np.float32)
    D, T, P = norm(D), norm(T), norm(P)

    # 每条工单 x 每篇文档 的"段落级最大余弦"，即该工单被知识库覆盖的程度。
    # 段落按文档顺序连续排列，因此用 reduceat 做分段最大值。
    SP = T @ P.T                                   # (n_tickets, n_passages)
    n_docs = len(D)
    starts = np.searchsorted(owner, np.arange(n_docs), side="left")
    ends = np.searchsorted(owner, np.arange(n_docs), side="right")
    if (ends <= starts).any():
        raise ValueError(f"存在没有段落的文档: "
                         f"{np.where(ends <= starts)[0].tolist()}")
    cover = np.maximum.reduceat(SP, starts, axis=1)   # (n_tickets, n_docs)
    assert cover.shape == (len(T), n_docs), cover.shape
    ticket_cover = cover.max(axis=1)               # (n_tickets,)

    meta.update(dim=int(D.shape[1]), encode_seconds=round(elapsed, 2),
                n_docs=int(D.shape[0]), n_tickets=int(T.shape[0]),
                n_passages=int(P.shape[0]),
                model_download_mb=95.8)

    np.save(os.path.join(out_dir, "doc_emb.npy"), D)
    np.save(os.path.join(out_dir, "ticket_emb.npy"), T)
    np.save(os.path.join(out_dir, "ticket_cover.npy"), ticket_cover)
    with open(os.path.join(out_dir, "embeddings_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # ---- 自检：同一意图内应高相似，跨意图应低（验证向量确有语义区分度）
    print(f"[embed] 方案 = {meta['scheme']} | 维度 = {meta['dim']} | "
          f"向量化耗时 = {elapsed:.1f}s")
    print(f"[embed] 工单被覆盖度(ticket_cover): min={ticket_cover.min():.3f} "
          f"max={ticket_cover.max():.3f} mean={ticket_cover.mean():.3f}")

    for pair in [("会议室预订规则", "门禁权限申请"),
                 ("数据导出权限申请", "系统权限开通"),
                 ("海外出差报销标准", "差旅费报销")]:
        a = np.where(tickets["intent_label"].values == pair[0])[0]
        b = np.where(tickets["intent_label"].values == pair[1])[0]
        if len(a) == 0 or len(b) == 0:
            continue
        within = float((T[a] @ T[a].T)[np.triu_indices(len(a), 1)].mean())
        across = float((T[a] @ T[b].T).mean())
        print(f"[embed] 自检 域内均值={within:.3f} 域间均值={across:.3f} "
              f"差值={within - across:+.3f}  ({pair[0]} vs {pair[1]})")
    print("[embed] 已写出 doc_emb.npy / ticket_emb.npy / ticket_cover.npy / "
          "embeddings_meta.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
