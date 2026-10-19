# -*- coding: utf-8 -*-
"""explore.py -- 复现基线 AUC 0.968、推导 doc->intent 映射、检查各场景可行性。
只读父目录已有文件，不写任何文件。"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

docs = pd.read_csv(os.path.join(PARENT, "docs.csv"), encoding="utf-8-sig")
tickets = pd.read_csv(os.path.join(PARENT, "tickets.csv"), encoding="utf-8-sig")
cover = np.load(os.path.join(PARENT, "ticket_cover.npy"))
gt = json.load(open(os.path.join(PARENT, "ground_truth.json"), encoding="utf-8"))
gap = set(gt["gap_intents"])

# ---- 复现意图级 AUC（cover 越小越可能是缺口 -> 取负号当分数）
tk = tickets.copy()
tk["cover"] = cover
intent_med = tk.groupby("intent_label")["cover"].median()
y = np.array([1 if i in gap else 0 for i in intent_med.index])
s = -intent_med.values


def auc(y, s):
    order = np.argsort(s)
    ranks = np.empty(len(s), float)
    sv = s[order]
    r = np.arange(1, len(s) + 1, dtype=float)
    i = 0
    while i < len(sv):  # 平均秩处理并列
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        r[i:j + 1] = (i + 1 + j + 1) / 2.0
        i = j + 1
    ranks[order] = r
    npos = y.sum()
    nneg = len(y) - npos
    return (ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)


print("=== 基线复现 ===")
print(f"意图数 {len(intent_med)} / 缺口意图 {y.sum()}")
print(f"median 聚合 AUC = {auc(y, s):.4f}")
print(f"mean   聚合 AUC = {auc(y, -tk.groupby('intent_label')['cover'].mean().values):.4f}")
print(f"min    聚合 AUC = {auc(y, -tk.groupby('intent_label')['cover'].min().values):.4f}")

# ---- doc -> intent（标题里含意图名）
import re
sys.path.insert(0, PARENT)
import gen_data as G  # noqa: E402

names = [i for i, _ in G.COVERED_INTENTS]
doc_intent, miss = [], []
for t in docs["title"]:
    hit = [n for n in names if n in t]
    if len(hit) == 1:
        doc_intent.append(hit[0])
    else:
        doc_intent.append(None)
        miss.append(t)
docs["intent"] = doc_intent
print(f"\n=== doc->intent 匹配 === 未匹配 {len(miss)} 篇")
if miss:
    print(miss[:3])
cnt = docs.groupby("intent")["doc_id"].count()
print(f"意图 {cnt.shape[0]} 个 / 每意图文档数 min={cnt.min()} max={cnt.max()}")
print("文档 category 与意图域一致性:",
      (docs.groupby("intent")["category"].nunique() == 1).all())

# ---- 意图 -> 域（缺口意图无文档，用工单向量与各域文档的相似度反推）
print("\n=== 缺口意图的域归属（数据驱动反推） ===")
T = np.load(os.path.join(PARENT, "ticket_emb.npy"))
D = np.load(os.path.join(PARENT, "doc_emb.npy"))
dom = {}
for gi in sorted(gap):
    idx = np.where(tickets["intent_label"].values == gi)[0]
    v = T[idx].mean(axis=0)
    v /= np.linalg.norm(v)
    sims = {c: float(np.mean(D[np.where(docs['category'].values == c)[0]] @ v))
            for c in sorted(docs["category"].unique())}
    best = max(sims, key=sims.get)
    dom[gi] = best
    top = sorted(sims.items(), key=lambda x: -x[1])[:3]
    print(f"  {gi:12s} -> {best:6s}  top3={[(k, round(v, 4)) for k, v in top]}")

# 与 COVERED_INTENTS 的域对照，验证反推方法的可信度
print("\n  对照：已覆盖意图的文档 category =", {i: c for i, c in G.COVERED_INTENTS[:4]})

# ---- 场景 beta 可行性：抽 100 篇会有多少意图失去全部文档
rng = np.random.default_rng(42)
for seed in [42, 7, 2024]:
    r = np.random.default_rng(seed)
    sel = r.choice(len(docs), 100, replace=False)
    keep = docs.iloc[sel]
    alive = set(keep["intent"].dropna())
    lost = [i for i in names if i not in alive]
    print(f"\nseed={seed}: 100 篇 -> 存活意图 {len(alive)}/25, 失去全部文档的意图 {len(lost)}")
    print("   ", lost)

# ---- 场景 gamma 可行性
for doms in [["财务管理"], ["财务管理", "人事行政", "信息技术", "采购合同"]]:
    keep = docs[docs["category"].isin(doms)]
    alive = set(keep["intent"].dropna())
    print(f"\ngamma 保留域 {doms}: 文档 {len(keep)} 篇, 存活意图 {len(alive)}/25")