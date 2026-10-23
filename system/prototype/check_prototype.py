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

    # ---- 5. 红线：数据字段与页面文本都不得出现评测依据列/归因列
    for name in ("index.html", "app.js", "data.js", "styles.css"):
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            body = f.read()
        for field in FORBIDDEN_FIELDS:
            if field in body:
                fail(f"{name} 出现禁透出字段 {field}")

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
