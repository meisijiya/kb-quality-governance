"""校验原型 data.js 的每个取值都能在 poc/kbgovernance/ 的产物里逐条对上。

纪律：原型页面上的每个数字都必须来自机读产物（见 AGENTS.md「数字纪律」）。
本脚本只读，不修改任何文件；退出码 0 表示全部对得上。

用法（仓库根目录）：
    python system/prototype/check_prototype.py
"""
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
POC = os.path.join(REPO, "poc", "kbgovernance")

FORBIDDEN_FIELDS = (
    "is_true_gap",
    "is_true_group",
    "in_control_sample",
    "is_dup_copy",
    "dup_source",
    "fp_reason",
    "rep_cover",
)

errors = []


def fail(msg):
    errors.append(msg)


def read_csv(name):
    with open(os.path.join(POC, name), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_data_js():
    path = os.path.join(HERE, "data.js")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"const KB = (\{.*?\});\s*\n\s*window\.KB = KB;", text, re.S)
    if not m:
        fail("data.js 里找不到 `const KB = {...}` 结构")
        return {}, text
    return json.loads(m.group(1)), text


def num(a, b):
    """浮点比较：容差 1e-9，规避 CSV 文本与 JSON 数值的表示差异。"""
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


def main():
    kb, text = load_data_js()
    if errors:
        print_report()
        return 1

    # ---- 1. 知识缺口：只取 cover_median < 0.62 的命中行，值须逐条等于 top15_gaps.csv
    gaps_src = [r for r in read_csv("top15_gaps.csv") if float(r["cover_median"]) < 0.62]
    gaps = kb.get("gaps", [])
    if len(gaps) != len(gaps_src):
        fail(f"缺口行数不符：原型 {len(gaps)} 行，产物命中 {len(gaps_src)} 行")
    src_by_rank = {int(r["rank"]): r for r in gaps_src}
    for row in gaps:
        r = src_by_rank.get(int(row["rank"]))
        if r is None:
            fail(f"缺口 rank={row['rank']} 在产物的命中行里不存在")
            continue
        for key in ("intent", "size", "cover_median", "rep_ticket", "rep_text"):
            if key not in row:
                fail(f"缺口 rank={row['rank']} 缺字段 {key}")
                continue
            if key in ("size", "cover_median"):
                if not num(row[key], r[key]):
                    fail(f"缺口 rank={row['rank']} 的 {key}={row[key]} 与产物 {r[key]} 不一致")
            elif row[key] != r[key]:
                fail(f"缺口 rank={row['rank']} 的 {key} 与产物不一致")

    # ---- 2. 内容腐化：原型取 risk_score >= 3 的代表行，每行须在 corrupt_docs.csv 中存在且一致
    corrupt_src = {r["doc_id"]: r for r in read_csv("corrupt_docs.csv")}
    corrupt = kb.get("corrupt", [])
    for row in corrupt:
        src = corrupt_src.get(row["doc_id"])
        if src is None:
            fail(f"腐化 {row['doc_id']} 在 corrupt_docs.csv 里不存在")
            continue
        if int(row["risk_score"]) < 3:
            fail(f"腐化 {row['doc_id']} 的 risk_score={row['risk_score']} 未达判定阈值 3")
        if not num(row["risk_score"], src["risk_score"]):
            fail(f"腐化 {row['doc_id']} 的 risk_score 与产物不一致")
        for key in ("title", "category", "last_modified", "rule_hits", "reasons"):
            if row.get(key) != src.get(key):
                fail(f"腐化 {row['doc_id']} 的 {key} 与产物不一致")

    # ---- 3. 重复冗余：全部 22 组，每组须与 dup_groups_best.csv 一致
    dup_src = {int(r["group"]): r for r in read_csv("dup_groups_best.csv")}
    dups = kb.get("dups", [])
    if len(dups) != len(dup_src):
        fail(f"重复组数不符：原型 {len(dups)} 组，产物 {len(dup_src)} 组")
    for row in dups:
        src = dup_src.get(int(row["group"]))
        if src is None:
            fail(f"重复组 group={row['group']} 在产物里不存在")
            continue
        if int(row["size"]) != int(src["size"]):
            fail(f"重复组 {row['group']} 的 size 与产物不一致")
        if not num(row["max_sim"], src["max_sim"]):
            fail(f"重复组 {row['group']} 的 max_sim 与产物不一致")
        for key in ("primary_doc", "member_docs"):
            if row.get(key) != src.get(key):
                fail(f"重复组 {row['group']} 的 {key} 与产物不一致")

    # ---- 4. 指标区：逐键对齐 metrics.json
    with open(os.path.join(POC, "metrics.json"), encoding="utf-8") as f:
        m = json.load(f)
    mm = kb.get("metrics", {})
    pairs = [
        ("n_docs", mm.get("n_docs"), m["embedding"]["n_docs"]),
        ("n_tickets", mm.get("n_tickets"), m["embedding"]["n_tickets"]),
        ("n_passages", mm.get("n_passages"), m["embedding"]["n_passages"]),
        ("encode_seconds", mm.get("encode_seconds"), m["embedding"]["encode_seconds"]),
        ("total_seconds", mm.get("total_seconds"), m["total_seconds"]),
        ("gap.threshold", mm.get("gap", {}).get("threshold"), m["gap"]["best"]["threshold"]),
        ("gap.gap_clusters", mm.get("gap", {}).get("gap_clusters"), m["gap"]["best"]["gap_clusters"]),
        ("gap.detected_intents", mm.get("gap", {}).get("detected_intents"), m["gap"]["best"]["detected_intents"]),
        ("gap.precision", mm.get("gap", {}).get("precision"), m["gap"]["best"]["precision"]),
        ("gap.recall", mm.get("gap", {}).get("recall"), m["gap"]["best"]["recall"]),
        ("gap.f1", mm.get("gap", {}).get("f1"), m["gap"]["best"]["f1"]),
        ("gap.min_cluster_size", mm.get("gap", {}).get("min_cluster_size"), m["gap"]["best"]["min_cluster_size"]),
        ("gap.n_clusters", mm.get("gap", {}).get("n_clusters"), m["gap"]["clusters"]["5"]["n_clusters"]),
        ("gap.n_noise", mm.get("gap", {}).get("n_noise"), m["gap"]["clusters"]["5"]["n_noise"]),
        ("corrupt.threshold", mm.get("corrupt", {}).get("threshold"), m["corrupt"]["score_threshold"]),
        ("corrupt.detected", mm.get("corrupt", {}).get("detected"), m["corrupt"]["detected"]),
        ("corrupt.embedded", mm.get("corrupt", {}).get("embedded"), m["corrupt"]["embedded"]),
        ("corrupt.tp", mm.get("corrupt", {}).get("tp"), m["corrupt"]["tp"]),
        ("corrupt.fp", mm.get("corrupt", {}).get("fp"), m["corrupt"]["fp"]),
        ("corrupt.fn", mm.get("corrupt", {}).get("fn"), m["corrupt"]["fn"]),
        ("corrupt.fp_from_control", mm.get("corrupt", {}).get("fp_from_control"), m["corrupt"]["fp_from_control"]),
        ("corrupt.fp_from_dup_inherit", mm.get("corrupt", {}).get("fp_from_dup_inherit"), m["corrupt"]["fp_from_dup_inherit"]),
        ("corrupt.fp_other", mm.get("corrupt", {}).get("fp_other"), m["corrupt"]["fp_other"]),
        ("corrupt.precision", mm.get("corrupt", {}).get("precision"), m["corrupt"]["precision"]),
        ("corrupt.recall", mm.get("corrupt", {}).get("recall"), m["corrupt"]["recall"]),
        ("corrupt.f1", mm.get("corrupt", {}).get("f1"), m["corrupt"]["f1"]),
        ("corrupt.seconds", mm.get("corrupt", {}).get("seconds"), m["corrupt"]["seconds"]),
        ("dup.threshold", mm.get("dup", {}).get("threshold"), m["dup"]["best"]["threshold"]),
        ("dup.dup_groups", mm.get("dup", {}).get("dup_groups"), m["dup"]["best"]["dup_groups"]),
        ("dup.detected_docs", mm.get("dup", {}).get("detected_docs"), m["dup"]["best"]["detected_docs"]),
        ("dup.group_precision", mm.get("dup", {}).get("group_precision"), m["dup"]["best"]["group_precision"]),
        ("dup.group_recall", mm.get("dup", {}).get("group_recall"), m["dup"]["best"]["group_recall"]),
        ("dup.group_f1", mm.get("dup", {}).get("group_f1"), m["dup"]["best"]["group_f1"]),
        ("dup.seconds", mm.get("dup", {}).get("seconds"), m["dup"]["best"]["seconds"]),
    ]
    for name, got, want in pairs:
        if got is None or want is None:
            fail(f"指标 {name} 缺失（原型={got}，产物={want}）")
        elif not num(got, want):
            fail(f"指标 {name}：原型 {got} 与产物 {want} 不一致")
    # 产物里规则键是全名（R1_正文过期日期），原型里用短名（R1）——按前缀配对
    for full_key, rv in m["corrupt"]["rule_weight"].items():
        short = full_key.split("_", 1)[0]
        if not num(mm.get("corrupt", {}).get("rule_weight", {}).get(short), rv):
            fail(f"腐化规则权重 {short}（产物 {full_key}）与产物不一致")
    for full_key, rv in m["corrupt"]["rule_hit_counts"].items():
        short = full_key.split("_", 1)[0]
        if not num(mm.get("corrupt", {}).get("rule_hit_counts", {}).get(short), rv):
            fail(f"腐化规则命中数 {short}（产物 {full_key}）与产物不一致")
    for sk, sv in m["corrupt"]["score_hist"].items():
        if not num(mm.get("corrupt", {}).get("score_hist", {}).get(sk), sv):
            fail(f"腐化风险分分布 {sk} 与产物不一致")

    # ---- 5. audit 段：评审要求补充披露的口径数字，同样逐条对产物
    audit = kb.get("audit", {})
    if not audit:
        fail("data.js 缺少 audit 段（评审要求补充披露的阈值敏感性、抽样规则等口径数字）")
    else:
        with open(os.path.join(POC, "repro_check.json"), encoding="utf-8") as f:
            repro = json.load(f)
        if audit.get("run", {}).get("generated_at") != repro.get("generated_at"):
            fail(f"audit.run.generated_at={audit.get('run', {}).get('generated_at')} 与 repro_check.json 不一致")

        top15 = read_csv("top15_gaps.csv")
        pool = audit.get("gap_pool", {})
        if not num(pool.get("clusters"), len(top15)):
            fail(f"audit.gap_pool.clusters={pool.get('clusters')} 与 top15_gaps.csv 行数 {len(top15)} 不一致")
        distinct = len({r["intent"] for r in top15})
        if not num(pool.get("intents"), distinct):
            fail(f"audit.gap_pool.intents={pool.get('intents')} 与 top15_gaps.csv 去重业务意图数 {distinct} 不一致")
        if not num(pool.get("shown_clusters"), mm.get("gap", {}).get("gap_clusters")):
            fail("audit.gap_pool.shown_clusters 与 metrics.gap.gap_clusters 不一致")
        if not num(pool.get("shown_intents"), mm.get("gap", {}).get("detected_intents")):
            fail("audit.gap_pool.shown_intents 与 metrics.gap.detected_intents 不一致")

        gap_thr = {float(r["threshold"]): r for r in read_csv("gap_threshold.csv") if int(r["min_cluster_size"]) == 5}
        for row in audit.get("gap_threshold_scan", []):
            src = gap_thr.get(float(row["threshold"]))
            if src is None:
                fail(f"audit.gap_threshold_scan 的阈值 {row['threshold']} 在 gap_threshold.csv 里不存在")
                continue
            for key in ("gap_clusters", "detected_intents", "precision", "recall", "f1"):
                if not num(row.get(key), src[key]):
                    fail(f"audit.gap_threshold_scan 阈值 {row['threshold']} 的 {key} 与 gap_threshold.csv 不一致")

        near_src = [r for r in top15 if float(r["cover_median"]) >= 0.62]
        near = audit.get("gap_near_miss", [])
        if len(near) != len(near_src):
            fail(f"audit.gap_near_miss 行数 {len(near)} 与 top15_gaps.csv 中 cover_median>=0.62 的 {len(near_src)} 行不符")
        for i, row in enumerate(near):
            if i >= len(near_src):
                break
            src = near_src[i]
            if row.get("intent") != src["intent"]:
                fail(f"audit.gap_near_miss 第 {i + 1} 行的业务意图与 top15_gaps.csv 不一致")
            if not num(row.get("size"), src["size"]):
                fail(f"audit.gap_near_miss 第 {i + 1} 行的 size 与 top15_gaps.csv 不一致")
            if not num(row.get("cover_median"), src["cover_median"]):
                fail(f"audit.gap_near_miss 第 {i + 1} 行的 cover_median 与 top15_gaps.csv 不一致")

        dup_thr = {float(r["threshold"]): r for r in read_csv("dup_threshold.csv")}
        for row in audit.get("dup_threshold_scan", []):
            src = dup_thr.get(float(row["threshold"]))
            if src is None:
                fail(f"audit.dup_threshold_scan 的阈值 {row['threshold']} 在 dup_threshold.csv 里不存在")
                continue
            for key in ("dup_groups", "detected_docs", "group_f1", "doc_f1"):
                if not num(row.get(key), src[key]):
                    fail(f"audit.dup_threshold_scan 阈值 {row['threshold']} 的 {key} 与 dup_threshold.csv 不一致")

        with open(os.path.join(POC, "standardize", "scenario_meta.json"), encoding="utf-8") as f:
            scenario = json.load(f)
        alpha = scenario.get("cover_stats", {}).get("alpha", {})
        for key in ("min", "mean", "max", "sd"):
            if not num(audit.get("cover_stats", {}).get(key), alpha.get(key)):
                fail(f"audit.cover_stats.{key} 与 standardize/scenario_meta.json 不一致")

        combos = {}
        for r in read_csv("corrupt_docs.csv"):
            if int(r["risk_score"]) < 3:
                continue
            codes = "+".join(sorted(part.split("_", 1)[0] for part in r["rule_hits"].split("|")))
            combos[codes] = combos.get(codes, 0) + 1
        for row in audit.get("corrupt_rule_combos", []):
            if not num(row.get("docs"), combos.get(row.get("rules"))):
                fail(f"audit.corrupt_rule_combos 的 {row.get('rules')} 篇数与 corrupt_docs.csv 不一致")
        if len(audit.get("corrupt_rule_combos", [])) != len(combos):
            fail("audit.corrupt_rule_combos 的组合数与 corrupt_docs.csv 不一致")

        sample = audit.get("corrupt_sample", {})
        if not num(sample.get("total"), mm.get("corrupt", {}).get("detected")):
            fail("audit.corrupt_sample.total 与 metrics.corrupt.detected 不一致")
        if not num(sample.get("shown"), len(corrupt)):
            fail("audit.corrupt_sample.shown 与原型腐化代表行数不一致")
        if not num(sample.get("combos"), len(audit.get("corrupt_rule_combos", []))):
            fail("audit.corrupt_sample.combos 与规则命中组合数不一致")

        for key, item in audit.get("products", {}).items():
            path = os.path.join(REPO, item.get("path", "").replace("/", os.sep))
            if not os.path.exists(path):
                fail(f"audit.products.{key} 指向的产物 {item.get('path')} 不存在")

    # ---- 6. 红线：数据字段与页面文本都不得出现评测依据列/归因列
    for name in ("index.html", "app.js", "data.js", "styles.css", "copy.js"):
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            body = f.read()
        for field in FORBIDDEN_FIELDS:
            if field in body:
                fail(f"{name} 出现禁透出字段 {field}")

    variants = os.path.join(HERE, "variants")
    if os.path.isdir(variants):
        for name in sorted(os.listdir(variants)):
            if not name.endswith(".html"):
                continue
            with open(os.path.join(variants, name), encoding="utf-8") as f:
                body = f.read()
            for field in FORBIDDEN_FIELDS:
                if field in body:
                    fail(f"variants/{name} 出现禁透出字段 {field}")

    print_report()
    return 1 if errors else 0


def print_report():
    if errors:
        print("[check_prototype] 不通过：")
        for e in errors:
            print("  -", e)
        print(f"[check_prototype] 共 {len(errors)} 处不一致")
    else:
        print("[check_prototype] 通过：原型 data.js 的每个取值都能在 poc/kbgovernance/ 产物里对上；"
              "未出现禁透出字段")


if __name__ == "__main__":
    sys.exit(main())
