"""校验原型 data.js 的每个取值都能在 poc/kbgovernance/ 的产物里逐条对上。

纪律：原型页面上的每个数字都必须来自机读产物（见 AGENTS.md「数字纪律」）。
本脚本只读，不修改任何文件；退出码 0 表示全部对得上。

口径要点：
- 知识缺口的判定单元是业务意图，主清单为 gap_intents_best.csv；
  gap_clusters_best.csv 是簇级明细，只作内部量与溯源。
- 内容腐化分「内容过期」与「维护周期」两个口径，各自报 P/R/F1，
  不合成单一 F1；合计只作覆盖面说明。

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

# 已作废的联合口径键，data.js 里不得再出现
RETIRED_KEYS = (
    "fp_from_control",
    "fp_from_dup_inherit",
    "fp_other",
)

GAP_ROW_FIELDS = ("intent", "n_clusters", "min_cover_median", "total_tickets", "rep_ticket", "rep_text")
CORRUPT_ROW_FIELDS = (
    "doc_id",
    "title",
    "category",
    "last_modified",
    "risk_score",
    "rule_hits",
    "reasons",
    "cause_score_content_expiry",
    "cause_score_maintenance",
)
CAUSES = ("content_expiry", "maintenance")

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


def check_row_fields(row, allowed, label):
    """行内只允许出现约定的字段，评测依据列与归因列不得混入。"""
    extra = [k for k in row if k not in allowed]
    if extra:
        fail(f"{label} 出现约定外字段 {extra}")
    missing = [k for k in allowed if k not in row]
    if missing:
        fail(f"{label} 缺少字段 {missing}")


def check_gaps(kb):
    """第 1 节：知识缺口按业务意图判定，逐条对 gap_intents_best.csv。"""
    src_rows = read_csv("gap_intents_best.csv")
    gaps = kb.get("gaps", [])
    if len(gaps) != len(src_rows):
        fail(f"缺口行数不符：原型 {len(gaps)} 行，产物 {len(src_rows)} 行")
    for i, row in enumerate(gaps):
        check_row_fields(row, GAP_ROW_FIELDS, f"缺口第 {i + 1} 行")
        if i >= len(src_rows):
            break
        src = src_rows[i]
        if row.get("intent") != src["intent"]:
            fail(f"缺口第 {i + 1} 行的业务意图与 gap_intents_best.csv 不一致")
        for key in ("n_clusters", "min_cover_median", "total_tickets"):
            if not num(row.get(key), src[key]):
                fail(f"缺口第 {i + 1} 行的 {key}={row.get(key)} 与 gap_intents_best.csv 的 {src[key]} 不一致")
        for key in ("rep_ticket", "rep_text"):
            if row.get(key) != src[key]:
                fail(f"缺口第 {i + 1} 行的 {key} 与 gap_intents_best.csv 不一致")


def check_corrupt(kb):
    """第 2 节：内容腐化代表行须在 corrupt_docs.csv 中存在且一致。"""
    corrupt_src = {r["doc_id"]: r for r in read_csv("corrupt_docs.csv")}
    corrupt = kb.get("corrupt", [])
    for i, row in enumerate(corrupt):
        check_row_fields(row, CORRUPT_ROW_FIELDS, f"腐化第 {i + 1} 行")
        src = corrupt_src.get(row.get("doc_id"))
        if src is None:
            fail(f"腐化 {row.get('doc_id')} 在 corrupt_docs.csv 里不存在")
            continue
        if int(row["risk_score"]) < 3:
            fail(f"腐化 {row['doc_id']} 的 risk_score={row['risk_score']} 未达判定阈值 3")
        if not num(row["risk_score"], src["risk_score"]):
            fail(f"腐化 {row['doc_id']} 的 risk_score 与产物不一致")
        for key in ("title", "category", "last_modified", "rule_hits", "reasons"):
            if row.get(key) != src.get(key):
                fail(f"腐化 {row['doc_id']} 的 {key} 与产物不一致")
        for key in ("cause_score_content_expiry", "cause_score_maintenance"):
            if not num(row.get(key), src.get(key)):
                fail(f"腐化 {row['doc_id']} 的 {key}={row.get(key)} 与产物 {src.get(key)} 不一致")
        total = int(row["cause_score_content_expiry"]) + int(row["cause_score_maintenance"])
        if total != int(row["risk_score"]):
            fail(f"腐化 {row['doc_id']} 的两口径分数之和 {total} 与 risk_score {row['risk_score']} 不一致")


def check_dups(kb):
    """第 3 节：重复冗余全部 22 组，每组须与 dup_groups_best.csv 一致。"""
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


def check_metrics(kb):
    """第 4 节：指标区逐键对齐 metrics.json，腐化按两个口径分别核对。"""
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
        ("gap.n_gap_intents", mm.get("gap", {}).get("n_gap_intents"), m["gap"]["n_gap_intents"]),
        ("corrupt.threshold", mm.get("corrupt", {}).get("threshold"), m["corrupt"]["score_threshold"]),
        ("corrupt.detected", mm.get("corrupt", {}).get("detected"), m["corrupt"]["detected"]),
        ("corrupt.embedded", mm.get("corrupt", {}).get("embedded"), m["corrupt"]["embedded"]),
        ("corrupt.covered", mm.get("corrupt", {}).get("covered"), m["corrupt"]["covered"]),
        ("corrupt.fp", mm.get("corrupt", {}).get("fp"), m["corrupt"]["fp"]),
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

    if mm.get("gap", {}).get("gap_intents") != m["gap"]["gap_intents"]:
        fail("metrics.gap.gap_intents 与产物不一致")

    # 腐化：顶层只保留覆盖面口径，不再有联合 P/R/F1
    for retired in ("tp", "fn", "precision", "recall", "f1"):
        if retired in mm.get("corrupt", {}):
            fail(f"metrics.corrupt 仍含作废的联合口径键 {retired}")
    for retired in RETIRED_KEYS:
        if retired in mm.get("corrupt", {}) or retired in mm.get("gap", {}):
            fail(f"metrics 仍含作废键 {retired}")

    # 腐化：两个口径各自与产物同源核对
    proto_causes = mm.get("corrupt", {}).get("by_cause", {})
    if set(proto_causes) != set(CAUSES):
        fail(f"metrics.corrupt.by_cause 的口径集合 {sorted(proto_causes)} 与预期 {list(CAUSES)} 不一致")
    for cause in CAUSES:
        got = proto_causes.get(cause, {})
        want = m["corrupt"]["by_cause"].get(cause, {})
        if got.get("label") != want.get("label"):
            fail(f"by_cause.{cause}.label={got.get('label')} 与产物 {want.get('label')} 不一致")
        if got.get("rules") != want.get("rules"):
            fail(f"by_cause.{cause}.rules 与产物不一致")
        cause_pairs = [
            ("threshold", got.get("threshold"), want.get("threshold")),
            ("planted", got.get("planted"), want.get("planted_of_this_nature")),
            ("truth", got.get("truth"), len(want.get("truth_doc_ids", []))),
            ("detected", got.get("detected"), want.get("detected")),
            ("tp", got.get("tp"), want.get("tp")),
            ("fp", got.get("fp"), want.get("fp")),
            ("fn", got.get("fn"), want.get("fn")),
            ("precision", got.get("precision"), want.get("precision")),
            ("recall", got.get("recall"), want.get("recall")),
            ("f1", got.get("f1"), want.get("f1")),
        ]
        for key, g, w in cause_pairs:
            if g is None or w is None:
                fail(f"by_cause.{cause}.{key} 缺失（原型={g}，产物={w}）")
            elif not num(g, w):
                fail(f"by_cause.{cause}.{key}：原型 {g} 与产物 {w} 不一致")
        if got.get("fp_attribution") != want.get("fp_attribution"):
            fail(f"by_cause.{cause}.fp_attribution 与产物不一致")

    # 规则权重、规则命中数与风险分分布：键名与产物一致，逐键核对
    for block in ("rule_weight", "rule_hit_counts"):
        proto_block = mm.get("corrupt", {}).get(block, {})
        want_block = m["corrupt"][block]
        if set(proto_block) != set(want_block):
            fail(f"metrics.corrupt.{block} 的键与产物不一致")
        for key, val in want_block.items():
            if not num(proto_block.get(key), val):
                fail(f"metrics.corrupt.{block}.{key}={proto_block.get(key)} 与产物 {val} 不一致")
    for sk, sv in m["corrupt"]["score_hist"].items():
        if not num(mm.get("corrupt", {}).get("score_hist", {}).get(sk), sv):
            fail(f"腐化风险分分布 {sk} 与产物不一致")


def check_audit(kb):
    """第 5 节：audit 段是评审要求补充披露的口径数字，同样逐条对产物。"""
    audit = kb.get("audit", {})
    if not audit:
        fail("data.js 缺少 audit 段（评审要求补充披露的阈值敏感性、抽样规则等口径数字）")
        return
    with open(os.path.join(POC, "repro_check.json"), encoding="utf-8") as f:
        repro = json.load(f)
    # 对账用内容指纹而不是时间戳：repro_check.json 每次重跑都会刷新 generated_at，
    # 拿时间戳对账等于「每次重跑必然失败」。指纹绑的是产物内容，内容变才失败。
    import hashlib as _hl
    _bd = repro.get("byte_deterministic", {})
    _blob = "\n".join(f"{k}={_bd[k]}" for k in sorted(_bd)).encode("utf-8")
    _fp = _hl.sha256(_blob).hexdigest()[:16]
    if audit.get("run", {}).get("artifacts_fingerprint") != _fp:
        fail(f"audit.run.artifacts_fingerprint={audit.get('run', {}).get('artifacts_fingerprint')} "
             f"与产物内容指纹 {_fp} 不一致（产物内容已变，原型数据需重新生成）")

    clusters = read_csv("gap_clusters_best.csv")
    intents = read_csv("gap_intents_best.csv")
    pool = audit.get("gap_pool", {})
    if not num(pool.get("clusters"), len(clusters)):
        fail(f"audit.gap_pool.clusters={pool.get('clusters')} 与 gap_clusters_best.csv 行数 {len(clusters)} 不一致")
    distinct = len({r["intent"] for r in clusters})
    if not num(pool.get("intents"), distinct):
        fail(f"audit.gap_pool.intents={pool.get('intents')} 与 gap_clusters_best.csv 去重业务意图数 {distinct} 不一致")
    shown_clusters = sum(1 for r in clusters if r["is_gap"] == "1")
    if not num(pool.get("shown_clusters"), shown_clusters):
        fail(f"audit.gap_pool.shown_clusters={pool.get('shown_clusters')} 与 gap_clusters_best.csv 中 is_gap=1 的 {shown_clusters} 行不一致")
    if not num(pool.get("shown_intents"), len(intents)):
        fail(f"audit.gap_pool.shown_intents={pool.get('shown_intents')} 与 gap_intents_best.csv 行数 {len(intents)} 不一致")
    if pool.get("source") != "poc/kbgovernance/gap_clusters_best.csv":
        fail(f"audit.gap_pool.source={pool.get('source')} 未指向 gap_clusters_best.csv")

    gap_thr = {float(r["threshold"]): r for r in read_csv("gap_threshold.csv") if int(r["min_cluster_size"]) == 5}
    for row in audit.get("gap_threshold_scan", []):
        src = gap_thr.get(float(row["threshold"]))
        if src is None:
            fail(f"audit.gap_threshold_scan 的阈值 {row['threshold']} 在 gap_threshold.csv 里不存在")
            continue
        for key in ("gap_clusters", "detected_intents", "precision", "recall", "f1"):
            if not num(row.get(key), src[key]):
                fail(f"audit.gap_threshold_scan 阈值 {row['threshold']} 的 {key} 与 gap_threshold.csv 不一致")

    near_src = [r for r in clusters if float(r["cover_median"]) >= 0.62]
    near = audit.get("gap_near_miss", [])
    # 页面只列最接近阈值的 10 个；候选总数另行记录，两者都要对上产物
    near_top = near_src[:10]
    if len(near) != len(near_top):
        fail(f"audit.gap_near_miss 行数 {len(near)} 应为最接近阈值的 {len(near_top)} 个")
    if not num(audit.get("gap_near_miss_total"), len(near_src)):
        fail(f"audit.gap_near_miss_total={audit.get('gap_near_miss_total')} 应为候选总数 {len(near_src)}")
    for i, row in enumerate(near):
        if i >= len(near_top):
            break
        src = near_top[i]
        if not num(row.get("cluster_id"), src["cluster_id"]):
            fail(f"audit.gap_near_miss 第 {i + 1} 行的簇号与 gap_clusters_best.csv 不一致")
        if row.get("intent") != src["intent"]:
            fail(f"audit.gap_near_miss 第 {i + 1} 行的业务意图与 gap_clusters_best.csv 不一致")
        if not num(row.get("size"), src["size"]):
            fail(f"audit.gap_near_miss 第 {i + 1} 行的 size 与 gap_clusters_best.csv 不一致")
        if not num(row.get("cover_median"), src["cover_median"]):
            fail(f"audit.gap_near_miss 第 {i + 1} 行的 cover_median 与 gap_clusters_best.csv 不一致")

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
    if not num(sample.get("total"), kb.get("metrics", {}).get("corrupt", {}).get("detected")):
        fail("audit.corrupt_sample.total 与 metrics.corrupt.detected 不一致")
    if not num(sample.get("shown"), len(kb.get("corrupt", []))):
        fail("audit.corrupt_sample.shown 与原型腐化代表行数不一致")
    if not num(sample.get("combos"), len(audit.get("corrupt_rule_combos", []))):
        fail("audit.corrupt_sample.combos 与规则命中组合数不一致")

    products = audit.get("products", {})
    for key, item in products.items():
        path = os.path.join(REPO, item.get("path", "").replace("/", os.sep))
        if not os.path.exists(path):
            fail(f"audit.products.{key} 指向的产物 {item.get('path')} 不存在")
    expected_products = {
        "gap": "poc/kbgovernance/gap_intents_best.csv",
        "gap_clusters": "poc/kbgovernance/gap_clusters_best.csv",
    }
    for key, path in expected_products.items():
        if products.get(key, {}).get("path") != path:
            fail(f"audit.products.{key}.path={products.get(key, {}).get('path')} 应为 {path}")


def check_copy_keys():
    """第 7 节：页面引用的每个 data-copy 键都必须存在于 copy.js 三变体，且三变体键集一致。

    少一个键的后果是页面上留下一段运行时永远不会被替换的静态文本（看起来像文案，
    实际是死键），所以这条要在长期脚本里守住，不能靠一次人工比对。
    """
    import re as _re

    copy_path = os.path.join(HERE, "copy.js")
    if not os.path.exists(copy_path):
        fail("缺少 copy.js")
        return
    with open(copy_path, encoding="utf-8") as f:
        copy_src = f.read()
    blocks = _re.findall(r"^  (v\d): \{", copy_src, _re.M)
    if not blocks:
        fail("copy.js 里找不到变体块（形如 '  v1: {'）")
        return
    key_sets = {}
    for name in blocks:
        body = copy_src.split(f"  {name}: {{", 1)[1]
        key_sets[name] = set(_re.findall(r'"([A-Za-z0-9_.]+)":', body))
    ref = list(key_sets.values())[0]
    for name, keys in key_sets.items():
        if keys != ref:
            fail(f"copy.js 变体 {name} 的键集与其它变体不一致："
                 f"仅 {name} 有 {sorted(keys - ref)}；缺 {sorted(ref - keys)}")

    htmls = ["index.html"] + [
        os.path.join("variants", n) for n in sorted(os.listdir(os.path.join(HERE, "variants")))
        if n.endswith(".html")
    ] if os.path.isdir(os.path.join(HERE, "variants")) else ["index.html"]
    for rel in htmls:
        path = os.path.join(HERE, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            html = f.read()
        used = set(_re.findall(r'data-copy="([^"]+)"', html))
        missing = sorted(used - ref)
        if missing:
            fail(f"{rel} 引用了 copy.js 里不存在的键：{missing}")


def check_redline():
    """第 6 节：数据字段与页面文本都不得出现评测依据列/归因列。"""
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


def main():
    kb, _ = load_data_js()
    if errors:
        print_report()
        return 1

    check_gaps(kb)
    check_corrupt(kb)
    check_dups(kb)
    check_metrics(kb)
    check_audit(kb)
    check_redline()
    check_copy_keys()

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
