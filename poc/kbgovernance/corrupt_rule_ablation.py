# -*- coding: utf-8 -*-
"""
corrupt_rule_ablation.py -- 内容腐化 4 条规则的贡献度消融（可复算版）

回答: R1/R2/R3/R4 各自对「腐化检测 precision / recall / F1」贡献多少？

口径与 detect.py 完全一致, 保证数字可比:
  * 分组单位 = 文档（与 detect.py 的 metrics.json:corrupt 同级）
  * 判定口径 = risk_score >= score_threshold，risk_score = sum(命中规则的权重)
  * 权重与阈值一律从 metrics.json:corrupt 读取，不在本文件里硬编码第二份
  * true positive 集合 = ground_truth.json:corrupt_doc_ids（埋的 62 篇）

两类设置:
  all       四条规则全用（等价于 detect.py 的主结果，必须逐位复现 P/R/F1）
  drop_Rn   屏蔽第 n 条规则后重算（leave-one-rule-out）
  only_Rn   只用第 n 条规则（单规则可分性）

产出:
  corrupt_rule_ablation.csv   列: setting / precision / recall / f1 / detected /
                              tp / fp / fn / 命中文档数 / 平均风险分 / 相对 all 的 ΔF1

运行: python corrupt_rule_ablation.py   (纯规则+查表，无随机性)
"""
import csv
import json
import os
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(HERE, "corrupt_rule_ablation.csv")


# ============================================================ 工具（与 detect.py 同名同义）
def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def short(tag):
    """R1_正文过期日期 -> R1，便于列名。"""
    return tag.split("_", 1)[0]


def evaluate(corr, weights, threshold, gt_corrupt, active):
    """active: 参与打分的规则集合(短名)。返回指标 dict。"""
    scores, nhit = [], []
    for hits in corr["_hits"]:
        s = sum(weights[h] for h in hits if short(h) in active)
        scores.append(s)
        nhit.append(sum(1 for h in hits if short(h) in active))
    scores = pd.Series(scores, index=corr.index)
    det = set(corr.index[scores >= threshold])
    tp = len(det & gt_corrupt)
    fp, fn = len(det) - tp, len(gt_corrupt) - tp
    p, r, f = prf(tp, fp, fn)
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4),
            "detected": len(det), "tp": tp, "fp": fp, "fn": fn,
            "mean_risk": round(float(scores.mean()), 4),
            "docs_with_hit": int(sum(1 for x in nhit if x > 0))}


# ============================================================ main
def main():
    metrics = json.load(open(os.path.join(HERE, "metrics.json"), encoding="utf-8"))
    gt = json.load(open(os.path.join(HERE, "ground_truth.json"), encoding="utf-8"))
    corr = pd.read_csv(os.path.join(HERE, "corrupt_docs.csv"), encoding="utf-8-sig")

    weights = metrics["corrupt"]["rule_weight"]
    threshold = int(metrics["corrupt"]["score_threshold"])
    ref = metrics["corrupt"]
    gt_corrupt = set(gt["corrupt_doc_ids"])

    # rule_hits 是 "R1_..|R3_.." 字符串; 空值在 pandas 里是 NaN, 统一成空元组
    corr["_hits"] = [tuple(h for h in str(s).split("|") if h and h != "nan")
                     for s in corr["rule_hits"].fillna("")]
    corr = corr.set_index("doc_id")

    print("=" * 74)
    print("[ablation] 文档 %d 篇 / 埋入腐化 %d 篇 / 判定阈值 risk_score >= %d"
          % (len(corr), len(gt_corrupt), threshold))
    print("[ablation] 规则权重（自 metrics.json 读取）: %s" % weights)

    # ---- 口径自检 1: risk_score 必须能被 rule_hits × 权重完全重算 ----
    recomputed = [sum(weights[h] for h in hs) for hs in corr["_hits"]]
    bad = int((pd.Series(recomputed, index=corr.index) != corr["risk_score"]).sum())
    print("[ablation] 口径自检 1: risk_score 由 rule_hits 重算, 不一致 %d 篇 %s"
          % (bad, "OK" if bad == 0 else "<-- 有问题"))

    # ---- 口径自检 2: 各规则命中数必须与 metrics.json 一致 ----
    counts = {short(h): int(corr["_hits"].apply(lambda hs, t=h: t in hs).sum())
              for h in weights}
    same = all(counts[short(h)] == v for h, v in ref["rule_hit_counts"].items())
    print("[ablation] 口径自检 2: 各规则命中数 %s vs metrics.json %s -> %s"
          % (counts, {short(k): v for k, v in ref["rule_hit_counts"].items()},
             "OK" if same else "<-- 有问题"))

    # ---- 口径自检 3: all 设置必须逐位复现 detect.py 的主结果 ----
    all_rules = {short(h) for h in weights}
    base = evaluate(corr, weights, threshold, gt_corrupt, all_rules)
    ok3 = (base["precision"] == ref["precision"] and base["recall"] == ref["recall"]
           and base["f1"] == ref["f1"] and base["detected"] == ref["detected"]
           and base["tp"] == ref["tp"] and base["fp"] == ref["fp"]
           and base["fn"] == ref["fn"])
    print("[ablation] 口径自检 3: all = P%.4f R%.4f F1%.4f vs metrics.json P%.4f R%.4f "
          "F1%.4f -> %s" % (base["precision"], base["recall"], base["f1"],
                            ref["precision"], ref["recall"], ref["f1"],
                            "OK" if ok3 else "<-- 有问题"))
    if not (bad == 0 and same and ok3):
        print("[ablation] 口径自检未全部通过, 下方消融数字与 detect.py 不可比")

    # ---- 消融 ----
    rules = sorted(all_rules)
    rows = [dict(setting="all", **base, delta_f1="")]
    for rn in rules:
        rows.append(dict(setting=f"drop_{rn}",
                         **evaluate(corr, weights, threshold, gt_corrupt,
                                    all_rules - {rn})))
    for rn in rules:
        rows.append(dict(setting=f"only_{rn}",
                         **evaluate(corr, weights, threshold, gt_corrupt, {rn})))

    df = pd.DataFrame(rows)
    df["delta_f1"] = [(round(r["f1"] - base["f1"], 4) if r["setting"] != "all" else "")
                      for _, r in df.iterrows()]
    cols = ["setting", "precision", "recall", "f1", "detected", "tp", "fp", "fn",
            "docs_with_hit", "mean_risk", "delta_f1"]
    df = df[cols]
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print("\n" + "-" * 74)
    print("[ablation] 逐条剔除（drop_*）与单规则（only_*）:")
    print("%-10s %9s %8s %8s %9s %4s %4s %4s %8s"
          % ("setting", "precision", "recall", "f1", "detected", "tp", "fp", "fn",
             "Δf1"))
    for _, r in df.iterrows():
        print("%-10s %9.4f %8.4f %8.4f %9d %4d %4d %4d %8s"
              % (r["setting"], r["precision"], r["recall"], r["f1"],
                 r["detected"], r["tp"], r["fp"], r["fn"],
                 "" if r["delta_f1"] == "" else "%+.4f" % r["delta_f1"]))

    # ---- 贡献度排序（按剔除后 F1 的跌幅）----
    print("\n[ablation] 各规则 F1 贡献（剔除后 F1 跌幅，越大越关键）:")
    contrib = sorted(((r["setting"][5:], base["f1"] - r["f1"]) for _, r in df.iterrows()
                      if r["setting"].startswith("drop_")),
                     key=lambda x: -x[1])
    for rn, d in contrib:
        print("  %-3s ΔF1 = %+.4f" % (rn, d))

    print("\n[ablation] 权重 %s | 阈值 %d | 埋 %d 篇" %
          ({short(k): v for k, v in weights.items()}, threshold, len(gt_corrupt)))
    print("[ablation] 风险分分布: %s" % dict(Counter(corr["risk_score"]).most_common()))
    print("[ablation] 已写出 corrupt_rule_ablation.csv (%d 行)" % len(df))
    print("=" * 74)


if __name__ == "__main__":
    main()