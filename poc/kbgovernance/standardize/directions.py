# -*- coding: utf-8 -*-
"""
directions.py -- 实测报告 §8 提出的 3 个后续方向，不停留在"建议"层面。

A: 同工单内 top-k 段落分数的形状（不做跨语料标准化）
B: 检索侧双向中心化（工单侧 - 文档流行度先验），无需业务域标签
C: 固定检出比例策略 vs 自适应阈值，公平比较可迁移性

所有实验跨 4 个场景（alpha/beta/gamma/gamma-X）跑，报 AUC 与阈值极差。
"""
import os
import re
import sys
import time

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("HF_HOME", "D:/hf_cache")
HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from standardize import (auc, best_f1_threshold, doc_intent_map,  # noqa: E402
                         get_encoder, load_base, thr_for_recall_k)

import gen_data as G  # noqa: E402


def passage_scores(docs, doc_idx, T, topk=5):
    """返回 (max, top5mean, min, doc_of_max) 每个都是 (n_tickets,) 或 (n_tickets,)。"""
    enc = get_encoder()
    texts, owner = [], []
    for j, i in enumerate(doc_idx):
        r = docs.iloc[i]
        t = f"{r['title']}。{r['content']}"
        parts = [p.strip() for p in re.split(r"[。；]", t) if len(p.strip()) >= 8]
        for p in (parts or [t]):
            texts.append(p)
            owner.append(j)
    P = np.asarray(enc.encode(texts, batch_size=64), dtype=np.float32)
    P /= (np.linalg.norm(P, axis=1, keepdims=True) + 1e-12)
    SP = T @ P.T
    owner = np.asarray(owner, dtype=np.int64)
    k = min(topk, SP.shape[1])
    part = np.partition(SP, -k, axis=1)[:, -k:]         # (n_tk, k) 最大的 k 个段落
    part = -np.sort(-part, axis=1)
    smax = part[:, 0]
    stop5 = part.mean(axis=1)
    smin = SP.min(axis=1)
    doc_of_max = owner[np.argmax(SP, axis=1)]   # 子集内的局部下标
    return smax, stop5, smin, doc_of_max, SP


def dual_center(T, smax, doc_of_max, P_owner, kb_vecs, n_docs):
    """方向 B：减去「该文档的平均被匹配度」先验。"""
    # 每篇文档的流行度先验 = 所有 top1 命中它的工单的 max 余弦均值
    prior = np.zeros(n_docs, float)
    idx = np.arange(len(doc_of_max))
    hits = doc_of_max
    cnt = np.zeros(n_docs)
    np.add.at(cnt, hits, 1.0)
    np.add.at(prior, hits, smax)
    prior = prior / np.maximum(cnt, 1.0)
    return prior[hits]


def main():
    t0 = time.time()
    docs, tickets, gt, cover_a, T, D = load_base()
    gap_a = set(gt["gap_intents"])
    ilab = tickets["intent_label"].values
    docs["intent"] = doc_intent_map(docs)
    covered = [i for i, _ in G.COVERED_INTENTS]

    r = np.random.default_rng(42)
    sel_b = np.sort(r.choice(len(docs), 75, replace=False))
    sel_g = np.where(docs["category"].isin(
        ["财务管理", "人事行政", "信息技术", "采购合同"]).values)[0]
    sel_gx = np.where(docs["category"].values == "财务管理")[0]
    for sel, tag in [(sel_b, "beta"), (sel_g, "gamma"), (sel_gx, "gamma-X")]:
        alive = set(docs.iloc[sel]["intent"].dropna())
        globals()[f"gap_{tag.replace('-', '_')}"] = \
            gap_a | {i for i in covered if i not in alive}
    gaps = {"alpha": gap_a, "beta": globals()["gap_beta"],
            "gamma": globals()["gap_gamma"], "gamma-X": globals()["gap_gamma_X"]}

    rows = []
    print("=" * 78)
    print("[DIR A/B] 同工单内形状量 + 双向中心化，跨 4 场景")
    for tag, sel in [("alpha", np.arange(len(docs))), ("beta", sel_b),
                     ("gamma", sel_g), ("gamma-X", sel_gx)]:
        smax, stop5, smin, docmax, SP = passage_scores(docs, sel, T)
        span = np.maximum(smax - smin, 1e-6)
        cand = {
            "ABS -max (基线)": -smax,
            "A1 (top5-mean)/(max-min)": -((stop5 - smin) / span),
            "A2 (max-top5)/max": (smax - stop5) / np.maximum(smax, 1e-9),
            "A3 (max-stop5)/span": (smax - stop5) / span,
            "A4 stop5-max": stop5 - smax,
        }
        # 方向 B: 文档流行度中心化
        n = len(sel)
        prior = np.zeros(n)
        cnt = np.zeros(n)
        np.add.at(cnt, docmax, 1.0)
        np.add.at(prior, docmax, smax)
        prior /= np.maximum(cnt, 1.0)
        cand["B 双向中心化 max-prior"] = -(smax - prior[docmax])
        cand["B+ top5 双向中心化"] = -((stop5 - prior[docmax]) / span)

        for nm, s in cand.items():
            df = pd.DataFrame({"i": ilab, "s": s})
            med = df.groupby("i")["s"].median()
            a = auc([v for k, v in med.items() if k in gaps[tag]],
                    [v for k, v in med.items() if k not in gaps[tag]])
            f1, p, rr, thr = best_f1_threshold(s, ilab, gaps[tag])
            ta = thr_for_recall_k(s, ilab, gaps[tag])
            rows.append(dict(方向=nm, 场景=tag, AUC=round(a, 4), F1=round(f1, 4),
                             召回全部阈值=round(ta, 4) if ta is not None else None))
        print(f"  [{tag}] done")

    dfA = pd.DataFrame(rows)
    piv = dfA.pivot(index="方向", columns="场景", values="AUC")
    print("\n=== 方向 A/B 意图级 AUC ===")
    print(piv.to_string())
    print("\n=== 跨场景阈值极差（越小越稳）===")
    tp = dfA.pivot(index="方向", columns="场景", values="召回全部阈值")
    tp["极差"] = tp.max(axis=1) - tp.min(axis=1)
    print(tp.to_string())
    dfA.to_csv(os.path.join(HERE, "results_directions.csv"), index=False,
               encoding="utf-8-sig")

    # ---------------- 方向 C：固定检出比例 vs 自适应阈值
    print("\n" + "=" * 78)
    print("[DIR C] 固定检出比例策略的跨场景表现（回答 §4.3 的比较陷阱）")
    rowsC = []
    for tag, sel in [("alpha", np.arange(len(docs))), ("beta", sel_b),
                     ("gamma", sel_g), ("gamma-X", sel_gx)]:
        smax, _, _, _, _ = passage_scores(docs, sel, T)
        for frac in [0.10, 0.15, 0.1855, 0.25, 0.30]:
            thr = float(np.quantile(smax, frac))
            s = -smax
            df = pd.DataFrame({"i": ilab, "s": s})
            med = df.groupby("i")["s"].median()
            det = {k for k, v in med.items() if v >= -thr}
            tp_ = len(det & gaps[tag])
            p = tp_ / len(det) if det else 0
            rr = tp_ / len(gaps[tag])
            f = 2 * p * rr / (p + rr) if (p + rr) > 0 else 0
            rowsC.append(dict(场景=tag, 固定检出比例=frac, 推出的绝对阈值=round(thr, 4),
                              检出意图数=len(det), P=round(p, 4), R=round(rr, 4),
                              F1=round(f, 4)))
    dfC = pd.DataFrame(rowsC)
    print(dfC.pivot(index="固定检出比例", columns="场景", values="F1").to_string())
    print("\n  各比例跨场景 F1 波动（越小越稳）：")
    pp = dfC.pivot(index="固定检出比例", columns="场景", values="F1")
    pp["标准差"] = pp.std(axis=1)
    print(pp[["标准差"]].to_string())
    dfC.to_csv(os.path.join(HERE, "results_directionC.csv"), index=False,
               encoding="utf-8-sig")
    print(f"\n[directions] 完成，总耗时 {round(time.time()-t0,1)}s")


if __name__ == "__main__":
    main()