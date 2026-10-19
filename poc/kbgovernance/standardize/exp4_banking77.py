# -*- coding: utf-8 -*-
"""
exp4_banking77.py -- 实验 4：在真实英文语料 banking77 上验证 S1-S4。

数据源: PolyAI/banking77, CC-BY-4.0。
  HF 上的 PolyAI/banking77 只有 banking77.py 脚本，datasets 3.x 已不支持脚本式加载
  （实测报错: "Dataset scripts are no longer supported, but found banking77.py"），
  因此按脚本内 _TRAIN_DOWNLOAD_URL 指向的官方仓库直接下 CSV。
  https://github.com/PolyAI-LDN/task-specific-datasets  train.csv 10017 / test.csv 3085

知识库构造（模拟「企业知识库 + 客服工单」）：
  - 把 77 个意图中的一部分当作「已被知识库覆盖的意图」，其 query 文本即知识库文档；
  - 另一部分意图的 query 文本当工单，知识库里完全没有对应文档 -> 真缺口。
  - 与原型同构：先按意图切成 cluster，再算簇内覆盖度中位数。
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("HF_HOME", "D:/hf_cache")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from standardize import (auc, best_f1_threshold, get_encoder, group_zscore,  # noqa: E402
                         group_pct, pct_rank, thr_for_recall_k, zscore)

MODEL = os.environ.get("BK_MODEL", "BAAI/bge-small-en-v1.5")
TAG = os.environ.get("BK_TAG", MODEL.split("/")[-1])
SEED = 42


def load_banking():
    tr = pd.read_csv(os.path.join(HERE, "data", "banking77_train.csv"), encoding="utf-8")
    te = pd.read_csv(os.path.join(HERE, "data", "banking77_test.csv"), encoding="utf-8")
    print(f"[exp4] banking77 原始: train {len(tr)} / test {len(te)}, "
          f"意图 {tr['category'].nunique()} 个")
    return tr, te


def build_kb_and_tickets(tr, te, n_gap_intents=15, docs_per_intent=6, tk_per_intent=40):
    """把 77 意图拆成「已覆盖」与「缺口」两类，构造知识库与工单。

    知识库 = 已覆盖意图的 query 文本（每意图取 docs_per_intent 条）
    工单   = 所有 77 个意图的 query 文本（每意图取 tk_per_intent 条，test 集优先）
    ground truth = 被分到「缺口」那一侧的意图
    """
    intents = sorted(tr["category"].unique())
    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(intents))
    gap_ids = [intents[i] for i in order[:n_gap_intents]]
    cov_ids = [intents[i] for i in order[n_gap_intents:]]

    kb_texts, kb_src = [], []
    for it in cov_ids:
        pool = tr[tr["category"] == it]["text"].tolist()
        take = rng.choice(len(pool), min(docs_per_intent, len(pool)), replace=False)
        for j in take:
            kb_texts.append(pool[j])
            kb_src.append(it)

    tk_texts, tk_lab = [], []
    for it in intents:
        pool = te[te["category"] == it]["text"].tolist()
        if len(pool) < tk_per_intent:
            pool = pool + tr[tr["category"] == it]["text"].tolist()
        take = rng.choice(len(pool), min(tk_per_intent, len(pool)), replace=False)
        for j in take:
            tk_texts.append(pool[j])
            tk_lab.append(it)
    return kb_texts, np.array(kb_src), tk_texts, np.array(tk_lab), set(gap_ids), cov_ids


def cover_scores(kb_texts, tk_texts):
    """知识库段落级最大余弦覆盖度（英文用空格分句）。"""
    import re
    t0 = time.time()
    enc = get_encoder(MODEL)
    kb_parts, owner = [], []
    for j, t in enumerate(kb_texts):
        parts = [p.strip() for p in re.split(r"[.;?!]", t) if len(p.strip()) >= 8]
        for p in (parts or [t]):
            kb_parts.append(p)
            owner.append(j)
    P = np.asarray(enc.encode(kb_parts, batch_size=64), dtype=np.float32)
    T = np.asarray(enc.encode(tk_texts, batch_size=64), dtype=np.float32)
    P /= (np.linalg.norm(P, axis=1, keepdims=True) + 1e-12)
    T /= (np.linalg.norm(T, axis=1, keepdims=True) + 1e-12)
    SP = T @ P.T
    n = len(kb_texts)
    starts = np.searchsorted(owner, np.arange(n), side="left")
    ends = np.searchsorted(owner, np.arange(n), side="right")
    if (ends <= starts).any():
        raise ValueError(f"空文档: {np.where(ends <= starts)[0].tolist()}")
    cover = np.maximum.reduceat(SP, starts, axis=1).max(axis=1).astype(np.float64)
    print(f"[exp4] 知识库 {len(kb_texts)} 篇 / 段落 {len(kb_parts)} / "
          f"工单 {len(tk_texts)} 条, 编码+覆盖度 {round(time.time()-t0,1)}s")
    return cover


def intent_auc(score, labels, gap):
    df = pd.DataFrame({"i": labels, "s": score})
    med = df.groupby("i")["s"].median()
    return auc([v for k, v in med.items() if k in gap],
               [v for k, v in med.items() if k not in gap]), med


def main():
    tr, te = load_banking()
    kb_texts, kb_src, tk_texts, tk_lab, gap, cov_ids = build_kb_and_tickets(tr, te)
    print(f"[exp4] 知识库 {len(kb_texts)} 篇 (覆盖 {len(cov_ids)} 意图) / "
          f"工单 {len(tk_texts)} 条 ({len(set(tk_lab))} 意图) / "
          f"ground truth 缺口意图 {len(gap)} 个")
    print(f"[exp4] 缺口意图 = {sorted(gap)}")

    cover = cover_scores(kb_texts, tk_texts)
    print(f"[exp4] cover: min={cover.min():.4f} mean={cover.mean():.4f} "
          f"max={cover.max():.4f} sd={cover.std(ddof=1):.4f}")

    # 意图 -> 业务域（banking77 无域字段，用覆盖意图的相似度结构聚成 4 个粗域）
    enc = get_encoder(MODEL)
    kb_src_uni = sorted(set(cov_ids))
    kv = np.asarray(enc.encode([max(tr[tr["category"] == i]["text"].tolist(),
                                    key=len) for i in kb_src_uni], batch_size=64),
                    dtype=np.float32)
    kv /= (np.linalg.norm(kv, axis=1, keepdims=True) + 1e-12)
    sim = kv @ kv.T
    dom_of = {}
    order = np.argsort(-sim.sum(axis=1))
    for rank, idx in enumerate(order):
        dom_of[kb_src_uni[idx]] = f"D{rank % 4}"
    dom = np.array([dom_of.get(i, "G") for i in tk_lab])

    zg = zscore(cover)[0]
    zw = group_zscore(cover, dom)
    SC = {
        "ABS(绝对阈值)": -cover,
        "S1 分位数排名": 1.0 - pct_rank(cover)[0],
        "S2 全局z-score": -zg,
        "S3 领域内z": -zw,
        "S3b 域内分位数": -group_pct(cover, dom),
        "S4 双参考系(域)": -np.maximum(zg, zw),
        "S4min 双参考系min": -np.minimum(zg, zw),
        "S5 双参考系均值": -(zg + zw) / 2.0,
    }
    rows = []
    print("\n[exp4] banking77 意图级指标：")
    for name, s in SC.items():
        a, _ = intent_auc(s, tk_lab, gap)
        f1, p, r, thr = best_f1_threshold(s, tk_lab, gap)
        tr_all = thr_for_recall_k(s, tk_lab, gap)
        rows.append(dict(方法=name, AUC=round(a, 4), best_F1=round(f1, 4),
                         P=round(p, 4), R=round(r, 4), 最优阈值=round(thr, 4),
                         召回全部门槛=round(tr_all, 4) if tr_all is not None else None))
        print(f"  {name:18s} AUC={a:.4f} F1={f1:.4f} P={p:.3f} R={r:.3f} thr={thr:+.4f}")
    df = pd.DataFrame(rows)
    _, med_all = intent_auc(-cover, tk_lab, gap)

    # ---- banking77 内部的「换语料」迁移：train 调阈值 -> test 语料调阈值
    #     做法：把 test 集作为第二个场景重算 cover，看阈值漂移
    print("\n[exp4] banking77 子场景迁移（知识库减半 / 只留 20 意图）：")
    rng = np.random.default_rng(SEED)
    sub_scen = []
    for tag, n_keep in [("KB减半", len(cov_ids) // 2), ("KB仅20意图", 20)]:
        keep_ids = set(sorted(cov_ids)[:n_keep])
        idx = np.array([i for i, s in enumerate(kb_src) if s in keep_ids])
        if len(idx) == 0:
            continue
        kb2 = [kb_texts[i] for i in idx]
        c2 = cover_scores(kb2, tk_texts)
        # 该场景下的 ground truth：知识库里没有文档的意图（含原有缺口意图）
        alive = set(kb_src[idx])
        gap2 = {i for i in set(tk_lab) if i not in alive}
        zg2, zw2 = zscore(c2)[0], group_zscore(c2, dom)
        sc2 = {"ABS(绝对阈值)": -c2, "S1 分位数排名": 1.0 - pct_rank(c2)[0],
               "S2 全局z-score": -zg2, "S3 领域内z": -zw2,
               "S3b 域内分位数": -group_pct(c2, dom),
               "S4 双参考系(域)": -np.maximum(zg2, zw2),
               "S4min 双参考系min": -np.minimum(zg2, zw2),
               "S5 双参考系均值": -(zg2 + zw2) / 2.0}
        base_a = {r["方法"]: r["AUC"] for r in rows}
        for nm, s in sc2.items():
            a, _ = intent_auc(s, tk_lab, gap2)
            f1, p, r, thr = best_f1_threshold(s, tk_lab, gap2)
            sub_scen.append(dict(子场景=tag, 知识库文档=len(kb2),
                                 ground_truth缺口意图=len(gap2), 方法=nm,
                                 AUC=round(a, 4), F1=round(f1, 4),
                                 最优阈值=round(thr, 4),
                                 AUC衰减=round(a - base_a[nm], 4)))
        print(f"  [{tag}] KB {len(kb2)} 篇, 新 ground truth {len(gap2)} 个缺口意图")

    # ---- 跨语料迁移（核心）：把中文合成语料上定出的阈值原封不动搬到英文真实语料
    print("\n[exp4] 跨语料阈值迁移（源=中文合成语料 alpha，abs 阈值 0.6463）：")
    print("      银行库 cover 分布 min=%.4f mean=%.4f max=%.4f，"
          "中文语料最优阈值 0.6463 落在银行库分布的哪个位置？" %
          (cover.min(), cover.mean(), cover.max()))
    xfer = []
    for src_name, src_thr in [("中文alpha ABS(cover<thr)", 0.6463),
                              ("中文alpha ABS(cover>thr, 反向)", 0.6463)]:
        # cover > 0.6463 判为「已覆盖」，反之判为缺口
        det = {k for k, v in med_all.items() if v <= 0.6463}
        tp = len(det & gap)
        p = tp / len(det) if det else 0
        r = tp / len(gap)
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0
        xfer.append(dict(源="中文合成语料 alpha", 源阈值=0.6463, 目标="banking77 英文",
                         判定="cover <= 0.6463 -> 缺口", 检出意图数=len(det),
                         P=round(p, 4), R=round(r, 4), F1=round(f, 4),
                         该场景最优F1=round(df[df.方法 == "ABS(绝对阈值)"]["best_F1"].iloc[0], 4)))
        print(f"  中文阈值 0.6463 -> 英文: 检出 {len(det)} 个意图, "
              f"P={p:.3f} R={r:.3f} F1={f:.3f}  (该场景最优 F1="
              f"{df[df['方法'] == 'ABS(绝对阈值)']['best_F1'].iloc[0]:.3f})")
    # 同一方向下，各标准化方法自己的最优阈值搬过来会怎样
    for nm in ["S1 分位数排名", "S2 全局z-score", "S4 双参考系(域)"]:
        a_row = df[df.方法 == nm]
        if len(a_row) == 0:
            continue
        s = SC[nm]
        thr = float(a_row["最优阈值"].iloc[0])
        _, medx = intent_auc(s, tk_lab, gap)
        det = {k for k, v in medx.items() if v >= thr}
        tp = len(det & gap)
        p = tp / len(det) if det else 0
        r = tp / len(gap)
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0
        xfer.append(dict(源="banking77 全量自身", 源阈值=round(thr, 4),
                         目标="banking77 KB减半", 判定=f"{nm} score>={thr:.4f}->缺口",
                         检出意图数=len(det), P=round(p, 4), R=round(r, 4),
                         F1=round(f, 4), 该场景最优F1=None))
        print(f"  {nm} 全量阈值 {thr:+.4f} -> KB减半: 检出 {len(det)}, F1={f:.3f}")
    pd.DataFrame(xfer).to_csv(os.path.join(HERE, f"results_xfer_banking77_{TAG}.csv"),
                              index=False, encoding="utf-8-sig")

    out = pd.concat([df.assign(子场景="全量"), pd.DataFrame(sub_scen)], ignore_index=True)
    cols = ["子场景", "知识库文档", "ground_truth缺口意图", "方法", "AUC", "F1",
            "P", "R", "最优阈值", "召回全部门槛", "AUC衰减"]
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    out = out[cols]
    out.to_csv(os.path.join(HERE, f"results_banking77_{TAG}.csv"), index=False,
               encoding="utf-8-sig")
    json.dump(dict(model=MODEL, n_kb=len(kb_texts), n_tk=len(tk_texts),
                   n_gap_intents=len(gap),
                   cover=dict(min=round(float(cover.min()), 4),
                              mean=round(float(cover.mean()), 4),
                              max=round(float(cover.max()), 4),
                              sd=round(float(cover.std(ddof=1)), 4))),
              open(os.path.join(HERE, f"banking77_meta_{TAG}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n[exp4] 完成 -> results_banking77_{TAG}.csv")


if __name__ == "__main__":
    main()