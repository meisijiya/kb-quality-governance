# -*- coding: utf-8 -*-
"""
derived_metrics.py -- 把方案文档里所有「由产物数字算出来」的派生量变成机读列（可复算版）

动机: 论文/答辩铁律要求「所有数字只能从机读产物读出, 禁止在正文里手算差值」。
但现有产物 (results_auc.csv / ablation.csv / corrupt_rule_ablation.csv / ...) 只落了
原始观测值, 文档里引用的差值、均值、标准差、极差全部是「正文手算」, 门禁脚本
check_numbers.py 无法机读核验。本脚本把这些派生量全部重算一遍并落成一张长表。

口径说明（严格取自产物自身的列, 不做任何为了对文档的调参）:
  * 一切数值一律从既有产物文件读入后现算, 脚本内不硬编码任何结果值。
  * 标准差统一用样本标准差 (ddof=1, n-1)。
  * 「落后基线 / 领先基线」一律取正数幅度, 方向写进 derived_key 与 formula。
  * 阈值换算: results_auc.csv / ablation.csv 的 ABS 行阈值是以 -cover 记的分数刻度
    (分数越高越像缺口), 换算到 cover 刻度即取负号。
  * 算不出来的 (输入不存在或口径对不上) 一律不落行, 只打印 SKIP <key> <原因>。

产出:
  derived_metrics.csv  列 = derived_key, value, formula, inputs, source_files
                      inputs 用 | 分隔的 name=value, 可逐条手算复现 value。

运行: python derived_metrics.py   (无随机性, 重复运行 CSV 与终端输出完全一致)
"""
import csv
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STD = os.path.join(HERE, "standardize")
OUT_CSV = os.path.join(HERE, "derived_metrics.csv")

sys.stdout.reconfigure(encoding="utf-8")

DIRECTION_C_SCENARIOS = ["alpha", "beta", "gamma", "gamma-X"]   # results_directionC.csv 无 delta 行
DIRECTION_B_SCENARIOS = ["alpha", "beta", "gamma", "gamma-X"]   # results_directions.csv 无 delta 行
ALL_ABS_SCENARIOS = ["alpha", "beta", "gamma", "gamma-X", "delta"]


# --------------------------------------------------------------------------- #
# 输出累积
# --------------------------------------------------------------------------- #
ROWS = []
SKIPS = []
VALUES = {}   # derived_key -> float, 供同一脚本内的派生量互相引用


def fmt(x):
    """数值格式化: 整数原样, 其余保留 6 位小数 —— 保证 value 可由 inputs 手算复现。"""
    f = float(x)
    if f == int(f):
        return str(int(f))
    return "{:.6f}".format(round(f, 6))


def add(key, value, formula, inputs, sources):
    """inputs: [(name, value), ...]; sources: [产物文件名, ...]"""
    VALUES[key] = float(value)
    ROWS.append({
        "derived_key": key,
        "value": fmt(value),
        "formula": formula,
        "inputs": "|".join("{}={}".format(n, fmt(v)) for n, v in inputs),
        "source_files": ";".join(sources),
    })


def skip(key, reason):
    SKIPS.append((key, reason))


def read_csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_csv_sections(path):
    """ablation.csv 是多段表 (段内各自带表头), 返回 [(表头list, 数据行list), ...]。"""
    sections = []
    header, body = None, []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if not any(x.strip() for x in row):
                continue
            if row[0].strip() == "变体":
                if header is not None:
                    sections.append((header, body))
                header, body = row, []
            else:
                if header is None:
                    header = ["列%d" % i for i in range(len(row))]
                body.append(row)
    if header is not None:
        sections.append((header, body))
    return sections


def as_dicts(header, body):
    return [dict(zip(header, r)) for r in body]


def pick_one(rows, pred, what):
    hits = [r for r in rows if pred(r)]
    if len(hits) != 1:
        skip(what, "按条件命中 %d 行（要求恰好 1 行），无法确定口径" % len(hits))
        return None
    return hits[0]


def num(s):
    return float(s)


# --------------------------------------------------------------------------- #
# 载入产物
# --------------------------------------------------------------------------- #
def load():
    d = {}
    d["auc"] = read_csv_rows(os.path.join(STD, "results_auc.csv"))
    d["dirC"] = read_csv_rows(os.path.join(STD, "results_directionC.csv"))
    d["dirs"] = read_csv_rows(os.path.join(STD, "results_directions.csv"))
    d["bk_en"] = read_csv_rows(os.path.join(STD, "results_banking77_en.csv"))
    d["bk_zh"] = read_csv_rows(os.path.join(STD, "results_banking77_zh.csv"))
    d["bk_all"] = read_csv_rows(os.path.join(STD, "results_banking77.csv"))
    abl = read_csv_sections(os.path.join(STD, "ablation.csv"))
    d["abl_head"] = as_dicts(abl[0][0], abl[0][1]) if abl else []
    d["gran"] = read_csv_rows(os.path.join(HERE, "granularity.csv"))
    d["rule"] = read_csv_rows(os.path.join(HERE, "corrupt_rule_ablation.csv"))
    d["scen"] = json.load(open(os.path.join(STD, "scenario_meta.json"), encoding="utf-8"))
    d["bk_en_meta"] = json.load(open(os.path.join(STD, "banking77_meta_en.json"), encoding="utf-8"))
    d["bk_zh_meta"] = json.load(open(os.path.join(STD, "banking77_meta_zh.json"), encoding="utf-8"))
    d["gt"] = json.load(open(os.path.join(HERE, "ground_truth.json"), encoding="utf-8"))
    d["emb"] = json.load(open(os.path.join(HERE, "embeddings_meta.json"), encoding="utf-8"))
    d["docs"] = read_csv_rows(os.path.join(HERE, "docs.csv"))
    return d


def read_log_encode_seconds(path):
    """从 run_all*.log 的 '[embed] ... 向量化耗时 = 14.9s' 读向量化秒数。"""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.search(r"向量化耗时\s*=\s*([0-9.]+)\s*s", line)
            if m:
                return float(m.group(1))
    return None


# --------------------------------------------------------------------------- #
# 各类派生量
# --------------------------------------------------------------------------- #
def thr_range_all_scenarios(d):
    """ABS 绝对阈值在 5 个自造场景上的极差 (文档 0.0264)。"""
    src = "standardize/results_auc.csv"
    ths = []
    for sc in ALL_ABS_SCENARIOS:
        r = pick_one(d["auc"], lambda r, s=sc: r["场景"] == s and r["方法"].startswith("ABS"),
                     "threshold.abs.%s" % sc)
        if r is None:
            return
        ths.append((sc, num(r["召回全部门槛的阈值"])))
    hi = max(ths, key=lambda t: t[1])
    lo = min(ths, key=lambda t: t[1])
    add("threshold.abs_5scenario_range",
        hi[1] - lo[1],
        "max({}) - min({}) = {} - ({})".format(
            ",".join(str(t[1]) for t in ths), ",".join(str(t[1]) for t in ths),
            hi[1], lo[1]),
        ths, [src])


def direction_c_abs(d):
    """方向 C 基线: 4 场景 ABS 最优 F1 的均值与样本标准差 (文档 0.8289 / 0.1452)。"""
    src = "standardize/results_auc.csv"
    f1s = []
    for sc in DIRECTION_C_SCENARIOS:
        r = pick_one(d["auc"], lambda r, s=sc: r["场景"] == s and r["方法"].startswith("ABS"),
                     "dirC.abs.%s" % sc)
        if r is None:
            return
        f1s.append((sc, num(r["best_F1"])))
    vals = [v for _, v in f1s]
    add("directionC.abs_mean_f1_4scenario", sum(vals) / len(vals),
        "mean({}) = {} / {}".format(",".join(str(v) for v in vals),
                                     " + ".join(str(v) for v in vals), len(vals)),
        f1s, [src])
    add("directionC.abs_sd_f1_4scenario", statistics.stdev(vals),
        "stdev(n-1) of ({}) = {:.6f}".format(",".join(str(v) for v in vals),
                                             statistics.stdev(vals)),
        f1s, [src])


def direction_c_fixed_ratio(d, ratio, tag):
    """方向 C 固定检出比例下的 4 场景平均 F1 与样本标准差。"""
    src = "standardize/results_directionC.csv"
    f1s = []
    for sc in DIRECTION_C_SCENARIOS:
        r = pick_one(d["dirC"], lambda r, s=sc: r["场景"] == s
                     and abs(num(r["固定检出比例"]) - ratio) < 1e-9,
                     "dirC.fixed.%s.%s" % (tag, sc))
        if r is None:
            return
        f1s.append((sc, num(r["F1"])))
    vals = [v for _, v in f1s]
    add("directionC.fixed%s_mean_f1_4scenario" % tag, sum(vals) / len(vals),
        "mean({}) = {} / {}".format(",".join(str(v) for v in vals),
                                     " + ".join(str(v) for v in vals), len(vals)),
        f1s, [src])
    add("directionC.fixed%s_sd_f1_4scenario" % tag, statistics.stdev(vals),
        "stdev(n-1) of ({}) = {:.6f}".format(",".join(str(v) for v in vals),
                                             statistics.stdev(vals)),
        f1s, [src])


def direction_c_ratio_sweep(d):
    """其余固定比例的曲线值 (文档 0.0883 等佐证数字)。"""
    for ratio, tag in [(0.10, "10"), (0.15, "15"), (0.1855, "18p55")]:
        direction_c_fixed_ratio(d, ratio, tag)


def threshold_cover_scale(d):
    """ABS 阈值从 -cover 分数刻度换算到 cover 刻度 (文档 0.6463 / 0.6657)。"""
    r = pick_one(d["auc"], lambda r: r["场景"] == "alpha" and r["方法"].startswith("ABS"),
                 "threshold.abs_alpha.cover_scale")
    if r is not None:
        t = num(r["召回全部门槛的阈值"])
        add("threshold.abs_alpha_recall_all_cover_scale", -t,
            "-1 * ({}) = cover <= {:.6f}".format(t, -t),
            [("results_auc.alpha.ABS.召回全部门槛的阈值", t)],
            ["standardize/results_auc.csv"])
    ra = pick_one(d["abl_head"], lambda r: r["变体"].startswith("ABS"),
                  "ablation.abs.cover_scale")
    if ra is not None:
        t = num(ra["最优阈值"])
        add("threshold.abs_alpha_best_cover_scale", -t,
            "-1 * ({}) = cover <= {:.6f}".format(t, -t),
            [("ablation.ABS 绝对余弦.最优阈值", t)],
            ["standardize/ablation.csv"])


def cover_scale_gap(d):
    """banking77 英文语料最优 cover 刻度 vs 中文合成语料 (文档 0.8495 / 0.6463 / 0.2032)。"""
    en = pick_one(d["bk_en"], lambda r: r["子场景"] == "全量" and r["方法"].startswith("ABS"),
                  "banking77_en.abs_best_threshold")
    zh_best = pick_one(d["abl_head"], lambda r: r["变体"].startswith("ABS"),
                       "ablation.abs.cover_scale")
    if en is None or zh_best is None:
        return
    t_en, t_zh = num(en["最优阈值"]), num(zh_best["最优阈值"])
    add("banking77_en.abs_best_threshold_raw", t_en,
        "results_banking77_en.csv 全量/ABS 的 最优阈值 原值 (未换算)",
        [("results_banking77_en.全量.ABS.最优阈值", t_en)],
        ["standardize/results_banking77_en.csv"])
    add("banking77_en.abs_best_cover_scale", -t_en,
        "-1 * ({}) = cover <= {:.6f}".format(t_en, -t_en),
        [("results_banking77_en.全量.ABS.最优阈值", t_en)],
        ["standardize/results_banking77_en.csv"])
    add("banking77_en.cover_scale_gap_vs_zh_alpha", (-t_en) - (-t_zh),
        "{} - {} = cover_scale(banking77_en) - cover_scale(alpha)".format(-t_en, -t_zh),
        [("banking77_en.ABS.最优阈值(cover刻度)", -t_en),
         ("alpha.ABS.最优阈值(cover刻度)", -t_zh)],
        ["standardize/results_banking77_en.csv", "standardize/ablation.csv"])


def cover_mean_gaps(d):
    """banking77 两模型覆盖度均值与中文合成语料 α 的差 (文档 0.1495 / 0.1906 / 0.0411)。"""
    srcs = ["standardize/banking77_meta_en.json", "standardize/banking77_meta_zh.json",
            "standardize/scenario_meta.json"]
    if "alpha" not in d["scen"]["cover_stats"]:
        skip("cover.alpha_mean", "scenario_meta.json cover_stats 无 alpha 场景")
        return
    base = d["scen"]["cover_stats"]["alpha"]["mean"]
    en = d["bk_en_meta"]["cover"]["mean"]
    zh = d["bk_zh_meta"]["cover"]["mean"]
    add("cover.banking77_en_mean_minus_alpha_mean", en - base,
        "{} - {} = banking77_en 覆盖度均值 - 中文合成 alpha 均值".format(en, base),
        [("banking77_en.cover.mean", en), ("alpha.cover.mean", base)], srcs)
    add("cover.banking77_zh_mean_minus_alpha_mean", zh - base,
        "{} - {} = banking77_zh 覆盖度均值 - 中文合成 alpha 均值".format(zh, base),
        [("banking77_zh.cover.mean", zh), ("alpha.cover.mean", base)], srcs)
    add("cover.banking77_en_minus_zh_mean", en - zh,
        "{} - {} = bge-small-en 与 bge-small-zh 覆盖度均值差".format(en, zh),
        [("banking77_en.cover.mean", en), ("banking77_zh.cover.mean", zh)], srcs)


def s3_auc_gaps(d):
    """S3 领域内 z 相对 ABS 基线的 AUC 差 (文档 0.0320 / 0.5194 / 0.2979)。"""
    r_base = pick_one(d["auc"], lambda r: r["场景"] == "alpha" and r["方法"].startswith("ABS"),
                      "s3.alpha.abs_auc")
    r_s3 = pick_one(d["auc"], lambda r: r["场景"] == "alpha" and r["方法"].startswith("S3 "),
                    "s3.alpha.s3_auc")
    if r_base and r_s3:
        b, s = num(r_base["AUC"]), num(r_s3["AUC"])
        add("auc.s3_alpha_lead_over_abs_baseline", s - b,
            "{} - {} = S3 领域内z α AUC - ABS 基线 α AUC (领先为正)".format(s, b),
            [("alpha.S3.领域内z.AUC", s), ("alpha.ABS.AUC", b)],
            ["standardize/results_auc.csv"])
    for tag, rows, src in [("banking77_en", d["bk_en"], "standardize/results_banking77_en.csv"),
                           ("banking77_zh", d["bk_zh"], "standardize/results_banking77_zh.csv")]:
        rb = pick_one(rows, lambda r: r["子场景"] == "全量" and r["方法"].startswith("ABS"),
                      "s3.%s.abs" % tag)
        rs = pick_one(rows, lambda r: r["子场景"] == "全量" and r["方法"].startswith("S3 "),
                      "s3.%s.s3" % tag)
        if rb and rs:
            b, s = num(rb["AUC"]), num(rs["AUC"])
            add("auc.s3_%s_lag_over_abs_baseline" % tag, b - s,
                "{} - {} = ABS 全量 AUC - S3 全量 AUC (落后为正)".format(b, s),
                [("%s.ABS.全量.AUC" % tag, b), ("%s.S3.全量.AUC" % tag, s)], [src])


def direction_b_lag(d):
    """方向 B 相对基线的落后幅度 (文档 0.1520 / 0.1802 / 0.2600 / 0.1635)。"""
    src = "standardize/results_directions.csv"
    for sc in DIRECTION_B_SCENARIOS:
        rb = pick_one(d["dirs"], lambda r, s=sc: r["方向"].startswith("ABS")
                      and r["场景"] == s, "dirB.base.%s" % sc)
        rB = pick_one(d["dirs"], lambda r, s=sc: r["方向"].startswith("B 双向中心化")
                      and r["场景"] == s, "dirB.b.%s" % sc)
        if not rb or not rB:
            continue
        b, v = num(rb["AUC"]), num(rB["AUC"])
        add("directionB.%s_lag_over_abs_baseline" % sc, b - v,
            "{} - {} = ABS 基线 AUC - 方向B AUC (落后为正)".format(b, v),
            [("%s.ABS.AUC" % sc, b), ("%s.方向B.AUC" % sc, v)], [src])


def direction_a2(d):
    """方向 A2 的跨场景阈值极差与 AUC (文档 0.0018 / 0.1120)。"""
    src = "standardize/results_directions.csv"
    ths, aucs = [], []
    for sc in DIRECTION_B_SCENARIOS:
        r = pick_one(d["dirs"], lambda r, s=sc: r["方向"].startswith("A2") and r["场景"] == s,
                     "a2.%s" % sc)
        if r is None:
            return
        ths.append((sc, num(r["召回全部阈值"])))
        aucs.append((sc, num(r["AUC"])))
    tv = [v for _, v in ths]
    av = [v for _, v in aucs]
    add("directionA2.4scenario_threshold_range", max(tv) - min(tv),
        "max({}) - min({})".format(",".join(str(v) for v in tv), ",".join(str(v) for v in tv)),
        ths, [src])
    add("directionA2.alpha_auc", av[0],
        "alpha 场景 A2 的 AUC 原值", [aucs[0]], [src])


def rule_ablation_drops(d):
    """规则消融的 ΔF1 幅度 (文档 0.2609 / 0.2657, 文档写正数, 产物为负)。"""
    src = "corrupt_rule_ablation.csv"
    base = pick_one(d["rule"], lambda r: r["setting"] == "all", "rule.all")
    if base is None:
        return
    f1_all = num(base["f1"])
    for st in ["drop_R1", "drop_R2", "drop_R3", "drop_R4", "only_R1", "only_R2"]:
        r = pick_one(d["rule"], lambda r, s=st: r["setting"] == s, "rule.%s" % st)
        if r is None:
            continue
        if r["delta_f1"].strip() == "":
            continue
        delta = num(r["delta_f1"])
        direction = ("无变化 (F1({}) = F1(all))".format(st) if delta == 0 else
                     "F1({}) 低于 F1(all)".format(st))
        add("rule_ablation.%s_f1_drop_magnitude" % st, abs(delta),
            "abs({}) ; 产物 delta_f1 为负表示 F1 下降, 此处取正数幅度, 方向 = {}".format(
                delta, direction),
            [("%s.f1" % st, num(r["f1"])), ("all.f1", f1_all)], [src])


def granularity_gain(d):
    """段落级相对整篇级的 AUC 提升。

    granularity.csv 的两列口径不同:
      auc              = 工单级 AUC   (文档 0.0352 = 0.8659 - 0.8307)
      auc_intent_median = 意图级 AUC  (文档 0.0800 / 相对提升 9.0%)
    """
    src = "granularity.csv"

    def get(gran, col):
        r = pick_one(d["gran"], lambda r: r["granularity"] == gran
                     and r["score_scheme"] == "max-cosine", "gran.%s" % gran)
        return None if r is None else num(r[col])

    p, q = get("passage_level", "auc_intent_median"), get("doc_level", "auc_intent_median")
    if p is None or q is None:
        return
    add("granularity.intent_auc_passage_minus_doc", p - q,
        "{} - {} = 段落级意图级 AUC - 整篇级意图级 AUC".format(p, q),
        [("passage_level.max-cosine.auc_intent_median", p),
         ("doc_level.max-cosine.auc_intent_median", q)], [src])
    add("granularity.intent_auc_relative_gain", (p - q) / q,
        "({} - {}) / {} = 相对提升比例".format(p, q, q),
        [("passage_level.max-cosine.auc_intent_median", p),
         ("doc_level.max-cosine.auc_intent_median", q)], [src])

    tp, tq = get("passage_level", "auc"), get("doc_level", "auc")
    if tp is None or tq is None:
        return
    add("granularity.ticket_auc_passage_minus_doc", tp - tq,
        "{} - {} = 段落级工单级 AUC - 整篇级工单级 AUC".format(tp, tq),
        [("passage_level.max-cosine.auc", tp),
         ("doc_level.max-cosine.auc", tq)], [src])


def ground_truth_ratios(d):
    """ground_truth.json 里的比例量 (文档 18.6%)。"""
    gt = d["gt"]
    cnt, tot = gt.get("gap_ticket_count"), gt.get("n_tickets")
    if cnt is None or tot is None:
        skip("ground_truth.gap_ticket_ratio", "ground_truth.json 缺 gap_ticket_count 或 n_tickets")
        return
    add("ground_truth.gap_ticket_ratio", cnt / tot,
        "{} / {} = 缺口工单数 / 工单总数 (与 ground_truth.gap_ticket_ratio 同值, 此处为重算)".format(
            cnt, tot),
        [("ground_truth.gap_ticket_count", cnt), ("ground_truth.n_tickets", tot)],
        ["ground_truth.json"])


def embedding_counts(d):
    """向量化条数与段落/篇比 (文档 6.2 段/篇、4152 条)。"""
    e = d["emb"]
    n_docs, n_tk, n_ps = e.get("n_docs"), e.get("n_tickets"), e.get("n_passages")
    if None in (n_docs, n_tk, n_ps):
        skip("embedding.counts", "embeddings_meta.json 缺 n_docs / n_tickets / n_passages")
        return
    add("embedding.total_texts_vectorized", n_docs + n_tk + n_ps,
        "{} + {} + {} = 文档 + 工单 + 段落 三类文本条数".format(n_docs, n_tk, n_ps),
        [("n_docs", n_docs), ("n_tickets", n_tk), ("n_passages", n_ps)],
        ["embeddings_meta.json"])
    add("embedding.passages_per_doc", n_ps / n_docs,
        "{} / {} = 段落数 / 文档数".format(n_ps, n_docs),
        [("n_passages", n_ps), ("n_docs", n_docs)], ["embeddings_meta.json"])


def docs_text_stats(d):
    """正文平均句数与平均字数（文档 5.2 句 / 140 字、长度区间 111–191 字）。"""
    docs = d.get("docs")
    if not docs:
        skip("docs.avg_sentences_per_doc", "docs.csv 不可读或无数据行")
        return
    sents = [len([s for s in re.split(r"[。；]", r.get("content", "")) if s.strip()])
             for r in docs]
    chars = [len(r.get("content", "")) for r in docs]
    n = len(docs)
    add("docs.avg_sentences_per_doc", sum(sents) / n,
        "sum(len(split(content, '。；'))) / {} = 300 篇正文按 。与 ； 切分后的句数均值".format(n),
        [("句数合计", sum(sents)), ("文档数", n)], ["docs.csv"])
    add("docs.avg_chars_per_doc", sum(chars) / n,
        "sum(len(content)) / {} = 300 篇正文平均字数".format(n),
        [("字数合计", sum(chars)), ("文档数", n)], ["docs.csv"])
    add("docs.min_chars_per_doc", min(chars), "min(len(content))", [], ["docs.csv"])
    add("docs.max_chars_per_doc", max(chars), "max(len(content))", [], ["docs.csv"])


def throughput(d):
    """向量化吞吐 (条/秒), 分别取首跑日志与复跑 embeddings_meta。"""
    total = d["emb"].get("n_docs", 0) + d["emb"].get("n_tickets", 0) + d["emb"].get("n_passages", 0)
    first = read_log_encode_seconds(os.path.join(HERE, "run_all.log"))
    if first:
        add("embedding.throughput_texts_per_sec_first_run", total / first,
            "{} / {} = 总条数 / 首跑向量化耗时(run_all.log)".format(total, first),
            [("total_texts", total), ("run_all.log 向量化耗时(秒)", first)],
            ["embeddings_meta.json", "run_all.log"])
    else:
        skip("embedding.throughput_texts_per_sec_first_run",
             "run_all.log 中未匹配到「向量化耗时 = Ns」")
    enc = d["emb"].get("encode_seconds")
    if enc:
        add("embedding.throughput_texts_per_sec_repro", total / enc,
            "{} / {} = 总条数 / embeddings_meta.encode_seconds".format(total, enc),
            [("total_texts", total), ("encode_seconds", enc)],
            ["embeddings_meta.json"])


# --------------------------------------------------------------------------- #
# 派生量之间的二次派生 (仍全部由同一批产物数字推出)
# --------------------------------------------------------------------------- #
def direction_c_tradeoff(d):
    """方向 C 的稳定性/牺牲比例 (文档「稳 40%, 即 39.9%」与「牺牲 33%」)。"""
    srcs = ["standardize/results_directionC.csv", "standardize/results_auc.csv"]
    sd_base = VALUES.get("directionC.abs_sd_f1_4scenario")
    sd_fix = VALUES.get("directionC.fixed25_sd_f1_4scenario")
    m_base = VALUES.get("directionC.abs_mean_f1_4scenario")
    m_fix = VALUES.get("directionC.fixed25_mean_f1_4scenario")
    if None in (sd_base, sd_fix, m_base, m_fix):
        skip("directionC.stability_and_sacrifice",
             "上游 directionC.* 均值/标准差未算出, 无法继续推导")
        return
    add("directionC.sd_reduction_ratio_fixed25", 1 - sd_fix / sd_base,
        "1 - {} / {} = 1 - sd(固定25%)/sd(ABS) = 稳定性改善比例".format(sd_fix, sd_base),
        [("sd_f1_fixed25", sd_fix), ("sd_f1_abs", sd_base)], srcs)
    add("directionC.mean_f1_sacrifice_ratio_fixed25", 1 - m_fix / m_base,
        "1 - {} / {} = 1 - meanF1(固定25%)/meanF1(ABS) = 平均 F1 牺牲比例".format(m_fix, m_base),
        [("mean_f1_fixed25", m_fix), ("mean_f1_abs", m_base)], srcs)


# --------------------------------------------------------------------------- #
# 明确算不出来 / 口径不成立的项 —— 必须显式 SKIP, 不许静默
# --------------------------------------------------------------------------- #
def report_uncomputable(d):
    mb = d["emb"].get("model_download_mb")
    skip("model.disk_size_mb",
         "embeddings_meta.json 只有 model_download_mb={} (下载标称体积), "
         "没有任何产物记录实测落盘体积, 文档的 92MB 无机读出处".format(mb))

    ths = []
    for logname in ["run_all.log", "run_all_repro.log"]:
        t = read_log_encode_seconds(os.path.join(HERE, logname))
        if t:
            ths.append(t)
    total = d["emb"].get("n_docs", 0) + d["emb"].get("n_tickets", 0) + d["emb"].get("n_passages", 0)
    skip("embed.throughput_range_tickets_per_sec",
         "文档写的区间 120-275 条/秒 无机读出处; 产物只能给出单点: 首跑 {}条/{}s, "
         "复跑 {}条/{}s, 区间上下界需人为取整, 不落行".format(
             total, ths[0] if ths else "n/a", total,
             d["emb"].get("encode_seconds", "n/a")))

    skip("pipeline.full_chain_upper_bound_seconds",
         "文档的 110 秒是人工设定的性能承诺上界, 任何产物里都没有「全链路上界」这个观测值, "
         "既非均值也非极值, 无法由产物推出")


def main():
    d = load()
    thr_range_all_scenarios(d)
    direction_c_abs(d)
    direction_c_fixed_ratio(d, 0.25, "25")
    direction_c_fixed_ratio(d, 0.30, "30")
    direction_c_ratio_sweep(d)
    direction_c_tradeoff(d)
    threshold_cover_scale(d)
    cover_scale_gap(d)
    cover_mean_gaps(d)
    s3_auc_gaps(d)
    direction_b_lag(d)
    direction_a2(d)
    rule_ablation_drops(d)
    granularity_gain(d)
    ground_truth_ratios(d)
    embedding_counts(d)
    docs_text_stats(d)
    throughput(d)
    report_uncomputable(d)

    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["derived_key", "value", "formula", "inputs",
                                          "source_files"])
        w.writeheader()
        for r in ROWS:
            w.writerow(r)

    for r in ROWS:
        print("{} = {}   [{}]".format(r["derived_key"], r["value"], r["formula"]))
    print("")
    for key, reason in SKIPS:
        print("SKIP {} {}".format(key, reason))
    print("")
    print("派生指标 {} 条 / 跳过 {} 条".format(len(ROWS), len(SKIPS)))
    print("输出: {}".format(OUT_CSV))


if __name__ == "__main__":
    main()