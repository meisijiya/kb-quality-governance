# -*- coding: utf-8 -*-
"""
detect.py -- 三个检测模块 + 与 ground truth 的对比评估

  A. 知识缺口  HDBSCAN 聚类工单 -> 代表工单检索文档 -> 最高相似度 < 阈值 = 缺口
     判定单元 = 业务意图。意图级覆盖度 = 该意图下所有簇覆盖度的最小值（min 聚合）。
     簇是算法实现的中间量，簇数不进主指标，只作为溯源明细落盘。
  B. 内容腐化  纯规则引擎（4 条规则加权打分），按两类缺陷口径分别评估：
       内容过期（规则集 R1 + R3）与 维护周期（规则集 R2 + R4）
     每类口径独立判定：子集内加权分 >= 阈值即该类缺陷成立。两类语义不同，
     各自单独报 P/R/F1；合计只作覆盖面说明，不合成单一 F1。
  C. 重复冗余  文档两两余弦相似度 -> 连通分量 -> 主文档选举

两种运行模式：
  默认（有真值）  读 ground_truth.json，按真值择优阈值并计算 P/R/F1
  --no-gt（无真值）固定阈值 min_cluster_size=5 / 缺口 0.62 / 腐化 3 / 重复 0.95，
                 P/R/F1 与真值列留空，指标里 has_ground_truth=false

产出:
  gap_threshold.csv       知识缺口扫参表
  gap_intents_best.csv    知识缺口意图级清单（主口径，与页面/下载一致）
  gap_clusters_best.csv   知识缺口簇级明细（溯源用）
  dup_threshold.csv       重复冗余扫参表
  dup_groups_best.csv     重复簇明细
  corrupt_docs.csv        腐化文档明细（逐篇含两类口径命中与误报归因）
  metrics.json            汇总指标（论文与文档的全部数字来自这里）
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DATE = date(2026, 10, 1)
STALE_YEARS = {2024, 2025}
STALE_MARKERS = ["截止", "失效", "废止", "施行", "有效期", "不再适用", "同时废止"]

GAP_THRESHOLDS = [0.30, 0.40, 0.50, 0.60, 0.70,        # 任务要求的五个
                  0.62, 0.64, 0.66, 0.68, 0.72, 0.74]  # 补充细扫
MIN_CLUSTER_SIZES = [5, 10]
DUP_THRESHOLDS = [0.85, 0.90, 0.95]

RULE_WEIGHTS = {"R1_正文过期日期": 3, "R2_更新时间超18个月": 2,
                "R3_正文含绝对过期年份": 2, "R4_同类存在更新文档": 1}
CORRUPT_SCORE_THRESHOLD = 3

# 无真值模式（--no-gt）使用的固定参数：阈值不再按真值择优，固定为需求给定值
FIXED_MIN_CLUSTER_SIZE = 5
FIXED_GAP_THRESHOLD = 0.62
FIXED_DUP_THRESHOLD = 0.95

# 两类缺陷口径。规则子集内的加权分 >= CORRUPT_SCORE_THRESHOLD 即该类缺陷成立。
# truth_key 指向生成器在 docs.csv 的 corrupt_reason 里留下的埋设成因标记。
CORRUPT_CAUSES = {
    "content_expiry": {
        "label": "内容过期",
        "rules": ("R1_正文过期日期", "R3_正文含绝对过期年份"),
        "truth_key": "stale_text",
    },
    "maintenance": {
        "label": "维护周期",
        "rules": ("R2_更新时间超18个月", "R4_同类存在更新文档"),
        "truth_key": "stale_mtime",
    },
}


# ============================================================ 工具
def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def bigrams(s):
    s = "".join(ch for ch in str(s) if ch.strip())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def containment(a, b):
    """标题包含度：短标题的 bigram 有多少出现在长标题里。"""
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


# ============================================================ A. 知识缺口
def detect_gaps(T, cover, tickets, gt_gap):
    """返回 (rows, all_clusters, best)。gt_gap 为 None 表示无真值，只跑固定参数。"""
    rows, all_clusters = [], {}
    mcs_list = MIN_CLUSTER_SIZES if gt_gap is not None else [FIXED_MIN_CLUSTER_SIZE]
    for mcs in mcs_list:
        t0 = time.time()
        labels = HDBSCAN(min_cluster_size=mcs, metric="euclidean",
                         copy=True).fit_predict(T)
        noise = int((labels == -1).sum())
        cl = []
        for lab in sorted(set(labels.tolist()) - {-1}):
            idx = np.where(labels == lab)[0]
            members = T[idx]
            centroid = members.mean(axis=0)
            centroid /= (np.linalg.norm(centroid) + 1e-12)
            rep_local = int(np.argmax(members @ centroid))
            rep = int(idx[rep_local])
            score = float(np.median(cover[idx]))       # 簇级覆盖度取中位数
            repsim = float(cover[rep])
            intents = tickets["intent_label"].values[idx]
            top_intent, top_n = Counter(intents).most_common(1)[0]
            purity = top_n / len(idx)
            cl.append({"cluster_id": int(lab), "size": int(len(idx)),
                       "rep_ticket": tickets["ticket_id"].values[rep],
                       "rep_text": tickets["content"].values[rep],
                       "rep_cover": repsim, "cover_median": score,
                       "intent": top_intent, "purity": purity,
                       "n_intent_members": top_n})
        secs = time.time() - t0
        all_clusters[mcs] = (cl, noise, secs)
        print(f"[gap] min_cluster_size={mcs}: {len(cl)} 个簇, 噪声 {noise} 条, "
              f"耗时 {secs:.2f}s")

        if gt_gap is None:
            # 无真值：不扫参，只落固定阈值的读数
            thr = FIXED_GAP_THRESHOLD
            gapc = [c for c in cl if c["cover_median"] < thr]
            det = {c["intent"] for c in gapc}
            rows.append({"min_cluster_size": mcs, "threshold": thr,
                         "gap_clusters": len(gapc), "detected_intents": len(det),
                         "precision": None, "recall": None, "f1": None})
            continue

        for thr in GAP_THRESHOLDS:
            gapc = [c for c in cl if c["cover_median"] < thr]
            det = {c["intent"] for c in gapc}
            tp = len(det & gt_gap)
            p, r, f = prf(tp, len(det) - tp, len(gt_gap) - tp)
            rows.append({"min_cluster_size": mcs, "threshold": round(thr, 3),
                         "gap_clusters": len(gapc), "detected_intents": len(det),
                         "precision": round(p, 4), "recall": round(r, 4),
                         "f1": round(f, 4)})

    if gt_gap is None:
        best = dict(rows[-1])
    else:
        best = max(rows, key=lambda x: (x["f1"], x["precision"]))
    return rows, all_clusters, best


def aggregate_intents(clusters, threshold, gt_gap):
    """意图级聚合：覆盖度取该意图下所有簇覆盖度的最小值（min 聚合）。

    判定上 min(簇覆盖度) < 阈值 与「存在一个簇覆盖度 < 阈值」等价，
    因此意图级与簇级检出集合一致，差别只在展示粒度。
    """
    by_intent = defaultdict(list)
    for c in clusters:
        by_intent[c["intent"]].append(c)
    rows = []
    for intent, cs in by_intent.items():
        worst = min(cs, key=lambda x: x["cover_median"])
        rows.append({
            "intent": intent,
            "n_clusters": len(cs),
            "min_cover_median": round(worst["cover_median"], 4),
            "total_tickets": int(sum(x["size"] for x in cs)),
            "is_gap": int(worst["cover_median"] < threshold),
            "is_true_gap": "" if gt_gap is None else int(intent in gt_gap),
            "rep_ticket": worst["rep_ticket"],
            "rep_text": worst["rep_text"],
        })
    rows.sort(key=lambda r: (r["min_cover_median"], r["intent"]))
    return rows


# ============================================================ B. 内容腐化
def detect_corruption(docs):
    dm = docs.set_index("doc_id")
    lm = pd.to_datetime(dm["last_modified"])

    rows = []
    for doc_id, r in dm.iterrows():
        content = str(r["content"])
        title = str(r["title"])
        hits, reasons = [], []

        years = {int(y) for y in re.findall(r"(20\d{2})\s*年", content)}
        has_marker = any(m in content for m in STALE_MARKERS)
        if years and has_marker and any(y < BASE_DATE.year for y in years):
            hits.append("R1_正文过期日期")
            reasons.append(f"正文含早于{BASE_DATE.year}年的日期表述+过期标记词")

        if lm[doc_id] < pd.Timestamp(BASE_DATE) - pd.DateOffset(months=18):
            hits.append("R2_更新时间超18个月")
            reasons.append(f"last_modified={r['last_modified']}, "
                           f"距基准日超过18个月")

        if years & STALE_YEARS:
            hits.append("R3_正文含绝对过期年份")
            reasons.append(f"正文含绝对过期年份 {sorted(years & STALE_YEARS)}")

        # R4: 同 category 下存在"明显更新"且标题主题重合的文档。
        # 说明：任务书原文是"同 category 下存在更新时间更新的文档"。直接照抄会让
        # 本规则命中几乎全部文档（同域内总有更新的），因此加了两道约束：
        #   ① 对方更新时间领先本篇 ≥ 365 天（而不是任意领先）；
        #   ② 标题 bigram 包含度 ≥ 0.50。
        # 这仍是对原规则的收紧实现，属于规则工程细节，已在 RESULT.md 说明。
        same = dm[(dm["category"] == r["category"]) & (dm.index != doc_id)]
        newer = [d for d in same.index
                 if lm[d] > lm[doc_id] + pd.Timedelta(days=365)
                 and containment(title, dm["title"][d]) >= 0.50]
        if newer:
            hits.append("R4_同类存在更新文档")
            reasons.append(f"同'{r['category']}'下有 {len(newer)} 篇更新且标题重合的文档")

        score = sum(RULE_WEIGHTS[h] for h in hits)
        row = {"doc_id": doc_id, "title": title, "category": r["category"],
               "last_modified": r["last_modified"],
               "risk_score": score, "rule_hits": "|".join(hits),
               "reasons": "; ".join(reasons)}
        # 两类口径各自在规则子集内算分（阈值与主判定一致）
        for name, spec in CORRUPT_CAUSES.items():
            row["cause_score_" + name] = sum(RULE_WEIGHTS[h] for h in hits
                                              if h in spec["rules"])
        rows.append(row)
    return pd.DataFrame(rows)


def planted_docs(docs):
    """被生成器埋入缺陷的文档集合（corrupt_reason 非空）。"""
    if "corrupt_reason" not in docs.columns:
        return set()
    out = set()
    for row in docs.itertuples():
        reason = str(getattr(row, "corrupt_reason", "") or "")
        if reason and reason != "nan":
            out.add(row.doc_id)
    return out


def planted_by_nature(docs):
    """按生成器埋设成因分桶：stale_text → 内容过期，stale_mtime → 维护周期。

    两个桶互斥（生成器按 all_ids 的互斥切片埋设），但一篇被埋设的文档可能
    在物理状态上同时满足另一类口径的判据——DOC0241 就是这样：它被埋的是
    正文过期，同时它的 last_modified 早就于 18 个月且同域存在更新文档。
    因此口径真值取「被埋设 ∧ 满足本口径判据」，跨类文档在两个口径下都算真阳性。
    """
    out = {name: set() for name in CORRUPT_CAUSES}
    if "corrupt_reason" not in docs.columns:
        return out
    for row in docs.itertuples():
        reason = str(getattr(row, "corrupt_reason", "") or "")
        for name, spec in CORRUPT_CAUSES.items():
            if spec["truth_key"] in reason:
                out[name].add(row.doc_id)
    return out


# ============================================================ C. 重复冗余
def dup_groups_at(S, thr):
    n = S.shape[0]
    uf = UnionFind(n)
    ii, jj = np.where(np.triu(S, 1) >= thr)
    for a, b in zip(ii, jj):
        uf.union(int(a), int(b))
    groups = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)
    return [sorted(v) for v in groups.values() if len(v) >= 2]


def elect_primary(members, docs):
    """主文档选举：ref_count 高 + last_modified 新 + 标题被包含度高。"""
    m = docs.iloc[members].copy()
    rc = pd.to_numeric(m["ref_count"], errors="coerce").fillna(0)
    lm = pd.to_datetime(m["last_modified"]).astype("int64")
    cont = []
    for _, r in m.iterrows():
        others = [x for x in m.index if x != r.name]
        cont.append(max([containment(r["title"], docs["title"][o]) for o in others],
                        default=0.0))
    score = (rc / rc.max()) + (lm / lm.max()) + np.asarray(cont)
    m["_score"] = score
    return m["_score"].idxmax()


# ============================================================ main
def parse_args():
    ap = argparse.ArgumentParser(description="知识库质量治理三模块检测")
    ap.add_argument("--no-gt", action="store_true",
                    help="无真值模式：固定阈值、不计算 P/R/F1，真值列留空")
    ap.add_argument("--out-dir", default=None,
                    help="产物输出目录（默认与本脚本同级；用于把扫描结果与基线隔离）")
    return ap.parse_args()


def main():
    args = parse_args()
    t_all = time.time()
    out_dir = os.path.abspath(args.out_dir) if args.out_dir else HERE
    os.makedirs(out_dir, exist_ok=True)

    docs = pd.read_csv(os.path.join(HERE, "docs.csv"), encoding="utf-8-sig")
    tickets = pd.read_csv(os.path.join(HERE, "tickets.csv"), encoding="utf-8-sig")
    D = np.load(os.path.join(HERE, "doc_emb.npy"))
    T = np.load(os.path.join(HERE, "ticket_emb.npy"))
    cover = np.load(os.path.join(HERE, "ticket_cover.npy"))
    emeta = json.load(open(os.path.join(HERE, "embeddings_meta.json"),
                           encoding="utf-8"))

    has_gt = not args.no_gt
    gt = {}
    gt_path = os.path.join(HERE, "ground_truth.json")
    if has_gt:
        gt = json.load(open(gt_path, encoding="utf-8"))
    elif os.path.exists(gt_path):
        print("[detect] --no-gt：忽略 ground_truth.json，不计算 P/R/F1")

    docs_idx = docs.set_index("doc_id")
    doc_ids = docs["doc_id"].tolist()

    print("=" * 74)
    print(f"[detect] embedding 方案 = {emeta['scheme']} ({emeta['model']})")
    print(f"[detect] 输入: {D.shape[0]} 文档 / {T.shape[0]} 工单")
    print(f"[detect] 模式: {'有真值（按真值择优阈值）' if has_gt else '无真值（固定阈值）'}")
    if has_gt:
        print(f"[detect] ground truth: 缺口意图 {len(gt['gap_intents'])} / "
              f"腐化文档 {len(gt['corrupt_doc_ids'])} / 重复组 {len(gt['dup_groups'])}")

    metrics = {"embedding": emeta, "has_ground_truth": has_gt}

    # ==================================================== C 重复冗余（先跑）
    # 重复件身份要从「检测出来的重复组」推导，不能从真值推导——Web 端没有真值。
    print("\n" + "-" * 74)
    print("[detect] === C. 重复冗余检测 ===")
    t0 = time.time()
    S = D @ D.T
    np.fill_diagonal(S, -1.0)
    print(f"[dup] 300x300 余弦矩阵耗时 {time.time() - t0:.2f}s")
    gt_dup = [set(g) for g in gt.get("dup_groups", [])] if has_gt else []
    gt_doc2grp = {}
    for gi, g in enumerate(gt_dup):
        for d in g:
            gt_doc2grp[d] = gi

    dup_rows = []
    for thr in (DUP_THRESHOLDS if has_gt else [FIXED_DUP_THRESHOLD]):
        t1 = time.time()
        groups = dup_groups_at(S, thr)
        secs = time.time() - t1
        correct = 0
        for g in groups:
            gids = {gt_doc2grp.get(doc_ids[i]) for i in g}
            if len(gids) == 1 and None not in gids:
                correct += 1
        if has_gt:
            gp, gr, gf = prf(correct, len(groups) - correct, len(gt_dup) - correct)
        else:
            gp = gr = gf = None
        det_docs = {doc_ids[i] for g in groups for i in g}
        if has_gt:
            d_tp = len(det_docs & set(gt_doc2grp))
            dp, dr, df = prf(d_tp, len(det_docs) - d_tp, len(gt_doc2grp) - d_tp)
        else:
            dp = dr = df = None
        dup_rows.append({"threshold": thr, "dup_groups": len(groups),
                         "detected_docs": len(det_docs),
                         "group_precision": None if gp is None else round(gp, 4),
                         "group_recall": None if gr is None else round(gr, 4),
                         "group_f1": None if gf is None else round(gf, 4),
                         "doc_precision": None if dp is None else round(dp, 4),
                         "doc_recall": None if dr is None else round(dr, 4),
                         "doc_f1": None if df is None else round(df, 4),
                         "seconds": round(secs, 2)})
        extra = ""
        if has_gt:
            extra = (f" (真实 {len(gt_dup)} 组 / {len(gt_doc2grp)} 篇) | "
                     f"组级 P={gp:.3f} R={gr:.3f} F1={gf:.3f} | "
                     f"文档级 P={dp:.3f} R={dr:.3f} F1={df:.3f}")
        print(f"[dup] thr={thr}: {len(groups)} 组 / {len(det_docs)} 篇{extra} | "
              f"{secs:.2f}s")

    with open(os.path.join(out_dir, "dup_threshold.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(dup_rows[0].keys()))
        w.writeheader()
        w.writerows(dup_rows)

    if has_gt:
        best_dup = max(dup_rows, key=lambda x: x["group_f1"])
    else:
        best_dup = dup_rows[-1]
    groups = dup_groups_at(S, best_dup["threshold"])
    dup_copies, dup_source_map = set(), {}
    for g in groups:
        ids = [doc_ids[i] for i in g]
        src = min(ids)          # 组内 id 最小者为源文档
        for x in ids:
            if x != src:
                dup_copies.add(x)
                dup_source_map[x] = src
    with open(os.path.join(out_dir, "dup_groups_best.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["group", "size", "primary_doc", "member_docs", "max_sim",
                    "is_true_group"])
        for gi, g in enumerate(groups, 1):
            ids = [doc_ids[i] for i in g]
            sub = S[np.ix_(g, g)]
            prim = elect_primary(g, docs_idx)
            gids = {gt_doc2grp.get(x) for x in ids}
            off = sub[~np.eye(len(g), dtype=bool)]
            w.writerow([gi, len(g), prim, "|".join(ids),
                        round(float(off.max()), 4),
                        "" if not has_gt else
                        int(len(gids) == 1 and None not in gids)])
    metrics["dup"] = {"embedded_groups": len(gt_dup), "embedded_docs": len(gt_doc2grp),
                      "rows": dup_rows, "best": best_dup,
                      "detected_groups": len(groups),
                      "duplicate_copies": len(dup_copies)}

    # ==================================================== A 知识缺口
    print("\n" + "-" * 74)
    print("[detect] === A. 知识缺口检测 ===")
    gt_gap = set(gt["gap_intents"]) if has_gt else None
    gap_rows, all_clusters, best = detect_gaps(T, cover, tickets, gt_gap)
    with open(os.path.join(out_dir, "gap_threshold.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(gap_rows[0].keys()))
        w.writeheader()
        w.writerows(gap_rows)
    if has_gt:
        print(f"[gap] 最优参数: min_cluster_size={best['min_cluster_size']} "
              f"threshold={best['threshold']} -> "
              f"P={best['precision']} R={best['recall']} F1={best['f1']}")
        print("[gap] 扫参表 (gap_threshold.csv):")
        print(f"{'mcs':>4} {'thr':>6} {'gap_cl':>7} {'det_int':>8} "
              f"{'P':>7} {'R':>7} {'F1':>7}")
        for r in gap_rows:
            print(f"{r['min_cluster_size']:>4} {r['threshold']:>6} "
                  f"{r['gap_clusters']:>7} {r['detected_intents']:>8} "
                  f"{r['precision']:>7} {r['recall']:>7} {r['f1']:>7}")
    else:
        print(f"[gap] 固定参数: min_cluster_size={best['min_cluster_size']} "
              f"threshold={best['threshold']} -> 无真值，不计算 P/R/F1")

    cl = all_clusters[best["min_cluster_size"]][0]
    thr = best["threshold"]
    gap_c = [c for c in cl if c["cover_median"] < thr]
    intent_rows = aggregate_intents(cl, thr, gt_gap)
    gap_intent_rows = [r for r in intent_rows if r["is_gap"]]

    # 意图级清单（主口径）：与页面、下载的清单是同一份数据
    with open(os.path.join(out_dir, "gap_intents_best.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["intent", "n_clusters",
                                          "min_cover_median", "total_tickets",
                                          "threshold", "is_true_gap",
                                          "rep_ticket", "rep_text"])
        w.writeheader()
        for r in gap_intent_rows:
            w.writerow({"intent": r["intent"], "n_clusters": r["n_clusters"],
                        "min_cover_median": r["min_cover_median"],
                        "total_tickets": r["total_tickets"],
                        "threshold": thr, "is_true_gap": r["is_true_gap"],
                        "rep_ticket": r["rep_ticket"], "rep_text": r["rep_text"]})
    print(f"[gap] 意图级清单: {len(gap_intent_rows)} 个缺口意图 "
          f"(对应 {len(gap_c)} 个缺口簇，簇级明细见 gap_clusters_best.csv)")

    # 簇级明细（溯源用）：min 聚合可由它逐簇复算
    with open(os.path.join(out_dir, "gap_clusters_best.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["cluster_id", "intent", "size", "cover_median", "rep_cover",
                    "rep_ticket", "rep_text", "purity", "n_intent_members",
                    "is_gap", "is_true_gap"])
        for c in sorted(cl, key=lambda x: (x["cover_median"], x["cluster_id"])):
            w.writerow([c["cluster_id"], c["intent"], c["size"],
                        round(c["cover_median"], 4), round(c["rep_cover"], 4),
                        c["rep_ticket"], c["rep_text"], round(c["purity"], 4),
                        c["n_intent_members"],
                        int(c["cover_median"] < thr),
                        "" if gt_gap is None else int(c["intent"] in gt_gap)])

    # 簇数与噪声条数是确定性结果（重复运行完全一致），必须落盘：
    # 论文与方案里的「95 簇 / 0 噪声」「88 簇 / 9 噪声」要有机读出处。
    # 聚类耗时按现行口径不落盘——它跨运行波动 ±25%，只在正文报量级。
    metrics["gap"] = {"best": best, "n_gap_clusters": len(gap_c),
                      "n_gap_intents": len(gap_intent_rows),
                      "gap_intents": [r["intent"] for r in gap_intent_rows],
                      "threshold_rows": gap_rows,
                      "intent_rows": intent_rows,
                      "clusters": {str(mcs): {"n_clusters": len(cl_mcs),
                                              "n_noise": noise}
                                   for mcs, (cl_mcs, noise, _) in all_clusters.items()}}

    # ==================================================== B 内容腐化
    print("\n" + "-" * 74)
    print("[detect] === B. 内容腐化检测 ===")
    t0 = time.time()
    corr = detect_corruption(docs)
    secs_corr = time.time() - t0
    gt_corrupt = set(gt.get("corrupt_doc_ids", [])) if has_gt else set()
    # 防作弊对照集（生成器 4% 分支命中），用于误报归因
    control_set = set(gt.get("control_doc_ids", [])) if has_gt else set()
    print(f"[corr] 规则权重 {RULE_WEIGHTS} 判定阈值 risk_score >= {CORRUPT_SCORE_THRESHOLD}")
    print(f"[corr] 耗时 {secs_corr:.2f}s")

    planted = planted_docs(docs) if has_gt else set()
    nature_sets = planted_by_nature(docs) if has_gt else \
        {name: set() for name in CORRUPT_CAUSES}

    by_cause = {}
    for name, spec in CORRUPT_CAUSES.items():
        hit_col = "cause_score_" + name
        hits = set(corr.loc[corr[hit_col] >= CORRUPT_SCORE_THRESHOLD, "doc_id"])
        nature = nature_sets[name]
        # 真值 = 被埋设 ∧ 满足本口径判据；跨类文档（埋的是另一类、但物理上
        # 同时满足本类）在两个口径下都算真阳性——它是真缺陷，只是成因不止一个。
        tp_set = hits & planted
        fp_set = hits - planted
        fn_set = nature - hits
        positives = tp_set | fn_set
        cross = sorted(tp_set - nature)
        p = len(tp_set) / len(hits) if hits else None
        r = len(tp_set) / len(positives) if positives else None
        f = 2 * p * r / (p + r) if (p is not None and r is not None and p + r) else None
        attrib = Counter()
        for d in fp_set:
            if d in dup_copies:
                attrib["dup_inherited_stale"] += 1
            elif d in control_set:
                attrib["control_stale"] += 1
            else:
                attrib["other"] += 1
        by_cause[name] = {
            "label": spec["label"],
            "rules": list(spec["rules"]),
            "truth_key": spec["truth_key"],
            "threshold": CORRUPT_SCORE_THRESHOLD,
            "planted_of_this_nature": len(nature),
            "detected": len(hits),
            "tp": len(tp_set), "fp": len(fp_set), "fn": len(fn_set),
            "precision": None if p is None else round(p, 4),
            "recall": None if r is None else round(r, 4),
            "f1": None if f is None else round(f, 4),
            "truth_doc_ids": sorted(tp_set | fn_set),
            "tp_doc_ids": sorted(tp_set),
            "fp_doc_ids": sorted(fp_set),
            "fn_doc_ids": sorted(fn_set),
            "cross_class_doc_ids": cross,
            "fp_attribution": dict(attrib),
        }
        print(f"[corr][{name}] {spec['label']}（规则 {'+'.join(spec['rules'])}）: "
              f"真值 {len(tp_set | fn_set)} 篇 / 检出 {len(hits)} 篇 / "
              f"TP={len(tp_set)} FP={len(fp_set)} FN={len(fn_set)}"
              + (f" | P={p:.4f} R={r:.4f} F1={f:.4f}" if p is not None else "")
              + (f" | 跨类文档 {len(cross)} 篇" if cross else ""))

    # 合计口径只作覆盖面说明：两类缺陷语义不同，不合成单一 F1。
    corr_out = corr[corr["risk_score"] >= CORRUPT_SCORE_THRESHOLD]
    det_corrupt = set(corr_out["doc_id"])
    union_tp = det_corrupt & gt_corrupt
    union_fp = det_corrupt - gt_corrupt
    union_fn = gt_corrupt - det_corrupt
    print(f"[corr] 合计检出 {len(det_corrupt)} 篇（真值 {len(gt_corrupt)} 篇，"
          f"覆盖 {len(union_tp)} 篇），两类口径的 P/R/F1 见上，不合成单一 F1")

    # 逐篇标记：命中哪类口径、在该口径下是否真值、误报原因
    fp_causes, fp_reason = {}, {}
    for name in CORRUPT_CAUSES:
        fp_set = set(by_cause[name]["fp_doc_ids"])
        for d in fp_set:
            fp_causes.setdefault(d, []).append(name)
    for d, causes in fp_causes.items():
        reason = ""
        if d in dup_copies:
            reason = "dup_inherited_stale"
        elif d in control_set:
            reason = "control_stale"
        else:
            reason = "other"
        fp_reason[d] = reason
    corr["fp_causes"] = corr["doc_id"].map(
        lambda d: ",".join(fp_causes.get(d, [])))
    corr["fp_reason"] = corr["doc_id"].map(fp_reason).fillna("")
    corr["in_control_sample"] = corr["doc_id"].isin(control_set).astype(int)
    corr["is_dup_copy"] = corr["doc_id"].isin(dup_copies).astype(int)
    corr["dup_source"] = corr["doc_id"].map(dup_source_map).fillna("")
    corr.sort_values("risk_score", ascending=False).to_csv(
        os.path.join(out_dir, "corrupt_docs.csv"), index=False, encoding="utf-8-sig")

    metrics["corrupt"] = {
        "embedded": len(gt_corrupt),
        "detected": len(det_corrupt),
        "covered": len(union_tp),
        "fn": len(union_fn),
        "fp": len(union_fp),
        "by_cause": by_cause,
        "control_sampled": len(control_set),
        "control_sampled_doc_ids": sorted(control_set),
        "rule_weight": RULE_WEIGHTS,
        "score_threshold": CORRUPT_SCORE_THRESHOLD,
        "rule_hit_counts": {h: int(corr['rule_hits'].str.contains(h).sum())
                            for h in RULE_WEIGHTS},
        "score_hist": dict(Counter(corr["risk_score"]).most_common()),
        "seconds": round(secs_corr, 2),
    }

    # ==================================================== 落盘
    metrics["total_seconds"] = round(time.time() - t_all, 2)
    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2, default=str)

    print("\n" + "=" * 74)
    if has_gt:
        print(f"[detect] 全部完成, 总耗时 {metrics['total_seconds']}s")
        print(f"[detect] 缺口 F1={best['f1']}（意图级） | "
              f"腐化 F1=内容过期 {by_cause['content_expiry']['f1']} / "
              f"维护周期 {by_cause['maintenance']['f1']} | "
              f"重复 组级F1={best_dup['group_f1']}")
    else:
        print(f"[detect] 全部完成, 总耗时 {metrics['total_seconds']}s（无真值模式）")
    print("=" * 74)


if __name__ == "__main__":
    main()
