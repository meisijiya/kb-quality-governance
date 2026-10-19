# -*- coding: utf-8 -*-
"""explore2.py -- 探场景 beta 的规模，以及 gamma 的域组合。"""
import os
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
docs = pd.read_csv(os.path.join(PARENT, "docs.csv"), encoding="utf-8-sig")
sys.path.insert(0, PARENT)
import gen_data as G  # noqa: E402

names = [i for i, _ in G.COVERED_INTENTS]
docs["intent"] = [next((n for n in names if n in t), None) for t in docs["title"]]

print("=== 场景 beta: 缩小语料, 各规模下有多少意图彻底失去覆盖 ===")
for n in [150, 100, 75, 50, 30, 20, 15]:
    r = np.random.default_rng(42)
    sel = r.choice(len(docs), n, replace=False)
    keep = docs.iloc[sel]
    alive = set(keep["intent"].dropna())
    lost = [i for i in names if i not in alive]
    print(f"  {n:4d} 篇 -> 存活意图 {len(alive):2d}/25, 新增真缺口意图 {len(lost)}: {lost}")

print("\n=== 场景 gamma: 域偏移 ===")
for doms in [["财务管理"], ["财务管理", "人事行政"],
             ["财务管理", "人事行政", "信息技术", "采购合同"]]:
    keep = docs[docs["category"].isin(doms)]
    alive = set(keep["intent"].dropna())
    print(f"  {doms}: {len(keep):3d} 篇, 存活意图 {len(alive):2d}/25, "
          f"彻底失去覆盖 {25 - len(alive)} 个")

print("\n=== 每个域的文档数 ===")
print(docs.groupby("category").agg(n_docs=("doc_id", "count"),
                                   n_intents=("intent", "nunique")).to_string())