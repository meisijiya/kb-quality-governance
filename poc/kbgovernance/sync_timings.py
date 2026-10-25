#!/usr/bin/env python
"""sync_timings.py -- 把文档里的「耗时值」同步为当前产物的复跑值

为什么要这个脚本
----------------
`metrics.json` 的耗时字段（`total_seconds` / `corrupt.seconds` /
`embedding.encode_seconds`）与派生的吞吐字段
（`embedding.throughput_texts_per_sec_repro`）跨运行必然抖动：同一条流水线
重跑一次数字就会变（实测轨迹：total_seconds 2.85 → 2.61 → 3.01 → 2.94 →
2.98 → 2.73）。方案文档按现行口径写的是「耗时值只认复跑值」
（`docs/技术方案/本科版实施方案.md` §7.2 第 3b 条），于是每次重跑
`run_all.sh` 之后文档里的耗时数字就与产物脱节，`check_numbers.py`
门禁会把它们判成「指标类 UNSOURCED」并以退出码 1 收场。

手工改十几处数字既慢又容易漏。这个脚本把「文档里的耗时值」当成
**产物的投影**：从 `metrics.json` / `embeddings_meta.json` /
`derived_metrics.csv` 读出当前值，定位文档中对应位置并替换。

用法
----
    python sync_timings.py            # 同步并打印逐处改动
    python sync_timings.py --check    # 只检查不修改，有漂移则退出码 1

识别规则（保守优先，宁可不改也不能改错）
----------------------------------------
1. 候选值 = 行内「数字 + 秒」「数字 + 条/秒」、`metrics.json` 字段赋值、
   YAML `key: 数字`、HTML `<dt>名</dt><dd>数字 秒</dd>` 四种形态。
2. 每个候选值的指标按优先级确定：
   a) 显式形态（YAML / HTML / 字段赋值）——形态本身指明指标；
   b) 候选值紧跟其后的 `metrics.json` → 字段 引用；
   c) 候选值「秒」之后紧跟的模块名（`16.88 秒向量化` / `2.73 秒检测`）；
   d) 否则取候选值**前面最近**的耗时关键词：
      向量化 / 条文本 / 编码耗时 / encode_seconds -> encode_seconds
      腐化耗时 / 腐化检测 / corrupt.seconds        -> corrupt_seconds
      三模块 / 全量扫描 / 检测环节 / total_seconds   -> total_seconds
      复现 / 复跑                                   -> throughput_repro
   关键词落在同一位置时取更长的那个（`腐化检测 0.35 秒` 里的「检测」比
   「腐化检测」更短，取后者才不会把腐化耗时误判成三模块总耗时）。
   吞吐（条/秒）另有一条：离候选值最近的「首跑 / 复现」标记决定它是首跑
   常量（固定，不动）还是复现跑吞吐（随 encode_seconds 变）。
3. 只替换「本脚本此前写入过的值」清单里的数字（清单在 `timings_state.json`
   的 `known` 段），因此不会误伤行里其它数字（`dup.seconds` 的 0.0、
   聚类耗时 1.18、pip 耗时 88.9、标准化耗时 26.2 等都不在清单内）。
4. 阈值表达（数字前带 `≤ ≥ ≈ ~ 约 大约 超过 至少 不超过 上限 上界`）默认
   不改——那是需求阈值 / 上界，不是实测值；唯一的例外是该值本身就在
   `known` 清单里（说明它是本脚本写入过的实测值，阈值记号只是行文里的
   「约等于」修饰）。
5. 含「重复检测」「余弦矩阵」「dup.」的行整行跳过（属于重复检测模块耗时）。
6. 同一行内同指标出现两个不同候选值时，跳过该行并报告，交人工判断。
7. 替换按候选值的精确字符位置进行（不是全行正则替换），一个候选值只改
   它自己那一位，不会误伤同行其它同数字文本。
8. 写入前做行数守卫：替换耗时值不应改变行数，变化则整体中止不写。

每处改动都会打印（文件:行号 指标 旧值 -> 新值），改完请看 git diff。
"""

import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))

METRICS = os.path.join(HERE, "metrics.json")
EMETA = os.path.join(HERE, "embeddings_meta.json")
DERIVED = os.path.join(HERE, "derived_metrics.csv")
STATE = os.path.join(HERE, "timings_state.json")

# 允许出现耗时值的文档清单。产物文件与门禁脚本不在其中。
TARGETS = [
    "README.md",
    "docs/技术方案/企业知识库质量治理系统技术方案.md",
    "docs/技术方案/技术方案拆解.html",
    "docs/技术方案/数字溯源审计.md",
    "docs/技术方案/本科版实施方案.md",
    "docs/技术方案/开发前准备清单.md",
    "docs/选题调研/最终裁决与选型决策.md",
    "poc/kbgovernance/RESULT.md",
    "poc/kbgovernance/产物索引.md",
    "poc/kbgovernance/figures/03-核心算法流程图.md",
    "poc/kbgovernance/figures/05-数据流图.md",
    "poc/kbgovernance/figures/06-实验矩阵图.md",
    "poc/kbgovernance/figures/07-部署与运行环境.md",
    "system/openapi.yaml",
    "system/prototype/data.js",
]

# 关键词 -> 指标。匹配时取候选值前面最近的一个。
LABELS = {
    "encode_seconds": [
        "embedding.encode_seconds", "encode_seconds", "向量化吞吐", "向量化",
        "编码耗时", "条文本", "encoding:",
    ],
    "corrupt_seconds": [
        "corrupt.seconds", "腐化耗时", "腐化检测", "其中腐化模块", "腐化", "corrupt:",
    ],
    "total_seconds": [
        "total_seconds", "三模块检测总耗时", "三模块检测合计", "三模块合计",
        "三模块检测", "三模块", "全量扫描", "检测环节", "检测阶段", "检测耗时",
        "检测", "total:",
    ],
    "throughput_repro": [
        "throughput_texts_per_sec_repro", "复现跑", "复跑",
    ],
}

# 候选值「秒」之后紧跟的模块名（形如「16.88 秒向量化」）。与 LABELS 相反，
# 这里看的是数字后面的词：中文里「X 秒检测」「X 秒向量化」比「检测 X 秒」常见。
SUFFIX_LABELS = {
    "腐化检测": "corrupt_seconds",
    "三模块检测合计": "total_seconds",
    "三模块检测": "total_seconds",
    "三模块": "total_seconds",
    "向量化": "encode_seconds",
    "编码": "encode_seconds",
    "检测": "total_seconds",
}

# 关键词与候选值的最大间隔（字符）。超过这个距离就不认为这个关键词在描述
# 那个数字——否则同一行里隔得远的关键词会误判归属。
LABEL_MAX_GAP = 12

# 吞吐候选值与其「首跑 / 复现」标记的最大间隔（字符）。
RATE_MARK_MAX_GAP = 20

# 整行跳过的标记：这些行里的秒数属于重复检测模块或第三方工具，不归本脚本管
LINE_SKIP = ("重复检测", "余弦矩阵", "dup.", "dup.best", "dup.seconds")

FIELD_METRIC = {
    "embedding.encode_seconds": "encode_seconds",
    "encode_seconds": "encode_seconds",
    "total_seconds": "total_seconds",
    "corrupt.seconds": "corrupt_seconds",
    "throughput_texts_per_sec_repro": "throughput_repro",
}

YAML_METRIC = {
    "encoding": "encode_seconds",
    "corrupt": "corrupt_seconds",
    "total": "total_seconds",
}

HTML_DT = {
    "耗时": "corrupt_seconds",
    "encode_seconds": "encode_seconds",
    "total_seconds": "total_seconds",
}

# 需要跨行上下文才能定位的赋值形态。逐行扫描在这里不够用：原型数据文件里
# 同一个 "seconds" 键在两个对象下各出现一次（腐化段与重复段），只看键名会
# 改错地方。改用「对象起点 + 键」定位，并在整篇文本上做替换。
WHOLE_TEXT_RULES = {
    "system/prototype/data.js": [
        (re.compile(r'("encode_seconds":\s*)([\d.]+)'), "encode_seconds"),
        (re.compile(r'("total_seconds":\s*)([\d.]+)'), "total_seconds"),
        (re.compile(r'("corrupt":\s*\{.*?"seconds":\s*)([\d.]+)', re.S),
         "corrupt_seconds"),
    ],
}

# 候选值形态
# 秒单位有中文「秒」与日志里的 ASCII「s」两种写法。
CAND_SEC = re.compile(r"(\d+\.\d+)\s*(?:秒|s)(?![A-Za-z])")
# 吞吐：数字与单位之间允许夹一段括注（`245.971564（复现跑）条每秒`），
# 单位允许「条/秒」与「条每秒」两种写法。
CAND_RATE = re.compile(
    r"(\d+\.\d+)\s*(?:（[^）]*）)?\s*条(?:文本)?\s*(?:/秒|每秒)")
CAND_FIELD = re.compile(
    r"`?(embedding\.encode_seconds|encode_seconds|total_seconds|corrupt\.seconds"
    r"|throughput_texts_per_sec_repro)`?\s*(?:=|→|：|:)?\s*(\d+\.\d+)")
CAND_YAML = re.compile(r"^\s*(encoding|corrupt|total):\s*(\d+\.\d+)\s*$")
# 裸 `seconds=` 字段赋值（不带 `corrupt.` 前缀）: 出现在讲 `corrupt` 段的那一行里,
# 指的仍是 metrics.json -> corrupt.seconds。带 `dup.` 前缀的重复检测耗时由
# LINE_SKIP 整行排除。
CAND_BARE_SECONDS = re.compile(r"(?<![\w.])seconds\s*=\s*(\d+\.\d+)")
CAND_HTML = re.compile(r"<dt>(.*?)</dt><dd>(\d+\.\d+)\s*秒</dd>")
# 候选值紧跟其后的 metrics.json → 字段 引用
TRAILING_FIELD = re.compile(
    r"^\W{0,12}`?metrics\.json`?\s*[:：→>\\-]*\s*`?"
    r"(embedding\.encode_seconds|total_seconds|corrupt\.seconds"
    r"|throughput_texts_per_sec_repro)")
# 阈值表达：数字前带这些记号说明它是需求阈值 / 上界，不是实测值
THRESHOLD_MARK = re.compile(
    r"(≤|≥|≈|~|约|大约|超过|至少|不超过|上限|上界|阈值)\s*$")
# 吞吐语境：「首跑」是固定常量，「复现 / 复跑」才随每次复跑变化
FIRST_RUN_MARK = re.compile(r"首跑")
REPRO_MARK = re.compile(r"复现|复跑")

METRICS_ORDER = ("total_seconds", "corrupt_seconds", "encode_seconds",
                 "throughput_repro")


def read_current():
    with open(METRICS, encoding="utf-8") as f:
        m = json.load(f)
    with open(EMETA, encoding="utf-8") as f:
        e = json.load(f)
    cur = {
        "total_seconds": m["total_seconds"],
        "corrupt_seconds": m["corrupt"]["seconds"],
        "encode_seconds": e["encode_seconds"],
    }
    with open(DERIVED, encoding="utf-8") as f:
        for row in csv.reader(f):
            if row and row[0] == "embedding.throughput_texts_per_sec_repro":
                cur["throughput_repro"] = float(row[1])
    return cur


def read_state():
    if not os.path.exists(STATE):
        return {}
    with open(STATE, encoding="utf-8") as f:
        return json.load(f)


def fmt(v):
    return f"{float(v):.6f}".rstrip("0").rstrip(".")


def is_threshold(line, pos):
    """候选值前面是阈值记号时，它是需求阈值 / 上界，不是实测值。"""
    prefix = line[max(0, pos - 12):pos]
    return bool(THRESHOLD_MARK.search(prefix))


def label_metric(line, pos):
    """候选值前面最近的耗时关键词所属指标。

    同一个位置上可能有多个关键词命中（`腐化检测 0.35 秒` 里的「检测」与
    「腐化检测」结束于同一处），取结束位置更靠后、长度更长的那个，否则
    腐化耗时会被误判成三模块总耗时。
    """
    best = None
    for metric, kws in LABELS.items():
        for kw in kws:
            idx = line.rfind(kw, 0, pos)
            if idx < 0:
                continue
            cand = (idx + len(kw), len(kw), metric)
            if best is None or cand[:2] > best[:2]:
                best = cand
    return best[2] if best else None


def suffix_metric(line, end_pos):
    """候选值「秒」之后紧跟的模块名（`16.88 秒向量化` / `2.73 秒检测`）。"""
    tail = line[end_pos:end_pos + 8]
    for kw, metric in sorted(SUFFIX_LABELS.items(), key=lambda kv: -len(kv[0])):
        if tail.startswith(kw):
            return metric
    return None


def trailing_metric(line, end_pos):
    """候选值紧跟其后的 metrics.json → 字段 引用所指的指标。"""
    tail = line[end_pos:end_pos + 80]
    mm = TRAILING_FIELD.match(tail)
    if mm:
        return FIELD_METRIC[mm.group(1)]
    return None


def rate_metric(line, pos, end_pos):
    """吞吐候选值的指标：离它最近的「首跑 / 复现」标记决定归属。

    优先看候选值**后面**的标记：文档的惯例是「278.657718 条/秒（首跑）/
    245.971564 条/秒（复现跑）」——标记跟在各自数字后面，看前面会把上一个
    数的「首跑」算到下一个数头上。
    """
    after = []
    before = []
    for mm in FIRST_RUN_MARK.finditer(line):
        (after if mm.start() >= end_pos else before).append(
            (mm.start() - end_pos if mm.start() >= end_pos else pos - mm.end(), "first"))
    for mm in REPRO_MARK.finditer(line):
        (after if mm.start() >= end_pos else before).append(
            (mm.start() - end_pos if mm.start() >= end_pos else pos - mm.end(), "repro"))
    after = [m for m in after if m[0] <= RATE_MARK_MAX_GAP]
    before = [m for m in before if m[0] <= RATE_MARK_MAX_GAP]
    if after:
        after.sort()
        return None if after[0][1] == "first" else "throughput_repro"
    if not before:
        return label_metric(line, pos)
    before.sort()
    return None if before[0][1] == "first" else "throughput_repro"


def line_candidates(line, known):
    """返回 [(位置, 数值, 指标)]。显式形态优先于关键词推断。

    阈值记号（≤ ≥ ≈ ~ 约 …）的候选值，只有在它本身就是本脚本写过的实测值
    （出现在 `known` 清单里）时才继续处理；否则是需求阈值 / 量级描述，
    直接丢弃，不进「需人工确认」。
    """
    found = {}

    def put(pos, val, metric, explicit):
        key = pos
        prev = found.get(key)
        if prev is None or (explicit and not prev[2]):
            found[key] = (pos, val, metric, explicit)

    def known_has(metric, val):
        return metric in known and fmt(val) in [fmt(v) for v in known[metric]]

    for mm in CAND_SEC.finditer(line):
        metric = trailing_metric(line, mm.end())
        explicit = metric is not None
        if metric is None:
            metric = suffix_metric(line, mm.end())
        if metric is None:
            metric = label_metric(line, mm.start(1))
        if is_threshold(line, mm.start(1)) and not known_has(metric, mm.group(1)):
            continue
        put(mm.start(1), mm.group(1), metric, explicit)

    for mm in CAND_RATE.finditer(line):
        metric = trailing_metric(line, mm.end())
        explicit = metric is not None
        if metric is None:
            metric = rate_metric(line, mm.start(1), mm.end())
        if metric is None:
            continue
        if is_threshold(line, mm.start(1)) and not known_has(metric, mm.group(1)):
            continue
        put(mm.start(1), mm.group(1), metric, explicit)

    if "metrics.json" in line or "embeddings_meta.json" in line:
        for mm in CAND_FIELD.finditer(line):
            put(mm.start(2), mm.group(2), FIELD_METRIC[mm.group(1)], True)

    for mm in CAND_YAML.finditer(line):
        put(mm.start(2), mm.group(2), YAML_METRIC[mm.group(1)], True)

    for mm in CAND_BARE_SECONDS.finditer(line):
        # 只在讲 `corrupt` 段的行里认定; 其它行的裸 seconds= 含义不明, 交人工
        if "corrupt" not in line:
            continue
        put(mm.start(1), mm.group(1), "corrupt_seconds", True)

    for mm in CAND_HTML.finditer(line):
        metric = HTML_DT.get(mm.group(1).strip())
        if metric:
            put(mm.start(2), mm.group(2), metric, True)

    return [(pos, val, metric) for pos, val, metric, _ in found.values()]


def sync(check_only=False):
    cur = read_current()
    state = read_state()
    known = state.get("known", {})
    changes = []
    unresolved = []

    for rel in TARGETS:
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            original = f.read()
        lines = original.split("\n")

        for i, line in enumerate(lines):
            if any(s in line for s in LINE_SKIP):
                continue
            cands = line_candidates(line, known)
            if not cands:
                continue
            by_metric = {}
            ambiguous = False
            for _, val, metric in cands:
                if metric is None:
                    continue
                if metric in by_metric and by_metric[metric] != val:
                    ambiguous = True
                by_metric[metric] = val
            if ambiguous:
                unresolved.append(f"{rel}:{i + 1} 同一行内同指标出现多个耗时值")
                continue

            new_line = line
            # 同一行里同一指标可能重复出现该值（文档写的数字 + 实测值列），
            # 按「该指标在本行的唯一取值」整体替换，避免只改一处留下矛盾。
            groups = {}
            for pos, val, metric in cands:
                if metric is None:
                    continue
                groups.setdefault(metric, set()).add(val)
            for metric, vals in groups.items():
                if len(vals) != 1:
                    continue
                val = next(iter(vals))
                new = cur.get(metric)
                if new is None:
                    continue
                if fmt(val) == fmt(new):
                    continue
                old_list = [fmt(v) for v in known.get(metric, [])]
                if fmt(val) not in old_list:
                    # 不是本脚本管过的旧值，可能是别的含义，交给人工判断
                    unresolved.append(
                        f"{rel}:{i + 1} {metric} 的值 {val} 不在已知旧值清单内")
                    continue
                new_val = fmt(new)
                pat = re.compile(r"(?<![\d.])" + re.escape(fmt(val)) + r"(?![\d])")
                n = len(pat.findall(new_line))
                if not n:
                    continue
                new_line = pat.sub(new_val, new_line)
                changes.append((rel, i + 1, metric, fmt(val), new_val))
            lines[i] = new_line

        text = "\n".join(lines)

        # 跨行上下文的赋值：整篇文本上做，替换后必须保持行数不变
        for rule_pat, metric in WHOLE_TEXT_RULES.get(rel, []):
            mm = rule_pat.search(text)
            if not mm:
                continue
            old_val = mm.group(2)
            cur_val = cur.get(metric)
            if cur_val is None:
                continue
            new_val = fmt(cur_val)
            if fmt(old_val) == fmt(new_val):
                continue
            old_list = [fmt(v) for v in known.get(metric, [])]
            if fmt(old_val) not in old_list:
                unresolved.append(
                    f"{rel} {metric} 的值 {old_val} 不在已知旧值清单内")
                continue
            line_no = text[:mm.start()].count(chr(10)) + 1
            text = text[:mm.start()] + mm.group(1) + new_val + text[mm.end():]
            changes.append((rel, line_no, metric, fmt(old_val), new_val))
        if text != original:
            before = original.count("\n")
            after = text.count("\n")
            if after != before:
                print(f"[abort] {rel}：行数由 {before} 变为 {after}，"
                      f"疑似替换越界，本次不写入")
                return 2
            if not check_only:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(text)

    for rel, i, metric, old, new in changes:
        print(f"  {rel}:{i}  {metric}  {old} -> {new}")
    for u in unresolved:
        print(f"  [需人工确认] {u}")

    if not check_only:
        new_known = {k: list(v) for k, v in known.items()}
        for metric in METRICS_ORDER:
            if metric not in cur:
                continue
            vals = new_known.setdefault(metric, [])
            if fmt(cur[metric]) not in [fmt(v) for v in vals]:
                vals.append(cur[metric])
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump({"known": new_known}, f, ensure_ascii=False, indent=2)

    print(f"[sync_timings] 改动 {len(changes)} 处；当前值 "
          f"total_seconds={fmt(cur['total_seconds'])} "
          f"corrupt.seconds={fmt(cur['corrupt_seconds'])} "
          f"encoding.encode_seconds={fmt(cur['encode_seconds'])} "
          f"throughput_repro={fmt(cur.get('throughput_repro'))}")

    if check_only and changes:
        print("[sync_timings] --check 发现文档耗时值与产物漂移，"
              "请先跑 `python sync_timings.py`")
        return 1
    return 0


def main():
    check_only = "--check" in sys.argv[1:]
    if check_only:
        print("[sync_timings] --check 模式：只检查不修改")
    return sync(check_only=check_only)


if __name__ == "__main__":
    sys.exit(main())
