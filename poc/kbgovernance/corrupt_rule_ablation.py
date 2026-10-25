# -*- coding: utf-8 -*-
"""
corrupt_rule_ablation.py -- 内容腐化两类口径的规则贡献度消融（可复算版）

回答: 每一类缺陷口径下，它所依赖的规则各自贡献多少？去掉一条会怎样？

口径与 detect.py 完全一致, 保证数字可比:
  * 两类缺陷语义不同, 各自单独评估, 不合成单一 F1:
      内容过期（规则集 R1 + R3）与 维护周期（规则集 R2 + R4）
  * 每类口径独立打分: 规则子集内加权分 >= 阈值即该类缺陷成立
  * 权重与阈值一律从 metrics.json:corrupt 读取, 不在本文件里硬编码第二份
  * 真值集固定取 metrics.json:corrupt.by_cause[cause].truth_doc_ids
    （该集合 = 被生成器埋设且在本口径下属实的文档, 消融时不变——
     真值是 ground truth, 不能随被测规则一起变, 否则精确率无从比较）

每类口径两类设置:
  all       该口径的全部规则（等价于 detect.py 的主结果, 必须逐位复现 P/R/F1）
  drop_Rn   屏蔽第 n 条规则后重算（leave-one-rule-out）
  only_Rn   只用第 n 条规则（单规则可分性）

产出:
  corrupt_rule_ablation_content_expiry.csv   内容过期口径消融
  corrupt_rule_ablation_maintenance.csv       维护周期口径消融
  两表列相同: cause / setting / precision / recall / f1 / detected /
              tp / fp / fn / truth / docs_with_hit / mean_risk / delta_f1

运行: python corrupt_rule_ablation.py   (纯规则+查表, 无随机性)
"""
import json
import os
import sys
from collections import Counter

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))

# 口径 -> 规则短名。规则名与权重一律从 metrics.json 取, 这里只声明归属关系。
CAUSE_RULES = {
    "content_expiry": ("R1", "R3"),
    "maintenance": ("R2", "R4"),
}
OUT_CSV = {
    cause: os.path.join(HERE, "corrupt_rule_ablation_%s.csv" % cause)
    for cause in CAUSE_RULES
}


# ============================================================ 工具
def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def short(tag):
    """R1_正文过期日期 -> R1，便于列名。"""
    return tag.split("_", 1)[0]


def evaluate(scores, threshold, truth, active):
    """active: 参与打分的规则短名集合。返回指标 dict。"""
    s = pd.Series(scores, index=truth_index(scores))
    det = set(s.index[s >= threshold])
    tp = len(det & truth)
    fp, fn = len(det) - tp, len(truth) - tp
    p, r, f = prf(tp, fp, fn)
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4),
            "detected": len(det), "tp": tp, "fp": fp, "fn": fn,
            "docs_with_hit": int(sum(1 for x in s if x > 0)),
            "mean_risk": round(float(s.mean()), 4)}


def truth_index(scores):
    return scores.index


# ============================================================ main
def main():
    metrics = json.load(open(os.path.join(HERE, "metrics.json"), encoding="utf-8"))
    corr = pd.read_csv(os.path.join(HERE, "corrupt_docs.csv"), encoding="utf-8-sig")

    weights = metrics["corrupt"]["rule_weight"]
    threshold = int(metrics["corrupt"]["score_threshold"])
    ref = metrics["corrupt"]["by_cause"]

    # rule_hits 是 "R1_..|R3_.." 字符串; 空值在 pandas 里是 NaN, 统一成空元组
    corr["_hits"] = [tuple(h for h in str(s).split("|") if h and h != "nan")
                     for s in corr["rule_hits"].fillna("")]
    corr = corr.set_index("doc_id")

    print("=" * 74)
    print("[ablation] 文档 %d 篇 / 判定阈值 risk_score >= %d"
          % (len(corr), threshold))
    print("[ablation] 规则权重（自 metrics.json 读取）: %s"
          % {short(k): v for k, v in weights.items()})

    # ---- 口径自检 1: risk_score 必须能被 rule_hits × 权重完全重算 ----
    recomputed = [sum(weights[h] for h in hs) for hs in corr["_hits"]]
    bad = int((pd.Series(recomputed, index=corr.index) != corr["risk_score"]).sum())
    print("[ablation] 口径自检 1: risk_score 由 rule_hits 重算, 不一致 %d 篇 %s"
          % (bad, "OK" if bad == 0 else "<-- 有问题"))

    # ---- 口径自检 2: 各规则命中数必须与 metrics.json 一致 ----
    counts = {short(h): int(corr["_hits"].apply(lambda hs, t=h: t in hs).sum())
              for h in weights}
    same = all(counts[short(h)] == v
               for h, v in metrics["corrupt"]["rule_hit_counts"].items())
    print("[ablation] 口径自检 2: 各规则命中数 %s vs metrics.json %s -> %s"
          % (counts, {short(k): v for k, v in
                      metrics["corrupt"]["rule_hit_counts"].items()},
             "OK" if same else "<-- 有问题"))

    ok_all = (bad == 0 and same)

    for cause, rule_names in CAUSE_RULES.items():
        spec = ref[cause]
        truth = set(spec["truth_doc_ids"])
        cause_hits = [h for h in weights if short(h) in rule_names]
        if not cause_hits:
            print("[ablation] %s: metrics.json 未给出该口径, 跳过" % cause)
            continue

        # 本口径下的加权分（只算属于本口径的规则）
        base_scores = pd.Series(
            [sum(weights[h] for h in hs if h in cause_hits)
             for hs in corr["_hits"]], index=corr.index)

        # ---- 口径自检 3: all 设置必须逐位复现 detect.py 的主结果 ----
        base = evaluate(base_scores, threshold, truth, set(rule_names))
        ok3 = (base["precision"] == spec["precision"]
               and base["recall"] == spec["recall"]
               and base["f1"] == spec["f1"]
               and base["detected"] == spec["detected"]
               and base["tp"] == spec["tp"]
               and base["fp"] == spec["fp"]
               and base["fn"] == spec["fn"])
        print("[ablation] 口径自检 3[%s]: all = P%.4f R%.4f F1%.4f vs metrics.json "
              "P%.4f R%.4f F1%.4f -> %s"
              % (cause, base["precision"], base["recall"], base["f1"],
                 spec["precision"], spec["recall"], spec["f1"],
                 "OK" if ok3 else "<-- 有问题"))
        ok_all = ok_all and ok3

        # ---- 消融 ----
        rows = [dict(cause=cause, setting="all", truth=len(truth), **base,
                     delta_f1="")]
        for rn in rule_names:
            dropped = [h for h in cause_hits if short(h) != rn]
            s = pd.Series([sum(weights[h] for h in hs if h in dropped)
                           for hs in corr["_hits"]], index=corr.index)
            rows.append(dict(cause=cause, setting="drop_%s" % rn, truth=len(truth),
                             **evaluate(s, threshold, truth, set(rule_names))))
        for rn in rule_names:
            only = [h for h in cause_hits if short(h) == rn]
            s = pd.Series([sum(weights[h] for h in hs if h in only)
                           for hs in corr["_hits"]], index=corr.index)
            rows.append(dict(cause=cause, setting="only_%s" % rn, truth=len(truth),
                             **evaluate(s, threshold, truth, set(rule_names))))

        df = pd.DataFrame(rows)
        df["delta_f1"] = [(round(r["f1"] - base["f1"], 4) if r["setting"] != "all" else "")
                          for _, r in df.iterrows()]
        cols = ["cause", "setting", "precision", "recall", "f1", "detected",
                "tp", "fp", "fn", "truth", "docs_with_hit", "mean_risk", "delta_f1"]
        df = df[cols]
        df.to_csv(OUT_CSV[cause], index=False, encoding="utf-8-sig")

        print("\n" + "-" * 74)
        print("[ablation] %s（规则 %s）真值 %d 篇"
              % (spec["label"], "+".join(rule_names), len(truth)))
        print("%-10s %9s %8s %8s %9s %4s %4s %4s %8s"
              % ("setting", "precision", "recall", "f1", "detected", "tp", "fp",
                 "fn", "Δf1"))
        for _, r in df.iterrows():
            print("%-10s %9.4f %8.4f %8.4f %9d %4d %4d %4d %8s"
                  % (r["setting"], r["precision"], r["recall"], r["f1"],
                     r["detected"], r["tp"], r["fp"], r["fn"],
                     "" if r["delta_f1"] == "" else "%+.4f" % r["delta_f1"]))
        print("[ablation] 已写出 %s（%d 行）"
              % (os.path.basename(OUT_CSV[cause]), len(df)))

    print("\n" + "=" * 74)
    if not ok_all:
        print("[ablation] 口径自检未全部通过, 消融数字与 detect.py 不可比")
    else:
        print("[ablation] 口径自检全部通过, 两表数字与 detect.py 主结果可比")
    print("[ablation] 风险分分布: %s" % dict(Counter(corr["risk_score"]).most_common()))
    print("=" * 74)


if __name__ == "__main__":
    main()
