# -*- coding: utf-8 -*-
"""
check_numbers.py -- 论文/方案文档「实测数字」↔ 实测产物一致性门禁

用法:
  python check_numbers.py                        # 默认检查上级目录的三份文档
  python check_numbers.py a.md b.md               # 指定 0 到多个文档路径
  python check_numbers.py --report out.md         # 指定报告输出路径
  python check_numbers.py --selftest              # 只跑判定逻辑自证, 不碰任何文件

默认文档集(不传参数时全扫, 顺序即报告顺序):
  企业知识库质量治理系统技术方案.md   主技术方案
  本科版实施方案.md                   本科裁剪版实施方案
  数字溯源审计.md                     数字溯源审计报告(本身引用大量实测值)

判定流程(先命中先定):
  EXTERNAL    参考文献著录行 / arXiv 编号 / 模型规格表 / 第三方依赖安装包体积 /
              pip 安装说明等「引用他人文献或外部标准」的数字
  STRUCTURAL  章节号(§2.1 / 5.3.3) / 外部文件行号(第 2 数据行 / RESULT.md 418 行) /
              年份日期 / 列表序号 / SQL 类型长度 / 模型维度参数量 / 版本号 / 端口号
              —— 明显不是指标的编号, 按正则自动识别
  OK          在某个产物数值中精确命中(容差 1e-6); 数字后紧跟 % 时额外做一次
              「百分数 ↔ 小数」换算比对(0.186 ↔ 0.1855), 命中的注明换算
  ROUNDED     产物值按该数字的小数位数四舍五入后正好等于文档写的值
  ALLOWED     前面都没命中, 但命中 ALLOWED_UNSOURCED 登记项(仅限计划参数
              与外部第三方事实)。登记项故意排在最后: 否则同一行里的实测数字
              会被行内的登记关键词顺手带成 ALLOWED(实测过的「8 种打分」曾这样
              被误豁免)。
  CITED       该数字位于 markdown 表格的**引用列**(表头含「文档写的数字」/
              「文档写法」/「断言」/「出处」/「判定」/「偏差性质」/「未被引用」/
              「文档位置」/「位置」), 或位于溯源审计文档的**判定叙述行**
              (含「受审集合内无」「无产物」「仅见于」「已被实测修正」「改判」
              「原子声明」等判定词)。这两种位置的数字是文档在**转述并判定**
              别人的数值(被审方案写的值、日志里读到的值、审计自己的行数统计),
              不是它自己做的实测断言, 故不要求在产物里逐字命中。
              该状态按表头/判定词识别, 不针对任何具体数值开豁免。
  UNSOURCED   疑似自造但无产物支撑的数字

注: EXTERNAL / STRUCTURAL 排在 ALLOWED 之前, 因为「年份 2026」「章节号 7」
这类编号本来就不是实测数字, 不该被同一行里的登记关键词抢成 ALLOWED。

退出码语义(任一文档命中即整体命中):
  0 = 所有文档都没有「指标类 UNSOURCED」
  1 = 任一文档存在「指标类 UNSOURCED」(小数位 ≥ 3, 或上下文 20 字内出现
      F1/AUC/precision/recall/阈值/秒/ms/MB/耗时/相似度/准确率 等指标词)
  2 = 有文档不存在
也就是说: 非指标的 UNSOURCED 会被列出来但不致命, 指标类的一个都不能有。

本脚本对产物与文档**只读**, 唯一写入的文件是报告(默认 check_numbers_report.md)。
"""
import argparse
import csv
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DOC_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
# 默认受检文档集(不传位置参数时全扫)。刻意不收日志、不收 poc 下的产物、
# 也不收其余 7 份早期调研/选题文档: 那几份写于实测之前, 不承载论文数字。
DEFAULT_DOCS = [os.path.join(DOC_ROOT, n) for n in
                ("企业知识库质量治理系统技术方案.md",
                 "本科版实施方案.md",
                 "数字溯源审计.md")]
REPORT_NAME = "check_numbers_report.md"

# --------------------------------------------------------------- 来源集合
# JSON 产物(逐个列出, 目录里的 JSON 不自动收)
SOURCES_JSON = ["metrics.json", "embeddings_meta.json", "ground_truth.json"]
# CSV 产物(与 metrics.json 同级)
SOURCES_CSV = ["granularity.csv",
               "granularity_dup.csv",
               "corrupt_rule_ablation.csv",
               "gap_threshold.csv",
               "dup_threshold.csv",
               "dup_groups_best.csv",
               "corrupt_docs.csv",
               "top15_gaps.csv"]
# 长表型来源: 逐行 (derived_key, value) 的派生指标表, 只能读 value 列。
# 绝不能按宽表那套「把每格里的数字都抠出来」的办法处理——formula / inputs 列
# 里全是公式与被代入的原始值, 收进来等于让文档里的任何数字都能「自己证明自己」。
SOURCES_DERIVED = ["derived_metrics.csv"]
DERIVED_KEY_COL = "derived_key"
DERIVED_VAL_COL = "value"
# 明确不作为来源的文件: 门禁自己写出的报告。收进来等于让上一轮的门禁输出
# 给这一轮的数字背书, 数字之间互相循环证明, 门禁彻底失效。
# (granularity_dup.csv 曾经被列入此处, 实测会造成 5 处假失败: 文档 L806/L1169/L1170
#  的 0.9796 / 0.9803 / 0.5671 / 0.9545 都明写着出自该表, 排除后反而失去出处。
#  故只排除门禁报告本身。)
SOURCE_EXCLUDE = {REPORT_NAME}

# 目录型来源: 该目录下 *.csv 与 *.json 全收
SOURCES_DIRS = ["standardize"]

EXACT_TOL = 1e-6
CONTEXT_CHARS = 46          # 报告里展示的上下文宽度
NEAR_CHARS = 20             # 判定「是否指标类」只看数字左右各 20 字

# 数值断言的抽取规则:
#   - 左侧不得紧跟 ASCII 字母/数字/./-/, 以免把 bge-small-zh-v1.5、AUC0.968 这类
#     版本号或紧贴的标识符切成半个数字;
#   - 支持千分位(1,852);
#   - 支持前导正负号, 以便对上产物里的负值(如 AUC 衰减 -0.1605)。
NUM_RE = re.compile(
    r"(?<![A-Za-z0-9._\-])[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|(?<![A-Za-z0-9._\-])[-+]?\d+(?:\.\d+)?")

# 文档里负号常用 U+2212 (−) 而不是 ASCII "-", 直接正则匹配会把 −0.999817
# 切成正的 0.999817, 导致与产物里的负值对不上。抽取前统一归一化成 "-";
# 短横线 U+2013 (–) 在本项目里一律是区间号, 不做归一化。
MINUS_MAP = {"−": "-", "－": "-", "﹣": "-"}

# --------------------------------------------------------------- 分类词表
# 指标词: 出现在数字左右 NEAR_CHARS 字内即认为该数字是「疑似指标」
METRIC_WORDS = ["F1", "AUC", "precision", "recall", "ROC", "P=", "R=",
                "阈值", "秒", "ms", "MB", "耗时", "相似度", "准确率",
                "召回", "精确率", "标准差", "极差", "覆盖度", "检出"]
# 计量单位: 紧跟在数字右侧的单位字符
METRIC_UNITS = ["秒", "ms", "MB", "GB", "%"]

# 参考文献 / 外部标准著录行
BIB_RE = re.compile(
    r"^\s*\[\d+\]|arXiv|\[[JCMDS]\]|GB/T|Conference|Proceedings|"
    r"Transactions|Journal|Press|IEEE|ACM|Elsevier|Springer|Retrieval|"
    r"\bet al\.|doi[:：]|https?://")

# 章节号: 形如 5.3 / 5.3.1, 且上下文明确是章节引用
SECTION_SHAPE = re.compile(r"^\d{1,2}(?:\.\d{1,2}){1,3}$")
SECTION_BEFORE = ["第", "见", "详见", "参见", "命题", "推论", "整理", "走",
                  "强化", "只押", "作为", "在", "复用", "沿用", "出自", "呼应"]
SECTION_AFTER = ["节", "章", "的结论", "的实测结论", "的使用边界", "之外",
                 "表", "给出了", "给出", "算法改进点"]

# 模型维度(bge 系列)
DIM_SET = {384, 512, 768, 1024, 1536, 2048}
# SQL 类型: VARCHAR(64) / TEXT(255)
SQL_TYPE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*\($")

# 外部文件行号引用: "RESULT.md 418 行" / "第 2 数据行" / "第 3 行"。
# 行号指向的是别的文件里的位置, 不是任何测量值。
FILE_LINE_BEFORE = re.compile(
    r"第\s*$"                                  # 第 2 数据行
    r"|\.(?:md|csv|json|log|npy|txt|sh|py)`?\s*$")   # `RESULT.md` 418 行
FILE_LINE_AFTER = re.compile(r"^\s*(?:[-–—~]\s*[\d,]*\s*)?(?:行|数据行)")
# §小节号: §2.1 / §5.3.3
SECTION_SIGN_RE = re.compile(r"§\s*$")

# --------------------------------------------------------------- CITED 词表
# 「引用语境」: 文档在该处**转述并判定**别人的数值(被审方案写的值、日志里读到的
# 值、审计自己的行数统计), 而不是自己做了一次实测断言。这类数字不要求在产物
# 里逐字命中 —— 但判据是**位置与措辞**, 不是具体数值, 因此不会变成白名单。
# 溯源审计报告(数字溯源审计.md)整篇都是这个性质。
#
# CITED_COL_HEADERS 只用于**表格列名**匹配(列名是审计自己定的受控词表,
# 不会在技术方案正文里随机出现); CITED_VERDICT_WORDS 用于**整行**匹配,
# 因此这一份收得比列名表更紧: 只保留「明确在陈述某项产物出处/判定」的措辞,
# 「分子」「分母」「判定」这类通用词不收, 免得把普通论述行一起放行。
CITED_COL_HEADERS = ["文档位置", "文档写的数字", "文档写法", "文档写的值",
                     "断言", "出处", "实测产物出处", "受审产物出处",
                     "现受审产物出处", "判定", "偏差性质",
                     "未被引用的内容", "产物字面值"]
CITED_VERDICT_WORDS = ["受审集合内", "无出处", "无产物", "无记录", "无对应",
                       "无同名字段", "无同名列", "旁注", "已被实测修正",
                       "已分别由", "改判", "原先判为", "仅见于", "无据",
                       "不在受审集合", "未被引用", "无法核验", "原子声明"]
# 判定类表格行: 一行里同时出现「出处列」形态(文件名/键名/受审集合措辞)与
# 「文档原话」。用于行内没有表头可继承的场景(摘要段、结论段)。
CITED_ROW_HINT = re.compile(
    r"受审集合内|无产物|无记录|无对应|旁注|仅见于|无据|不在受审集合|"
    r"已分别由|已被实测修正|改判|无法核验|产物字面值|文档写的数字|文档写法")

# ---------------------------------------------------------------------------
# 已登记的「非产物来源」数字。每项 ("关键词", "理由"):
#   关键词 出现在该数字所在行的上下文里 -> 该数字判为 ALLOWED, 不计入失败。
#   默认留空: 先让脚本把真实差异全部暴露出来, 人工确认后再逐条登记。
#   例: ("2026-10-13", "文档撰写日期"), ("Ravenna", "他方产品定价, 非本原型实测")
#
# 登记门槛: 只登记「计划/估算参数」与「外部第三方事实」两类, 且**不得包含任何
# 实测指标**。任何实测数字走到这里都必须是真·无出处, 留在致命清单里逼人补产物
# 或改文档, 不许靠登记变绿。
# ---------------------------------------------------------------------------
ALLOWED_UNSOURCED = [
    # 计划参数(文档里已自标「尚未执行」): 目标语料规模, 无对应产物, 也不该有
    ("计划扩量目标",
     "计划参数, 非实测: 文档原文标注「尚未执行, 当前实测语料为 2000 条」"),
    # 计划估算工时: 原文已自标「计划估算, 非实测」, 是工作量推算而非任何模块的耗时
    ("计划估算，非实测",
     "计划估算工时, 非实测: 文档原文标注「计划估算，非实测」(数据扩量/阈值论证/Web/论文/答辩 天数)"),
]


# ============================================================ 产物侧收集
def parse_cell_numbers(cell):
    """从一个 CSV 单元格里抠出全部纯数值 token(文本里夹的数字也算)。"""
    vals = []
    for m in NUM_RE.finditer(str(cell).strip()):
        raw = m.group(0).replace(",", "")
        try:
            vals.append(float(raw))
        except ValueError:
            pass
    return vals


def collect_json(path, prefix):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    out = {}

    def walk(node, key):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, ("%s.%s" % (key, k)) if key else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (key, i))
        elif isinstance(node, bool):
            pass                      # True/False 不是数值
        elif isinstance(node, (int, float)):
            out[key] = float(node)

    walk(data, "")
    return {"%s:%s" % (prefix, k): v for k, v in out.items()}


def collect_csv(path, prefix):
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        if rdr.fieldnames is None:
            return out
        for i, row in enumerate(rdr, 1):
            for col, cell in row.items():
                if col is None or cell is None:
                    continue
                for j, v in enumerate(parse_cell_numbers(cell)):
                    out["%s:%s[row=%d][%d]" % (prefix, col, i, j)] = v
    return out


def collect_derived(path, prefix):
    """读长表型派生指标表。

    结构: derived_key,value,formula,inputs,source_files
    只收 value 列, 键用 derived_key —— 这是「这个数字是从哪些实测产物按什么公式
    算出来的」的自证链。formula / inputs 两列里的数字**一律不收**: 它们是公式的
    文字写法与被代入的原始值, 收进来后文档里写任何数字都能在自己身上找到出处。
    """
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        if rdr.fieldnames is None:
            return out
        names = {n.strip() for n in rdr.fieldnames}
        if DERIVED_KEY_COL not in names or DERIVED_VAL_COL not in names:
            return out
        for row in rdr:
            key = (row.get(DERIVED_KEY_COL) or "").strip()
            if not key:
                continue
            cell = (row.get(DERIVED_VAL_COL) or "").strip()
            try:
                out["%s:%s" % (prefix, key)] = float(cell)
            except ValueError:
                continue
    return out


def collect_sources(verbose=True):
    """收集全部产物数值, 返回 (来源表, 来源文件清单)。"""
    sources = {}
    files = []
    for name in SOURCES_JSON:
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            if verbose:
                print("[check] 缺少产物: %s" % name)
            continue
        sources.update(collect_json(p, name))
        files.append(name)
    for name in SOURCES_CSV:
        if name in SOURCE_EXCLUDE:
            continue
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            if verbose:
                print("[check] 缺少产物: %s" % name)
            continue
        sources.update(collect_csv(p, name))
        files.append(name)
    for name in SOURCES_DERIVED:
        if name in SOURCE_EXCLUDE:
            continue
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            if verbose:
                print("[check] 缺少产物: %s" % name)
            continue
        sources.update(collect_derived(p, name))
        files.append(name)
    for dname in SOURCES_DIRS:
        d = os.path.join(HERE, dname)
        if not os.path.isdir(d):
            if verbose:
                print("[check] 缺少产物目录: %s" % dname)
            continue
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            low = fn.lower()
            if fn in SOURCE_EXCLUDE or not low.endswith((".csv", ".json")):
                continue
            if low.endswith(".csv"):
                sources.update(collect_csv(p, "%s/%s" % (dname, fn)))
            else:
                sources.update(collect_json(p, "%s/%s" % (dname, fn)))
            files.append("%s/%s" % (dname, fn))
    return sources, files


# ============================================================ 文档侧抽取
def decimals_of(text):
    """文档里写的有效小数位数(0.7037 -> 4, 22 -> 0, 1,852 -> 3)。"""
    body = text.replace(",", "")
    if body.count(".") != 1:
        # 1,852 之类千分位已去掉逗号; 5.3.1 这种多段号不算小数
        return len(body.split(".")[1]) if "." in body else 0
    return len(body.split(".")[1])


def fmt_context(line, start, end):
    """截取数字前后各 CONTEXT_CHARS 个字符作为可读上下文。"""
    a = max(0, start - CONTEXT_CHARS)
    b = min(len(line), end + CONTEXT_CHARS)
    frag = re.sub(r"\s+", " ", line[a:b].strip())
    if a > 0:
        frag = "…" + frag
    if b < len(line):
        frag = frag + "…"
    return frag


def _table_cells(line):
    """markdown 表格行 -> [(起始偏移, 结束偏移, 单元格文本)]。非表格行返回 []。

    逐个竖线扫描而不是 split 再回查位置: split 丢失偏移, 回查会在重复文本上
    匹配错列, 而列名正是本脚本判定「引用列」的依据。
    """
    if not line.strip().startswith("|"):
        return []
    spans = []
    depth_start = line.index("|") + 1
    start = depth_start
    pos = depth_start
    while pos < len(line):
        ch = line[pos]
        if ch == "\\" and pos + 1 < len(line):
            pos += 2
            continue
        if ch == "|":
            spans.append((start, pos, line[start:pos].strip()))
            start = pos + 1
        pos += 1
    tail = line[start:].strip()
    if tail:
        # 行尾没有收尾竖线: 末格是残段, 仍按一列计
        spans.append((start, len(line), tail))
    else:
        spans = spans[:-1] if spans and not spans[-1][2] else spans
    # 去掉行首竖线之前那一格(恒为空)
    if spans and spans[0][2] == "" and spans[0][0] == depth_start:
        spans = spans[1:]
    return spans


def _is_sep_row(line):
    s = line.strip()
    return bool(s.startswith("|")) and set(s) <= set("|-: \t")


def extract_claims(text):
    """逐行抽数值断言。同一行内相同写法只记一次, 合并进 count。

    同时维护 markdown 表格的表头上下文: 溯源审计报告整篇由表格构成, 表头列名
    决定了某一格里的数字是「被审文档写的数 / 审计自己的判定」还是「本报告做的
    实测断言」。缺了表头上下文, 这类数字会被整片误判成无出处。
    """
    for ch, plain in MINUS_MAP.items():
        text = text.replace(ch, plain)
    lines = text.splitlines()
    claims = []
    header = []          # 当前表格的表头单元格文本
    header_valid = False  # 表头是否由「表头行 + 分隔行」确证
    for lineno, line in enumerate(lines, 1):
        # 表头行: 本行是表格行, 下一行是 |---|---| 分隔行
        nxt = lines[lineno] if lineno < len(lines) else ""
        if line.strip().startswith("|") and _is_sep_row(nxt):
            header = [c[2] for c in _table_cells(line)]
            header_valid = len(header) >= 2
        elif not line.strip().startswith("|"):
            header = []
            header_valid = False
        elif _is_sep_row(line):
            continue

        cells = _table_cells(line)
        in_table = bool(cells)
        seen = {}
        for m in NUM_RE.finditer(line):
            raw = m.group(0)
            try:
                value = float(raw.replace(",", ""))
            except ValueError:
                continue
            if raw in seen:
                seen[raw]["count"] += 1
                continue
            before = re.sub(r"\s+", " ", line[:m.start()]).strip()
            after = re.sub(r"\s+", " ", line[m.end():]).strip()
            # 该数字落在表格的哪一列
            col = -1
            if in_table:
                for i, (a, b, _t) in enumerate(cells):
                    if a <= m.start() < b:
                        col = i
                        break
                if col < 0 and m.start() >= (cells[-1][1] if cells else 0):
                    col = len(cells) - 1
            col_name = header[col] if (in_table and 0 <= col < len(header)) else ""
            item = {"line": lineno,
                    "raw": raw,
                    "value": value,
                    "decimals": decimals_of(raw),
                    "count": 1,
                    "before": before[-40:],
                    "after": after[:40],
                    "near": before[-NEAR_CHARS:] + " ⟂ " + after[:NEAR_CHARS],
                    "context": fmt_context(line, m.start(), m.end()),
                    "heading": bool(re.match(r"^\s{0,3}#{1,6}\s", line)),
                    "bib": bool(BIB_RE.search(line)),
                    "in_table": in_table,
                    "col": col,
                    "col_name": col_name,
                    "header_valid": header_valid,
                    # 行级判定标记: 整行是否在陈述溯源判定。溯源报告的结论段
                    # 是用自然语言枚举判定结果的（「无出处的 12 条：…92MB、33.7 秒…」），
                    # 没有表格列名可依赖, 只能按行判。
                    "line_hint": bool(CITED_ROW_HINT.search(line))
                    or any(w in line for w in CITED_VERDICT_WORDS)}
            seen[raw] = item
            claims.append(item)
    return claims


def looks_like_metric(claim):
    """疑似指标 = 小数位 ≥ 3, 或左右 20 字内出现指标词/计量单位。"""
    if claim["decimals"] >= 3:
        return True
    near = claim["near"]
    if any(w in near for w in METRIC_WORDS):
        return True
    after = claim["after"]
    return any(after.startswith(u) for u in METRIC_UNITS)


def unit_suffix(claim):
    """取数字右侧紧跟的一个单位 token(没有则空串)。"""
    m = re.match(r"^\s*([A-Za-z%]+|秒|条|篇|张|天|字|页|维|份|行|个|人)", claim["after"])
    return m.group(1) if m else ""


# ============================================================ 判定
def classify_against(value, decimals, sources, percent_ok=False):
    """在来源表里找 value。返回 (状态, 来源标识, 产物值, 备注)。"""
    best = None
    for sid, v in sources.items():
        d = abs(v - value)
        if d <= EXACT_TOL and (best is None or d < best[0]):
            best = (d, sid, v)
    if best:
        note = "百分数换算" if percent_ok else ""
        return "OK", best[1], best[2], note

    if percent_ok:
        frac = value / 100.0
        cands = [(abs(v - frac), sid, v) for sid, v in sources.items()
                 if round(v, decimals + 2) == round(frac, decimals + 2)]
        if cands:
            cands.sort(key=lambda t: (t[0], t[1]))
            return "OK", cands[0][1], cands[0][2], "百分数换算 ↔ 小数"

    cands = [(abs(v - value), sid, v) for sid, v in sources.items()
             if v != value and round(v, decimals) == value]
    if cands:
        cands.sort(key=lambda t: (t[0], t[1]))
        return "ROUNDED", cands[0][1], cands[0][2], ""
    return None, "", None, ""


def structural_of(claim):
    """结构化编号识别。返回 (状态, 理由) 或 None。"""
    raw = claim["raw"]
    value = claim["value"]
    before = claim["before"]
    after = claim["after"]
    unit = unit_suffix(claim)

    # 年份 / 日期: 1900-2100 的四位数, 且不是「768 维」这类规格
    if re.fullmatch(r"(19|20)\d{2}", raw) and unit not in ("维", "M", "层"):
        return "STRUCTURAL", "年份/日期"
    # 版本号: Python 3.11.9 / torch 2.14.0 / UML 2.0
    if re.match(r"^\.\d", after) and re.search(r"[A-Za-z0-9]\s*$", before):
        return "STRUCTURAL", "版本号"
    # 随机种子
    if re.search(r"(random\.)?seed\s*\(?\s*=?\s*$", before, re.I):
        return "STRUCTURAL", "随机种子"
# SQL 字段长度: VARCHAR(64)
    if re.fullmatch(r"\d+", raw) and SQL_TYPE_RE.search(before) \
            and after.startswith(")"):
        return "STRUCTURAL", "SQL 字段长度"
    # 外部文件行号: "RESULT.md 418 行" / "第 2 数据行" / "第 3 行"
    if FILE_LINE_AFTER.match(after) and FILE_LINE_BEFORE.search(before):
        return "STRUCTURAL", "外部文件行号引用"
    # 列表序号: **11.** / 12. **
    if re.match(r"^\s*\.\s*\*\*", after) or \
            re.match(r"^\s*\*\*\d+\.", before + after):
        return "STRUCTURAL", "列表序号"
    # 端口号
    if re.fullmatch(r"\d{4,5}", raw) and 1024 <= value <= 65535 \
            and re.search(r"(端口|port)\s*[:：=]?\s*$|[:：=]\s*$",
                          before[-10:], re.I):
        return "STRUCTURAL", "端口号"
    # 章节号
    if SECTION_SHAPE.match(raw):
        if claim["heading"] or before.endswith("**"):
            return "STRUCTURAL", "章节号"
        if SECTION_SIGN_RE.search(before) or before.endswith("§"):
            return "STRUCTURAL", "章节号(§引用)"
        if any(before.endswith(k) or before.endswith(k + " ") for k in SECTION_BEFORE):
            return "STRUCTURAL", "章节号"
        if any(after.startswith(k) for k in SECTION_AFTER):
            return "STRUCTURAL", "章节号"
        if re.search(r"\d\.\d\s*/\s*\d\.\d", claim["context"]):
            return "STRUCTURAL", "章节号(枚举)"
        # 表格「文档位置 / 位置 / 编号」列里的 x.y: 指向被引文档的小节
        if claim.get("in_table") and claim.get("col_name") in (
                "文档位置", "位置", "章节", "编号"):
            return "STRUCTURAL", "章节号(文档位置列)"
    # 模型参数量: 24M / 326M (排除 MB 体积)
    if unit == "M":
        return "STRUCTURAL", "模型参数量"
    # 模型维度: 768 / 1024 且所在行是 bge 规格表
    if int(value) in DIM_SET and unit in ("", "维") \
            and re.search(r"bge-[a-z]", claim["context"]):
        return "STRUCTURAL", "模型维度"
    return None


def external_of(claim):
    """外部来源数字识别。返回 (状态, 理由) 或 None。"""
    before = claim["before"]
    after = claim["after"]
    near = claim["near"]
    unit = unit_suffix(claim)
    measured = "实测" in before[-8:]

    if claim["bib"] and "arXiv" not in after[:12]:
        return "EXTERNAL", "参考文献/外部标准著录"
    if re.match(r"^\.\d{4,5}", after) or re.search(r"arXiv[:：]\s*$", before):
        return "EXTERNAL", "arXiv 预印本编号"
    if re.search(r"bge-[a-z]", claim["context"]) and not measured:
        if unit in ("M", "MB", "GB", "维") or int(claim["value"]) in DIM_SET:
            return "EXTERNAL", "模型规格(外部公开参数)"
    if re.search(r"pip install|download\.pytorch|whl/cpu", claim["context"]):
        return "EXTERNAL", "外部依赖安装说明"
    # 第三方 wheel 体积(如 torch CPU 版 200MB / CUDA 版 2.5GB): 描述的是
    # PyTorch 官方发布包的大小, 不是本原型的任何实测值。
    if re.search(r"torch|whl|cuda", claim["context"], re.I) \
            and unit in ("MB", "GB"):
        return "EXTERNAL", "第三方依赖安装包体积(非本原型实测)"
    if re.search(r"\bGB/?T\s*$", before) or re.search(r"GB/T \d{3,4}", claim["context"]):
        return "EXTERNAL", "外部标准编号"
    del near
    return None


def allowance_for(claim):
    """命中 ALLOWED_UNSOURCED 登记项则返回理由, 否则 None。"""
    for keyword, reason in ALLOWED_UNSOURCED:
        if keyword and keyword in claim["context"]:
            return reason
    return None


def cited_of(claim):
    """引用语境识别。返回 (状态, 理由) 或 None。

    判据是**位置与措辞**, 不是数值本身, 所以这不是白名单:
      1. 数字落在 markdown 表格的引用列(表头含「文档写的数字」「断言」「出处」
         「判定」「偏差性质」等)。这类列装的是被审文档写的数、日志里读到的数、
         或审计自己的判定词, 不是本报告做的实测断言。
      2. 数字所在的行/列表格行带溯源判定词(「受审集合内无」「仅见于」
         「已被实测修正」等)。这类行是审计在**陈述一项判定**, 数字是判定对象。
    命中前仍要先过 STRUCTURAL 与产物精确命中, 因此「引用列里真命中了产物」
    的数字照样显示为 OK, 不会被这个状态盖掉。
    """
    col = claim.get("col_name") or ""
    # 列名匹配必须是整列名或「列名（补充说明）」的前缀, 不能是子串:
    # 早先用子串匹配时, 本科版的「备注（判定理由）」列因为含「判定」二字被误判成
    # 引用列, 里面真实的 0.035 指标数字被放行了。
    base = re.split(r"[（(]", col)[0].strip() if col else ""
    if base and base in CITED_COL_HEADERS:
        return "CITED", "表格引用列「%s」：转述并判定他处数值，非本报告实测断言" % col
    if claim.get("line_hint"):
        return "CITED", "溯源判定语境：该数字是本行判定所转述的对象，非本报告实测断言"
    return None


def classify_claim(claim, sources):
    """完整判定一个数值断言。"""
    # 参考文献著录行整行都是外部数字(年份/卷期/页码/标准号), 先于结构性判定
    if claim["bib"] and not re.match(r"^\.\d{4,5}", claim["after"]):
        return {"status": "EXTERNAL", "source": "参考文献/外部标准著录",
                "product": None, "note": ""}

    # STRUCTURAL 先于一切: 年份/章节号/列表序号这类编号本来就不是「实测数字」。
    st = structural_of(claim)
    if st:
        return {"status": st[0], "source": st[1], "product": None, "note": ""}

    percent = claim["after"].lstrip().startswith("%")
    status, sid, val, note = classify_against(claim["value"], claim["decimals"],
                                              sources, percent_ok=percent)
    if status:
        return {"status": status, "source": sid, "product": val, "note": note}

    reason = allowance_for(claim)
    if reason:
        return {"status": "ALLOWED", "source": reason, "product": None, "note": ""}

    st = external_of(claim)
    if st:
        return {"status": st[0], "source": st[1], "product": None, "note": ""}

    st = cited_of(claim)
    if st:
        return {"status": st[0], "source": st[1], "product": None, "note": ""}

    return {"status": "UNSOURCED", "source": "", "product": None, "note": ""}


def audit(doc_path, sources):
    with open(doc_path, encoding="utf-8") as f:
        text = f.read()
    rows = []
    for c in extract_claims(text):
        c.update(classify_claim(c, sources))
        c["metric"] = looks_like_metric(c)
        rows.append(c)
    return rows


# ============================================================ 报告
def fmt_value(v):
    if v is None:
        return ""
    return ("%.10g" % v)


STATUS_ORDER = ["UNSOURCED", "ROUNDED", "STRUCTURAL", "EXTERNAL", "CITED",
                "ALLOWED", "OK"]


def write_report(audits, sources, files, out_path):
    """写多文档报告。audits = [(doc_path, rows), ...]。返回 (总计, 致命总数)。"""
    lines = ["# 实测数字一致性检查报告", ""]
    lines.append("- 受检文档：**%d** 份" % len(audits))
    for p, _rows in audits:
        lines.append("  - `%s`" % p)
    lines.append("- 产物来源（%d 个文件）：%s" % (len(files), "、".join("`%s`" % f for f in files)))
    lines.append("- 产物数值叶子：**%d** 个" % len(sources))
    lines.append("")
    lines.append("> 判定口径（先命中先定）：`EXTERNAL` = 参考文献著录 / arXiv 编号 / 模型规格 / "
                 "第三方依赖安装包体积 / 依赖安装说明；"
                 "`STRUCTURAL` = 章节号（含 §引用与表格「文档位置」列）/ 外部文件行号 / "
                 "年份日期 / 列表序号 / SQL 类型长度 / 模型维度参数量 / 版本号 / 端口号等"
                 "结构性编号；"
                 "`ALLOWED` = 已登记的非产物来源（仅限计划参数与外部第三方事实）；"
                 "`OK` = 产物中有同值（容差 1e-6，"
                 "数字后紧跟 `%` 时额外做一次百分数↔小数换算）；"
                 "`ROUNDED` = 产物值按该数字小数位四舍五入后相等；"
                 "`CITED` = 引用语境 —— 数字落在 markdown 表格的引用列（表头含"
                 "「文档写的数字」「文档写法」「断言」「出处」「判定」「偏差性质」"
                 "「未被引用的内容」等），或落在带溯源判定词（`受审集合内无` / `仅见于` / "
                 "`已被实测修正` / `改判` …）的行里，即本文档在**转述并判定**他处数值或"
                 "做自己的计数，而非自己做了一次实测断言。判据是位置与措辞，不是数值白名单；"
                 "`UNSOURCED` = 找不到任何出处。")
    lines.append("")
    lines.append("> 只有 **指标类 UNSOURCED** 影响退出码。指标类 = 小数位 ≥ 3，"
                 "或数字左右各 20 字内出现 %s 等指标词。"
                 % "、".join(METRIC_WORDS[:8]))

    # ---------------- 总览表 ----------------
    total = {s: 0 for s in STATUS_ORDER}
    total["n_claims"] = 0
    total_bad = 0
    overview = []
    for doc_path, rows in audits:
        counts = {s: 0 for s in STATUS_ORDER}
        for r in rows:
            counts[r["status"]] += 1
        bad = [r for r in rows if r["status"] == "UNSOURCED" and r["metric"]]
        for s in STATUS_ORDER:
            total[s] += counts[s]
        total["n_claims"] += len(rows)
        total_bad += len(bad)
        overview.append((doc_path, len(rows), counts, len(bad)))

    lines.append("")
    lines.append("## 0. 总览")
    lines.append("")
    head = "| 文档 | 断言数 | OK | ROUNDED | STRUCTURAL | EXTERNAL | CITED | ALLOWED | UNSOURCED | 指标类 UNSOURCED（致命） |"
    lines.append(head)
    lines.append("|" + "---|" * 10)
    for doc_path, n, c, nb in overview:
        lines.append("| `%s` | %d | %d | %d | %d | %d | %d | %d | %d | **%d** |"
                     % (os.path.basename(doc_path), n, c["OK"], c["ROUNDED"],
                        c["STRUCTURAL"], c["EXTERNAL"], c["CITED"], c["ALLOWED"],
                        c["UNSOURCED"], nb))
    lines.append("| **合计** | **%d** | %d | %d | %d | %d | %d | %d | %d | **%d** |"
                 % (total["n_claims"], total["OK"], total["ROUNDED"],
                    total["STRUCTURAL"], total["EXTERNAL"], total["CITED"],
                    total["ALLOWED"], total["UNSOURCED"], total_bad))
    lines.append("")
    lines.append("- 总退出码：**%d**（%s）"
                 % (1 if total_bad else 0,
                    "指标类 UNSOURCED 合计 %d 条，必须逐条给出产物出处或改文档" % total_bad
                    if total_bad else "没有指标类数字缺出处"))

    def table(subset, note_col=False):
        if not subset:
            return ["（无）", ""]
        head = "| 行号 | 文档上下文 | 文档写的数字 | 匹配到的来源 | 产物值 |"
        sep = "|---|---|---|---|---|"
        if note_col:
            head += " 备注 |"
            sep += "---|"
        out = [head, sep]
        for r in subset:
            ctx = r["context"].replace("|", "\\|")
            shown = r["raw"] + (" (×%d)" % r["count"] if r["count"] > 1 else "")
            src = r["source"].replace("|", "\\|") if r["source"] else ""
            row = "| %d | %s | `%s` | `%s` | `%s` |" % (
                r["line"], ctx, shown, src, fmt_value(r["product"]))
            if note_col:
                row += " %s |" % r["note"]
            out.append(row)
        out.append("")
        return out

    # ---------------- 每份文档独立分节 ----------------
    for di, (doc_path, rows) in enumerate(audits, 1):
        counts = {s: 0 for s in STATUS_ORDER}
        for r in rows:
            counts[r["status"]] += 1
        bad = [r for r in rows if r["status"] == "UNSOURCED" and r["metric"]]
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 文档 %d / %d：`%s`" % (di, len(audits), os.path.basename(doc_path)))
        lines.append("")
        lines.append("- 完整路径：`%s`" % doc_path)
        lines.append("- 抽到的数值断言：**%d** 处" % len(rows))
        lines.append("- 判定统计：OK=**%d**　ROUNDED=**%d**　STRUCTURAL=**%d**　"
                     "EXTERNAL=**%d**　CITED=**%d**　ALLOWED=**%d**　UNSOURCED=**%d**"
                     % (counts["OK"], counts["ROUNDED"], counts["STRUCTURAL"],
                        counts["EXTERNAL"], counts["CITED"], counts["ALLOWED"],
                        counts["UNSOURCED"]))
        lines.append("- 指标类 UNSOURCED（致命）：**%d** 条 —— %s"
                     % (len(bad),
                        "必须逐条给出产物出处" if bad else "无"))

        lines.append("")
        lines.append("### %d.1 指标类 UNSOURCED —— 致命项，必须为空或逐条补出处" % di)
        lines.append("")
        lines.extend(table(bad, note_col=True))

        other_unsourced = [r for r in rows
                           if r["status"] == "UNSOURCED" and not r["metric"]]
        lines.append("### %d.2 非指标类 UNSOURCED —— 不致命，但同样没有产物出处" % di)
        lines.append("")
        lines.extend(table(other_unsourced))

        lines.append("### %d.3 ROUNDED —— 产物值四舍五入后等于文档写法（需人工确认语义一致）" % di)
        lines.append("")
        lines.append("> 本节同时给出**文档上下文**与**产物值**：同值不同义的情况（例如文档说的是"
                     "组内余弦相似度、产物那格却是 AUC）只能靠这一对信息人工看出来，"
                     "脚本不做语义推断，也不靠放宽容差掩盖。")
        lines.append("")
        lines.extend(table([r for r in rows if r["status"] == "ROUNDED"]))

        for si, status in enumerate(["STRUCTURAL", "EXTERNAL", "CITED", "ALLOWED"]):
            title = {"STRUCTURAL": "STRUCTURAL —— 结构性编号（章节号/外部文件行号/年份/"
                                   "序号/SQL 长度/模型维度参数量/版本号/端口号）",
                     "EXTERNAL": "EXTERNAL —— 引用他人文献或外部标准的数字",
                     "CITED": "CITED —— 引用语境（转述并判定他处数值 / 审计自身计数）",
                     "ALLOWED": "ALLOWED —— 已在 ALLOWED_UNSOURCED 登记的例外"}[status]
            lines.append("### %d.%d %s" % (di, si + 4, title))
            lines.append("")
            lines.extend(table([r for r in rows if r["status"] == status]))

        lines.append("### %d.8 OK —— 精确命中产物" % di)
        lines.append("")
        lines.extend(table([r for r in rows if r["status"] == "OK"]))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return total, total_bad


# ============================================================ 自证
def selftest():
    fake = {"metrics.json:gap.best.f1": 0.8,
            "standardize/dup.csv:group_f1[0]": 0.7037012,
            "standardize/dup.csv:group_f1[1]": 0.9466,
            "standardize/auc.csv:AUC[row=1]": 0.1123,
            "granularity.csv:auc[0]": 0.888,
            "granularity_dup.csv:min[0]": 0.1855}
    cases = [
        ("完全相等", 0.8, 1, "OK", "metrics.json:gap.best.f1"),
        ("四舍五入", 0.7037, 4, "ROUNDED", "standardize/dup.csv:group_f1[0]"),
        ("位数不同的相等", 0.9466, 4, "OK", "standardize/dup.csv:group_f1[1]"),
        ("无匹配", 0.1234, 4, "", ""),
        ("整数无匹配", 4711, 0, "", ""),
        ("百分数换算", 18.55, 2, "OK", "granularity_dup.csv:min[0]"),
    ]
    ok = True
    for name, value, dec, want_status, want_src in cases:
        pct = name == "百分数换算"
        got_status, got_src, _, _ = classify_against(value, dec, fake,
                                                     percent_ok=pct)
        if want_status == "":
            good = got_status is None
        else:
            good = (got_status == want_status
                    and (want_src == "" or got_src == want_src))
        ok = ok and good
        print("[selftest] 数值匹配 %-10s %-8s -> %-9s %s  %s"
              % (name, ("%g" % value), got_status or "(无匹配)", got_src,
                 "PASS" if good else "FAIL(want %s %s)" % (want_status, want_src)))

    doc = ("### 5.3 阈值可迁移性\n"
           "撰写日期：2026-10-13，seed=42。\n"
           "F1=0.9466，检测耗时 2.59 秒，段落级 AUC 由 0.888 提升至 0.968。\n"
           "缺口意图工单占比 18.55%，组级 F1=0.7037，随机基线 0.1123。\n"
           "name VARCHAR(64) NOT NULL, bge-base-zh-v1.5 约 102M 参数 / 768 维。\n"
           "另引他人结论：McDonald et al. 2003, 2009: 226-231。\n"
           "详见 5.3.3 节；本机 Python 3.11.9，服务端口 8080。\n"
           "纯属杜撰 4.2424 与 9.8765。\n")
    claims = extract_claims(doc)
    got = {}
    for c in claims:
        c.update(classify_claim(c, fake))
        c["metric"] = looks_like_metric(c)
        got.setdefault(c["status"], []).append(c["raw"])

    # 注: NUM_RE 的左边界不含 "." , 故 "5.3.3" 只切出首个 "5.3"
    want_structural = ["5.3", "2026", "42", "64", "102", "768", "8080", "3.11"]
    want_external = ["2003", "2009", "226"]
    want_ok = ["0.9466", "0.888", "18.55", "0.1123"]
    want_rounded = ["0.7037"]
    want_unsourced = ["2.59", "0.968", "4.2424", "9.8765"]

    def all_in(actual, expected):
        return all(any(e in a for a in actual) for e in expected)

    checks = [
        ("结构性编号", all_in(got.get("STRUCTURAL", []), want_structural),
         got.get("STRUCTURAL", [])),
        ("外部引用", all_in(got.get("EXTERNAL", []), want_external),
         got.get("EXTERNAL", [])),
        ("精确命中", all_in(got.get("OK", []), want_ok), got.get("OK", [])),
        ("四舍五入", all_in(got.get("ROUNDED", []), want_rounded),
         got.get("ROUNDED", [])),
        ("无出处", all_in(got.get("UNSOURCED", []), want_unsourced),
         got.get("UNSOURCED", [])),
    ]
    for name, good, actual in checks:
        ok = ok and good
        print("[selftest] %-10s -> %s  %s"
              % (name, actual, "PASS" if good else "FAIL"))

    metric_bad = [c["raw"] for c in claims
                  if c["status"] == "UNSOURCED" and c["metric"]]
    nonmetric_bad = [c["raw"] for c in claims
                     if c["status"] == "UNSOURCED" and not c["metric"]]
    fatal_ok = set(metric_bad) == {"2.59", "0.968", "4.2424", "9.8765"}
    ok = ok and fatal_ok
    print("[selftest] 指标类致命 -> %s  %s"
          % (metric_bad, "PASS" if fatal_ok else "FAIL"))
    ok = ok and nonmetric_bad == []
    print("[selftest] 非指标容忍 -> %s  %s"
          % (nonmetric_bad, "PASS" if nonmetric_bad == [] else "FAIL"))

    # --- 新增机制的自证: §章节号 / 外部文件行号 / 表格引用列 ---
    doc2 = ("见 §5.3.3 节与 §2.1 的结论。\n"
            "`RESULT.md` 418 行、`granularity.csv` 10 行、第 2 数据行。\n"
            "| 文档位置 | 文档写的数字 | 实测产物出处 | 实测值 | 判定 |\n"
            "|---|---|---|---|---|\n"
            "| §1.4 贡献 1 | 整篇级 AUC 0.9137 | 受审集合内无记录 | — | 【无出处】 |\n"
            "| §1.4 贡献 2 | 缺口 F1 = 0.800 | `metrics.json` → `gap.best.f1` | 0.8 | 一致 |\n"
            "| §2.1 选型表 | 实测落盘 92MB | 受审集合内无记录落盘体积的键 | — | 【无出处】 |\n")
    claims2 = extract_claims(doc2)
    got2 = {}
    for c in claims2:
        c.update(classify_claim(c, fake))
        c["metric"] = looks_like_metric(c)
        got2.setdefault(c["status"], []).append(c["raw"])

    # §引用的 5.3.3 / 2.1 / 1.4 / 5.3 必须是 STRUCTURAL(章节号),
    # 而 0.8880 / 92MB 这类「文档写的数字」列必须是 CITED,
    # 表格里真命中产物的 0.800 / 0.8 必须仍然是 OK(不能被 CITED 盖掉)。
    sec_ok = ("5.3" in got2.get("STRUCTURAL", [])
              and "2.1" in got2.get("STRUCTURAL", []))
    ok = ok and sec_ok
    print("[selftest] §章节号   -> %s  %s"
          % (got2.get("STRUCTURAL", []), "PASS" if sec_ok else "FAIL"))

    line_ok = ("418" in got2.get("STRUCTURAL", [])
               and "10" in got2.get("STRUCTURAL", []))
    ok = ok and line_ok
    print("[selftest] 文件行号 -> %s  %s"
          % (got2.get("STRUCTURAL", []), "PASS" if line_ok else "FAIL"))

    cited_ok = "0.9137" in got2.get("CITED", []) and "92" in got2.get("CITED", [])
    ok = ok and cited_ok
    print("[selftest] 引用列   -> %s  %s"
          % (got2.get("CITED", []), "PASS" if cited_ok else "FAIL"))

    # 关键回归: 引用列里真命中产物的数字必须显示 OK, 不能被 CITED 抢走
    not_masked = "0.8" in got2.get("OK", []) and "0.8" not in got2.get("CITED", [])
    ok = ok and not_masked
    print("[selftest] 引用列不掩盖命中 -> %s  %s"
          % (got2.get("OK", []), "PASS" if not_masked else "FAIL"))

    # 关键回归: 引用列的判定不得让普通文档里的裸指标数字脱罪
    bare_ok = classify_claim(dict(extract_claims("整篇级 AUC 0.9137 提升。")[0],
                                  value=0.9137, decimals=4, raw="0.9137",
                                  before="整篇级 AUC ", after="提升。",
                                  near="整篇级 AUC ⟂ 提升。",
                                  context="整篇级 AUC 0.9137 提升。",
                                  heading=False, bib=False, in_table=False,
                                  col=-1, col_name="", header_valid=False),
                             fake)["status"] == "UNSOURCED"
    ok = ok and bare_ok
    print("[selftest] 裸指标不放行 -> %s  %s"
          % ("UNSOURCED" if bare_ok else "被误放行", "PASS" if bare_ok else "FAIL"))

    print("[selftest] 结论: %s" % ("全部 PASS" if ok else "存在 FAIL"))
    return 0 if ok else 1


# ============================================================ main
def main():
    ap = argparse.ArgumentParser(
        description="文档实测数字 ↔ 产物数值一致性门禁"
                    "（只有指标类 UNSOURCED 影响退出码）")
    ap.add_argument("docs", nargs="*", default=None,
                    help="待检查的文档路径, 可传 0 到多个"
                         "(默认 %s)" % "、".join(os.path.basename(p)
                                              for p in DEFAULT_DOCS))
    ap.add_argument("--report", default=None,
                    help="报告输出路径(默认同目录 %s)" % REPORT_NAME)
    ap.add_argument("--selftest", action="store_true",
                    help="只跑判定逻辑自证, 不读产物也不写报告")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    doc_paths = [os.path.normpath(p) for p in (args.docs or DEFAULT_DOCS)]
    missing = [p for p in doc_paths if not os.path.exists(p)]
    if missing:
        for p in missing:
            print("[check] 文档不存在: %s" % p)
        return 2

    sources, files = collect_sources()
    audits = [(p, audit(p, sources)) for p in doc_paths]
    out_path = args.report or os.path.join(HERE, REPORT_NAME)
    total, n_bad = write_report(audits, sources, files, out_path)

    print("=" * 72)
    print("[check] 产物来源  : %d 个文件 / %d 个数值叶子" % (len(files), len(sources)))
    for doc_path, rows in audits:
        counts = {s: 0 for s in STATUS_ORDER}
        for r in rows:
            counts[r["status"]] += 1
        bad = [r for r in rows if r["status"] == "UNSOURCED" and r["metric"]]
        print("-" * 72)
        print("[check] 文档      : %s" % doc_path)
        print("[check] 数值断言  : %d 处" % len(rows))
        print("[check] OK=%d  ROUNDED=%d  STRUCTURAL=%d  EXTERNAL=%d  CITED=%d  "
              "ALLOWED=%d  UNSOURCED=%d"
              % (counts["OK"], counts["ROUNDED"], counts["STRUCTURAL"],
                 counts["EXTERNAL"], counts["CITED"], counts["ALLOWED"],
                 counts["UNSOURCED"]))
        print("[check] 指标类 UNSOURCED（致命）= %d" % len(bad))
        for r in bad:
            print("           L%-5d %-10s %s" % (r["line"], r["raw"],
                                                r["context"][:64]))
    print("-" * 72)
    print("[check] 合计断言  : %d 处" % total["n_claims"])
    print("[check] 合计致命  : %d 条" % n_bad)
    print("[check] 报告      : %s" % out_path)
    print("=" * 72)
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
