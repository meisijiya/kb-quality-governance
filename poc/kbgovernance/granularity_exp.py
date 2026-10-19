# -*- coding: utf-8 -*-
"""
granularity_exp.py -- 「检索粒度」与「打分方案」对照实验（可复算版）

回答两个问题:
  Q1 整篇文档级检索 vs 段落级检索, 对「意图可分性」(能否把缺口意图与已覆盖意图分开)差多少?
  Q2 在同一粒度下, max-cosine / max-top5均值 / max÷std / max÷top5均值 / max-min
     这几种打分方案各自的可分性是多少?

口径说明（全部与仓库既有产物一致, 不做任何为了对数的调参）:
  * 段落切分与向量化直接复用 embed.py 的 build_passages() + make_encoder(),
    模型 BAAI/bge-small-zh-v1.5 (HF_HOME=D:/hf_cache 已缓存), 与 embed.py 落盘的
    ticket_cover.npy 同口径; 脚本会把重算的 cover 与 ticket_cover.npy 逐元素对比。
  * 缺口方向统一为「分数越高越像缺口」: 所有方案取负号, 因为 cover 越大越说明
    该意图被知识库覆盖, 越不像缺口。
  * 两种 AUC 都算:
      auc               工单级 AUC, sklearn.metrics.roc_auc_score(y∈{0,1}, score)
                        —— 任务书要求的「用 sklearn 计算」
      auc_intent_median 意图级 AUC, 先按 intent_label 取中位数再算 (Mann-Whitney)
                        —— 与 standardize/results_auc.csv 的 0.968 同口径, 用于交叉校验
  * top5 均值 / std 都在「该粒度下每条工单的全部候选相似度」上统计:
      整篇级 -> 300 个文档相似度; 段落级 -> 1852 个段落相似度
    std 用总体标准差 (ddof=0)。

产出:
  granularity.csv       粒度 x 打分方案 的 AUC 对照表
  granularity_dup.csv   两种粒度下真实重复组的组内最大相似度均值(0.982-0.985 的来源)

运行: python granularity_exp.py   (无随机性, 重复运行结果完全一致)
"""
import csv
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embed import build_passages, make_encoder  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))

TOPK = 5                     # 「top5 均值」里的 k
EPS = 1e-12
EPSD = 1e-9                  # 除法保护

# 打分方案: name -> 说明. 统一在取负号前定义(值越大 = 越像被覆盖)
SCORE_SCHEMES = [
    ("max-cosine", "max: 到该粒度下所有候选的最大余弦(基准)"),
    ("max-top5mean", "max - top5 均值(margin)"),
    ("max/std", "max ÷ 全体候选相似度的总体标准差"),
    ("max/top5mean", "max ÷ top5 均值"),
    ("max-min", "max - min(极差, span)"),
]

# RESULT.md 散文里记录、但此前没有任何机读产物支撑的数字（用于事后比对, 不参与计算）
RESULT_MD_REFERENCE = {
    "doc_level|max-cosine": 0.936,
    "passage_level|max-cosine": 0.968,
    "passage_level|max-top5mean": 0.512,
    "passage_level|max/std": 0.448,
    "passage_level|max/top5mean": 0.384,
}
DUP_REFERENCE = (0.982, 0.985)   # RESULT.md §5.3 写的重复组内相似度区间


# ============================================================ 工具
def l2norm(X):
    return (X / (np.linalg.norm(X, axis=1, keepdims=True) + EPS)).astype(np.float32)


def scheme_values(S):
    """S: (n_tickets, n_candidates) 相似度矩阵 -> {方案名: (n_tickets,) 取负号后的分数}。"""
    part = np.sort(S, axis=1)[:, ::-1]
    smax = part[:, 0]
    stop5 = part[:, :TOPK].mean(axis=1)
    sstd = S.std(axis=1, ddof=0)
    smin = part[:, -1]
    raw = {
        "max-cosine": smax,
        "max-top5mean": smax - stop5,
        "max/std": smax / (sstd + EPSD),
        "max/top5mean": smax / (stop5 + EPSD),
        "max-min": smax - smin,
    }
    return {k: -raw[k] for k, _ in SCORE_SCHEMES}, raw


def auc_ticket(y, s):
    return float(roc_auc_score(y, s))


def auc_intent(labels, s, gap_intents):
    med = pd.Series(np.asarray(s, float)).groupby(np.asarray(labels)).median()
    pos = [v for k, v in med.items() if k in gap_intents]
    neg = [v for k, v in med.items() if k not in gap_intents]
    if not pos or not neg:
        return float("nan")
    return float(roc_auc_score([1] * len(pos) + [0] * len(neg), pos + neg))


def doc_doc_maxcos(P, owner, n_docs):
    """段落级 -> 文档 x 文档相似度: 每对文档取其段落两两余弦的最大值。"""
    PP = P @ P.T                                   # (n_passages, n_passages)
    rowmax = np.maximum.reduceat(PP, owner, axis=1)  # (n_docs, n_passages)
    return np.maximum.reduceat(rowmax, owner, axis=0)  # (n_docs, n_docs)


def group_max_sim(Sim, groups, doc_index):
    out = []
    for g in groups:
        idx = [doc_index[d] for d in g if d in doc_index]
        if len(idx) < 2:
            continue
        sub = Sim[np.ix_(idx, idx)]
        off = sub[~np.eye(len(idx), dtype=bool)]
        out.append(float(off.max()))
    return np.asarray(out)


# ============================================================ main
def main():
    t0 = time.time()
    docs = pd.read_csv(os.path.join(HERE, "docs.csv"), encoding="utf-8-sig")
    tickets = pd.read_csv(os.path.join(HERE, "tickets.csv"), encoding="utf-8-sig")
    D = np.load(os.path.join(HERE, "doc_emb.npy"))
    T = np.load(os.path.join(HERE, "ticket_emb.npy"))
    cover_disk = np.load(os.path.join(HERE, "ticket_cover.npy"))
    emeta = json.load(open(os.path.join(HERE, "embeddings_meta.json"),
                           encoding="utf-8"))
    gt = json.load(open(os.path.join(HERE, "ground_truth.json"), encoding="utf-8"))
    doc_ids = docs["doc_id"].tolist()
    doc_index = {d: i for i, d in enumerate(doc_ids)}
    gap_intents = set(gt["gap_intents"])
    labels = tickets["intent_label"].astype(str).values
    y = np.asarray([1 if l in gap_intents else 0 for l in labels], dtype=int)

    print("=" * 74)
    print("[gran] 输入: 文档 %d / 工单 %d / embedding=%s(%s) dim=%d"
          % (D.shape[0], T.shape[0], emeta["scheme"], emeta["model"], D.shape[1]))
    print("[gran] 缺口意图 %d 个, 对应工单 %d 条 (占 %.2f%%)"
          % (len(gap_intents), int(y.sum()), 100.0 * y.mean()))

    # ---------------- 段落向量: embed.py 未单独落盘, 按同一策略重算 ----------------
    print("\n" + "-" * 74)
    print("[gran] 检查段落向量是否已落盘: doc_emb.npy 形状 =", D.shape,
          "-> doc_emb.npy 是整篇级向量, embeddings_meta.json 里也没有 passage 向量文件")
    passage_texts, owner = build_passages(docs)
    print("[gran] 按 embed.py 的切分策略切出 %d 段 (每篇 %.1f 段), 重新向量化..."
          % (len(passage_texts), len(passage_texts) / len(docs)))
    t1 = time.time()
    encode, meta = make_encoder()
    P = l2norm(encode(passage_texts))
    print("[gran] 段落向量化完成, 形状 %s, 耗时 %.1fs (embed.py 记录 n_passages=%d)"
          % (P.shape, time.time() - t1, meta.get("n_passages", -1)))

    # 与 embed.py 落盘的 ticket_cover.npy 逐元素对照, 确认口径一致
    n_docs = len(D)
    starts = np.searchsorted(owner, np.arange(n_docs), side="left")
    ends = np.searchsorted(owner, np.arange(n_docs), side="right")
    cover_docs = np.maximum.reduceat(T @ P.T, starts, axis=1)     # (n_tickets, n_docs)
    cover_re = cover_docs.max(axis=1)
    diff = float(np.abs(cover_re - cover_disk).max())
    print("[gran] 交叉校验: 重算 ticket_cover 与 ticket_cover.npy 最大逐元素差 = %.2e"
          % diff)
    print("[gran] 段落数一致性: 本脚本 %d vs embeddings_meta.json %d"
          % (len(passage_texts), emeta["n_passages"]))

    # ---------------- 两种粒度的相似度矩阵 ----------------
    gran_sim = {"doc_level": T @ D.T, "passage_level": T @ P.T}
    for k, v in gran_sim.items():
        print("[gran] %-13s 相似度矩阵 %s" % (k, v.shape))

    # ---------------- AUC 对照 ----------------
    print("\n" + "-" * 74)
    print("[gran] 打分方案 x 检索粒度 -> AUC (分数已取负, 越大越像缺口)")
    print("%-13s %-14s %9s %9s   %s"
          % ("granularity", "score_scheme", "auc(工单)", "auc(意图)", "说明"))
    rows = []
    for gname in ("doc_level", "passage_level"):
        scores, _ = scheme_values(gran_sim[gname])
        for sname, desc in SCORE_SCHEMES:
            s = scores[sname]
            a_t = auc_ticket(y, s)
            a_i = auc_intent(labels, s, gap_intents)
            rows.append({"granularity": gname, "score_scheme": sname,
                         "auc": round(a_t, 4),
                         "auc_intent_median": round(a_i, 4),
                         "n_tickets": int(len(labels)),
                         "n_labeled": int(y.sum()),
                         "description": desc})
            print("%-13s %-14s %9.4f %9.4f   %s" % (gname, sname, a_t, a_i, desc))

    out = os.path.join(HERE, "granularity.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["granularity", "score_scheme", "auc",
                                          "auc_intent_median", "n_tickets",
                                          "n_labeled", "description"])
        w.writeheader()
        w.writerows(rows)
    print("\n[gran] 已写出 granularity.csv (%d 行)" % len(rows))

    # 与 standardize/results_auc.csv 的 alpha 场景基线交叉校验
    std_path = os.path.join(HERE, "standardize", "results_auc.csv")
    if os.path.exists(std_path):
        st = pd.read_csv(std_path, encoding="utf-8-sig")
        base = st[(st["场景"] == "alpha") & (st["方法"].str.startswith("ABS"))]
        if len(base):
            print("[gran] 交叉校验: standardize/results_auc.csv alpha ABS 意图级 AUC = %.4f"
                  % float(base["AUC"].iloc[0]))

    # ---------------- 重复组内相似度 (0.982-0.985 的来源) ----------------
    print("\n" + "-" * 74)
    print("[gran] 真实重复组 (%d 组) 组内成员两两最大相似度:" % len(gt["dup_groups"]))
    doc_sim = {
        "doc_level": D @ D.T,
        "passage_level": doc_doc_maxcos(P, owner, n_docs),
    }
    dup_rows = []
    for gname, Sim in doc_sim.items():
        gs = group_max_sim(Sim, gt["dup_groups"], doc_index)
        dup_rows.append({"granularity": gname, "score_scheme": "pairwise-max-cosine",
                         "n_groups": int(len(gs)),
                         "mean_max_sim": round(float(gs.mean()), 4),
                         "min_max_sim": round(float(gs.min()), 4),
                         "max_max_sim": round(float(gs.max()), 4)})
        print("[gran] %-13s mean=%.4f  min=%.4f  max=%.4f  (n=%d)"
              % (gname, gs.mean(), gs.min(), gs.max(), len(gs)))
        if gname == "doc_level":
            print("[gran]   逐组 max_sim（22 组, 便于核对 RESULT.md §5.3 只列了前 3 组）:")
            print("[gran]   " + " ".join("%.4f" % v for v in gs))
    out2 = os.path.join(HERE, "granularity_dup.csv")
    with open(out2, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["granularity", "score_scheme", "n_groups",
                                          "mean_max_sim", "min_max_sim",
                                          "max_max_sim"])
        w.writeheader()
        w.writerows(dup_rows)
    print("[gran] 已写出 granularity_dup.csv")

    # ---------------- 与 RESULT.md 散文数字的对账(只报告, 不调参) ----------------
    print("\n" + "=" * 74)
    print("[gran] === 与 RESULT.md 散文数字对账(实算值原样输出, 绝不反向调参)===")
    got = {(r["granularity"], r["score_scheme"]): r for r in rows}
    mism = 0
    for key, ref in RESULT_MD_REFERENCE.items():
        gn, sn = key.split("|")
        r = got.get((gn, sn))
        if r is None:
            print("[gran] 对账跳过: %s 未在结果中找到" % key)
            continue
        real = r["auc_intent_median"]
        flag = "一致" if abs(real - ref) < 5e-3 else "MISMATCH"
        if flag == "MISMATCH":
            mism += 1
            print("MISMATCH vs RESULT.md: %s | %s 实算 AUC(意图级) %.4f vs 文档 %.4f "
                  "(差 %+.4f)" % (gn, sn, real, ref, real - ref))
        else:
            print("[gran] 一致: %s | %s 实算 %.4f vs 文档 %.4f" % (gn, sn, real, ref))
        print("           (工单级 AUC = %.4f, 意图级 AUC = %.4f)"
              % (r["auc"], r["auc_intent_median"]))
    lo, hi = DUP_REFERENCE
    ms = dup_rows[0]["mean_max_sim"]
    if not (lo - 5e-4 <= ms <= hi + 5e-4):
        mism += 1
        print("MISMATCH vs RESULT.md: 重复组内相似度 实算 %.4f vs 文档 %.3f-%.3f "
              "(差 %+.4f)" % (ms, lo, hi, ms - lo))
    else:
        print("[gran] 一致: 重复组内相似度 实算 %.4f vs 文档 %.3f-%.3f" % (ms, lo, hi))
    print("[gran] 对账结论: %d 项与 RESULT.md 不一致(上面已逐项列出)" % mism)
    print("[gran] 总耗时 %.1fs" % (time.time() - t0))
    print("=" * 74)


if __name__ == "__main__":
    main()