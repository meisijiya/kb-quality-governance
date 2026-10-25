#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_worklist.py -- 生成「人工标注工作单」：A 卷（全量）与 B 卷（重叠子集）

用途
----
为本科毕设项目《基于语义聚类与时效性分析的企业知识库质量治理系统设计与实现》
的人工标注环节生成**可复算、可机读、盲化**的标注材料。

口径（与 `.scratch/caliber_dictionary.md` 一致）
---------------------------------------------
1. **内容腐化拆成两个独立口径**，各自独立判定、各自报 P/R/F1，不合成单一 F1：
   - **内容过期**：正文写明的口径 / 日期 / 金额 / 条款本身是否已被取代或失效；
   - **维护周期**：距基准日超过 18 个月未更新，**且**同域已有更新版本。
2. **缺口判定单元 = 业务意图**（不是意图簇）。标注对象是**全部 30 个业务意图**，
   意图级覆盖度按「各簇覆盖度取最小值」聚合（min 聚合）。
3. **腐化类工作单双标签 + 盲化**：每条腐化条目给两个互不影响的问题；
   工作单里不含任何系统判定字段（rule_hits / risk_score / cause_score_* / reasons /
   fp_reason / in_control_sample / is_dup_copy / dup_source 等一律不进工作单）。

输入（只读，全部位于上一级目录 poc/kbgovernance/）
    docs.csv                300 篇文档
    tickets.csv             2000 条工单
    doc_emb.npy             300×512 文档级向量（与 docs.csv 行序一一对应）
    ticket_emb.npy          2000×512 工单级向量（与 tickets.csv 行序一一对应）
    gap_clusters_best.csv   95 行意图簇明细（全部 30 个业务意图）
    gap_intents_best.csv    5 行意图级缺口清单（与上表聚合结果一致，用于交叉核对）
    corrupt_docs.csv        300 行腐化检测明细（只用来分层抽样，判定字段不外泄）
    dup_groups_best.csv     22 行重复组清单
    ground_truth.json       参考真值（只用于 --score，脚本在评分时现场推导，不落盘）

输出（本目录）
    worklist_A.csv        全部条目（300 条）
    worklist_B.csv        100 条重叠子集（供第二标注者独立标注）

用法
----
    python make_worklist.py
    python make_worklist.py --score --a worklist_A_filled.csv --b worklist_B_filled.csv

抽样方法（确定性）
------------------
1. 候选集合一律先按主键升序排序（doc_id / ticket_id / cluster_id / group），
   保证「同键 → 同序」，与磁盘上的文件行序无关；
2. 再用 ``random.Random(42).sample(候选, k)`` 无放回抽样；
3. 随机种子固定为 42：同一份输入必然产出逐字节相同的工作单。
   分层抽样时按固定的分层顺序依次取样，复用同一个 ``Random(42)`` 实例。

各层抽样规模
------------
    文档内容合理性   30 / 300   全体按 doc_id 升序后无放回抽 30
    工单内容合理性  200 / 2000  全体按 ticket_id 升序后无放回抽 200
    缺口清单         30 / 30    全部 30 个业务意图全量纳入（无抽样空间）
    腐化清单         20 / 69    在「系统已给出判定」的 69 行里按四象限分层抽 20
    重复清单         20 / 22    全体按 group 升序后无放回抽 20

    腐化清单的分层配额（固定顺序，复用同一个 Random(42)）：
        内容过期×维护周期 双命中            1
        只命中内容过期                       9
        只命中维护周期                      10
        两口径均未命中但被系统判过              0（该象限实际为空）
        合计                                 20

B 卷选样规则
------------
1. **缺陷清单条目全量覆盖**：缺口 30 + 腐化 20 + 重复 20 = 70 条；
2. 剩余 30 条补内容合理性条目：文档类 15 条 + 工单类 15 条；
3. 合计 **100 条**；
4. B 卷这 100 条的 judge_question 与 material 与 A 卷**逐字一致**，
   但 decision / decision_content_expiry / decision_maintenance / reason /
   annotator / annotated_at 六列各自留空、互不可见；
   两个标注者的结果只在评分阶段（--score）汇总。

盲化约定
--------
* 腐化类工作单只给**可读材料**：标题、领域、正文、最后修改日期、语料基准日，
  以及「同域篇数 / 同域同一业务意图的文档清单（编号 + 最后修改日期 + 标题）」
  这一**中性事实**；
* 工作单里**不出现任何参考真值列**，也**不落盘答案表**；
* 评分所需的参考真值在 ``--score`` 模式下现场从源产物推导，不写回工作单。

换行符约定（对齐仓库 .gitattributes：*.csv 走 CRLF 且 -text，*.py 走 LF）
---------------------------------------------------------------------------
"""
import argparse
import csv
import json
import os
import random
import re
import sys
from collections import Counter, OrderedDict, defaultdict

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)                       # poc/kbgovernance/
OUT_A = os.path.join(HERE, "worklist_A.csv")
OUT_B = os.path.join(HERE, "worklist_B.csv")

SEED = 42
NL = "\r\n"                                     # CSV 行内换行（保持整文件 CRLF）

FIELDS = ["item_id", "category", "source_ref", "judge_question",
          "material", "decision", "decision_content_expiry",
          "decision_maintenance", "reason", "annotator", "annotated_at"]

C_DOC = "文档内容合理性"
C_TKT = "工单内容合理性"
C_GAP = "缺口清单"
C_COR = "腐化清单"
C_DUP = "重复清单"

CATEGORY_ORDER = [C_DOC, C_TKT, C_GAP, C_COR, C_DUP]

# 各类的合法判定取值（与 annotation_rules.md 一致）
LEGAL_DECISIONS = OrderedDict([
    (C_DOC, ["合理", "不合理", "无法判断"]),
    (C_TKT, ["合理", "不合理", "无法判断"]),
    (C_GAP, ["是真缺口", "不是真缺口", "无法判断"]),
    (C_DUP, ["是真重复组", "不是真重复组", "无法判断"]),
])
# 腐化类是双标签：两个口径各自独立作答
LEGAL_CONTENT_EXPIRY = ["正文已过期", "正文未过期", "无法判断"]
LEGAL_MAINTENANCE = ["维护状态已失控", "维护状态正常", "无法判断"]

# 缺口条目：每条给出几篇候选文档
GAP_CANDIDATE_DOCS = 3
# 腐化条目：四象限分层配额（固定顺序）
CORRUPT_QUOTA = [
    ("内容过期×维护周期（双命中）", 1),
    ("只命中内容过期", 9),
    ("只命中维护周期", 10),
    ("两口径均未命中但被系统判过", 0),
]


# ----------------------------------------------------------------- 读源产物
def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_sources():
    src = {
        "docs": read_csv(os.path.join(KB, "docs.csv")),
        "tickets": read_csv(os.path.join(KB, "tickets.csv")),
        "clusters": read_csv(os.path.join(KB, "gap_clusters_best.csv")),
        "gap_intents_csv": read_csv(os.path.join(KB, "gap_intents_best.csv")),
        "corrupt": read_csv(os.path.join(KB, "corrupt_docs.csv")),
        "dups": read_csv(os.path.join(KB, "dup_groups_best.csv")),
    }
    with open(os.path.join(KB, "ground_truth.json"), "r", encoding="utf-8") as f:
        src["ground_truth"] = json.load(f)

    src["docs_by_id"] = {d["doc_id"]: d for d in src["docs"]}
    src["tickets_by_id"] = {t["ticket_id"]: t for t in src["tickets"]}
    src["corrupt_by_id"] = {r["doc_id"]: r for r in src["corrupt"]}

    # 落盘向量（embed.py 产出，顺序与 CSV 行序一致）：用于挑选缺口条目的候选文档
    src["doc_emb"] = np.load(os.path.join(KB, "doc_emb.npy"))
    src["ticket_emb"] = np.load(os.path.join(KB, "ticket_emb.npy"))
    if len(src["doc_emb"]) != len(src["docs"]) or len(src["ticket_emb"]) != len(src["tickets"]):
        raise ValueError("向量行数与 CSV 行数不一致，doc_emb/ticket_emb 与源表可能不同版本")

    idx = defaultdict(list)
    for i, t in enumerate(src["tickets"]):
        idx[t["intent_label"]].append(i)
    src["ticket_idx_by_intent"] = dict(idx)

    # 文档所属业务意图：标题里出现的业务意图名（与工单 intent_label 同一套名称）。
    # 用于「同域同主题文档清单」——清单必须是人能一眼看懂的事实，不能是黑箱指标。
    intent_names = sorted(src["ticket_idx_by_intent"])
    src["doc_intent"] = {}
    for d in src["docs"]:
        hit = [n for n in intent_names if n in d["title"]]
        if len(hit) != 1:
            raise ValueError("文档 %s 的标题未能唯一匹配业务意图名：%s" % (d["doc_id"], hit))
        src["doc_intent"][d["doc_id"]] = hit[0]
    return src


# ----------------------------------------------------------------- 通用小工具
def take(rng, population, k, key=None):
    """候选集合已按主键升序排好；无放回抽 k 条，返回值同样按主键升序。"""
    k = min(k, len(population))
    picked = rng.sample(list(population), k)
    return sorted(picked, key=key) if key else sorted(picked)


def split_passages(text, min_len=8):
    """段落切分：与 poc/kbgovernance/embed.py 的 split_passages 保持同一口径。

    切分规则必须与段落级覆盖度的计算一致，否则标注者看到的段落号与
    系统算覆盖度时用的段落不是同一批。
    """
    parts = [p.strip() for p in re.split(r"[。；]", text)
             if len(p.strip()) >= min_len]
    return parts or [text]


def f4(x):
    return "%.4f" % float(x)


# ----------------------------------------------------------------- 缺口条目
def aggregate_intents(clusters):
    """从 gap_clusters_best.csv 聚合全部业务意图的意图级读数。

    意图级覆盖度 = 该意图下各簇 cover_median 的最小值（min 聚合）。
    """
    by = OrderedDict()
    for c in clusters:
        d = by.setdefault(c["intent"], {"intent": c["intent"], "clusters": [],
                                        "total": 0})
        d["clusters"].append(c)
        d["total"] += int(c["size"])
    for d in by.values():
        d["clusters"].sort(key=lambda c: int(c["cluster_id"]))
        d["n_clusters"] = len(d["clusters"])
        d["min_cover"] = min(float(c["cover_median"]) for c in d["clusters"])
    # 顺序：意图级覆盖度从低到高（同值按意图名），最「缺」的排在前面
    return OrderedDict(sorted(by.items(), key=lambda kv: (kv[1]["min_cover"], kv[0])))


def cross_check_intents(src, intents):
    """与 gap_intents_best.csv 交叉核对（有行的那几个意图）。"""
    for row in src["gap_intents_csv"]:
        name = row["intent"]
        if name not in intents:
            raise ValueError("gap_intents_best.csv 的意图 %s 不在 gap_clusters_best.csv 的聚合里" % name)
        agg = intents[name]
        if abs(agg["min_cover"] - float(row["min_cover_median"])) > 1e-9:
            raise ValueError("意图 %s 的 min_cover_median 与 gap_clusters_best.csv 聚合不一致" % name)
        if agg["total"] != int(row["total_tickets"]):
            raise ValueError("意图 %s 的 total_tickets 与 gap_clusters_best.csv 聚合不一致" % name)
        if agg["n_clusters"] != int(row["n_clusters"]):
            raise ValueError("意图 %s 的 n_clusters 与 gap_clusters_best.csv 聚合不一致" % name)
    return True


def candidate_docs(intent, src):
    """挑候选文档：标题命中该意图的文档优先，其余按语义接近度补足。

    相似度用已落盘的 doc_emb.npy × ticket_emb.npy 计算（整篇级），
    不依赖任何模型，重跑结果一致。
    """
    docs = src["docs"]
    idx = src["ticket_idx_by_intent"].get(intent, [])
    if not idx:
        raise ValueError("意图 %s 在 tickets.csv 里没有工单" % intent)
    mean_sim = (src["ticket_emb"][idx] @ src["doc_emb"].T).mean(axis=0)
    hit = [i for i, d in enumerate(docs) if intent in d["title"]]
    rest = [int(i) for i in np.argsort(-mean_sim) if int(i) not in set(hit)]
    order = sorted(hit, key=lambda i: -float(mean_sim[i])) + rest
    return [(int(i), float(mean_sim[i])) for i in order[:GAP_CANDIDATE_DOCS]]


def build_gap_items(src):
    """缺口清单：全部 30 个业务意图各一条（判定单元 = 业务意图）。"""
    intents = aggregate_intents(src["clusters"])
    cross_check_intents(src, intents)

    items = []
    for i, (name, agg) in enumerate(intents.items(), start=1):
        clusters = agg["clusters"]
        # 代表工单：取覆盖度最低 / 中位 / 最高的三簇，覆盖该意图的诉求跨度
        by_cover = sorted(clusters, key=lambda c: float(c["cover_median"]))
        pick = [by_cover[0]]
        if len(by_cover) > 1:
            pick.append(by_cover[len(by_cover) // 2])
        if len(by_cover) > 2:
            pick.append(by_cover[-1])

        cluster_lines = []
        rep_lines = []
        for c in clusters:
            cluster_lines.append("  · 簇 {cid}：簇内工单 {size} 条，簇覆盖度 {cov}，"
                                 "代表工单 {rep}（该工单覆盖度 {rcov}）".format(
                                     cid=c["cluster_id"], size=c["size"],
                                     cov=c["cover_median"], rep=c["rep_ticket"],
                                     rcov=c["rep_cover"]))
        for c in pick:
            rep_lines.append("  · 簇 {cid} / {rep}：{txt}".format(
                cid=c["cluster_id"], rep=c["rep_ticket"], txt=c["rep_text"]))

        cand_lines = []
        for di, sim in candidate_docs(name, src):
            d = src["docs"][di]
            cand_lines.append("  · {did}（领域：{cat}）最后修改 {lm}".format(
                did=d["doc_id"], cat=d["category"], lm=d["last_modified"]))
            cand_lines.append("    标题：{t}".format(t=d["title"]))
            for pi, p in enumerate(split_passages(d["title"] + "。" + d["content"]), 1):
                cand_lines.append("    段落 {pi}：{p}".format(pi=pi, p=p))

        material = NL.join([
            "【业务意图 intent】" + name,
            "【该意图工单总数】%d" % agg["total"],
            "【参与聚合的意图簇数】%d" % agg["n_clusters"],
            "【意图级覆盖度（各簇覆盖度取最小值）】" + f4(agg["min_cover"]),
            "【意图簇明细（簇号 / 簇内工单数 / 簇覆盖度）】",
        ] + cluster_lines + [
            "【代表工单原文（取自不同意图簇）】",
        ] + rep_lines + [
            "【知识库候选文档：从全库 %d 篇中，按与本意图工单的语义接近度取前 %d 篇】"
            % (len(src["docs"]), GAP_CANDIDATE_DOCS),
        ] + cand_lines)

        question = (
            "业务意图「{intent}」下提出的问题，知识库里是否有对应条目支撑？"
            "请依据下面给出的工单与知识库片段判断："
            "若你认为现有文档已经能支撑该诉求、只是覆盖度数值偏低，判「不是真缺口」"
            "并在 reason 中写明是哪一篇文档的哪个段落支撑了该诉求；"
            "若材料不足以判断，判「无法判断」并写明还缺什么信息。".format(intent=name)
        )
        items.append({
            "item_id": "GAP-%03d" % i,
            "category": C_GAP,
            "source_ref": name,
            "judge_question": question,
            "material": material,
        })
    return items


# ----------------------------------------------------------------- 文档/工单合理性
def build_doc_items(rng, src):
    items = []
    docs = sorted(src["docs"], key=lambda d: d["doc_id"])
    for i, d in enumerate(take(rng, docs, 30, key=lambda x: x["doc_id"]), start=1):
        material = NL.join([
            "【文档编号】" + d["doc_id"],
            "【标题】" + d["title"],
            "【领域归属 category】" + d["category"],
            "【创建日期】" + d["created_at"],
            "【最后修改日期】" + d["last_modified"],
            "【生效日期】" + d["effective_date"],
            "【文档状态】" + d["status"],
            "【被引用次数】" + d["ref_count"],
            "【正文】",
            d["content"],
        ])
        question = (
            "文档 {doc_id}（标题：{title}）的正文是否语义通顺？"
            "系统给出的领域归属 category「{category}」是否正确？"
            "若判断为不合理，请在 reason 中写明：哪一句不通顺（请引用原文片段），"
            "或为什么这篇内容不属于「{category}」。".format(
                doc_id=d["doc_id"], title=d["title"], category=d["category"])
        )
        items.append({
            "item_id": "DOC-%03d" % i,
            "category": C_DOC,
            "source_ref": d["doc_id"],
            "judge_question": question,
            "material": material,
        })
    return items


def build_ticket_items(rng, src):
    items = []
    tickets = sorted(src["tickets"], key=lambda t: t["ticket_id"])
    for i, t in enumerate(take(rng, tickets, 200, key=lambda x: x["ticket_id"]), start=1):
        material = NL.join([
            "【工单编号】" + t["ticket_id"],
            "【受理渠道】" + t["channel"],
            "【创建时间】" + t["created_at"],
            "【紧急程度】" + t["urgency"],
            "【处理状态】" + t["status"],
            "【系统标注意图 intent_label】" + t["intent_label"],
            "【工单正文】",
            t["content"],
        ])
        question = (
            "工单 {tid} 的表述是否像真实员工提问（自然、不截断、不空泛套话）？"
            "系统给出的意图标签「{label}」是否与这条工单的真实诉求一致？"
            "若判断为不合理，请在 reason 中写明：哪里不自然（请引用原文片段），"
            "或你认为正确的意图应该是什么。".format(
                tid=t["ticket_id"], label=t["intent_label"])
        )
        items.append({
            "item_id": "TKT-%03d" % i,
            "category": C_TKT,
            "source_ref": t["ticket_id"],
            "judge_question": question,
            "material": material,
        })
    return items


# ----------------------------------------------------------------- 腐化条目（双标签 + 盲化）
def corrupt_stratum(row):
    """按两个口径各自的规则加权分分层（只看系统的分，不看任何真值）。"""
    ce = int(row["cause_score_content_expiry"])
    mt = int(row["cause_score_maintenance"])
    if ce >= 3 and mt >= 3:
        return "内容过期×维护周期（双命中）"
    if ce >= 3:
        return "只命中内容过期"
    if mt >= 3:
        return "只命中维护周期"
    if int(row["risk_score"]) >= 3:
        return "两口径均未命中但被系统判过"
    return "系统未给出判定"


def same_intent_docs(doc, src):
    """同域（category）内、与本文属于同一业务意图的文档（客观可复核的中性事实）。

    同一业务意图 = 标题里出现同一个业务意图名（与工单意图标签同一套名称）。
    清单按最后修改日期倒序排列；只陈述事实，不代表任何判定。
    """
    intent = src["doc_intent"][doc["doc_id"]]
    peers = [d for d in src["docs"]
             if d["category"] == doc["category"]
             and d["doc_id"] != doc["doc_id"]
             and src["doc_intent"][d["doc_id"]] == intent]
    peers.sort(key=lambda d: (d["last_modified"], d["doc_id"]), reverse=True)
    return intent, peers


def build_corrupt_items(rng, src):
    """腐化清单：四象限分层抽样；材料只给可读材料，两个标签互不影响。"""
    buckets = {name: [] for name, _ in CORRUPT_QUOTA}
    for r in sorted(src["corrupt"], key=lambda x: x["doc_id"]):
        st = corrupt_stratum(r)
        if st in buckets:
            buckets[st].append(r)

    picked = []
    for name, quota in CORRUPT_QUOTA:                    # 固定顺序
        picked.extend(take(rng, buckets[name], quota, key=lambda x: x["doc_id"]))
    picked.sort(key=lambda r: r["doc_id"])

    base_date = src["ground_truth"].get("base_date", "")
    items = []
    for i, r in enumerate(picked, start=1):
        doc = src["docs_by_id"].get(r["doc_id"], {})
        intent, peers = same_intent_docs(doc, src)
        # 清单按最后修改日期倒序，本文按同一顺序插回
        rows_ = [(d["last_modified"], d["doc_id"], d["title"], False) for d in peers]
        rows_.append((doc.get("last_modified", ""), doc["doc_id"], doc.get("title", ""), True))
        rows_.sort(key=lambda x: (x[0], x[1]), reverse=True)
        peer_lines = ["  · {did}　最后修改 {lm}　{t}{mark}".format(
            did=did, lm=lm, t=t, mark="　← 本文" if self_ else "")
            for lm, did, t, self_ in rows_]
        cat_total = sum(1 for d in src["docs"] if d["category"] == doc.get("category", ""))

        material = NL.join([
            "【文档编号】" + r["doc_id"],
            "【标题】" + doc.get("title", ""),
            "【领域归属 category】" + doc.get("category", ""),
            "【本文所属业务意图】" + intent,
            "【最后修改日期 last_modified】" + doc.get("last_modified", ""),
            "【语料基准日】" + base_date + "（知识库语料的统一起算日）",
            "【同域同主题文档清单】本文所属领域「{cat}」下共 {n} 篇文档（含本文）；"
            "其中属于同一业务意图「{it}」的共 {m} 篇（含本文），清单如下"
            "（只陈述事实，不代表任何判定）：".format(
                cat=doc.get("category", ""), n=cat_total,
                it=intent, m=len(peers) + 1),
        ] + peer_lines + [
            "【正文】",
            doc.get("content", ""),
        ])
        question = (
            "本条要你回答两个**互不影响**的问题，分别作答。"
            "①（内容过期口径）只看【正文】本身：正文写明的时间口径"
            "（生效日期、有效期截止日、适用年度、所废止的旧版本等）"
            "相对语料基准日 {base} 是否**已经是过去**，"
            "以至于正文写明的内容已经不能作为当前依据？"
            "合法取值：正文已过期 / 正文未过期 / 无法判断。"
            "判「正文已过期」时必须在 reason 中引用正文原文片段、指出具体位置；"
            "正文里没有任何时间口径、或时间口径仍在基准日之后，判「正文未过期」。"
            "②（维护周期口径）本文是否**同时**满足两个条件："
            "（a）最后修改日期距语料基准日 {base} 超过 18 个月"
            "（即最后修改日期早于 2025-04-01）；"
            "（b）同域同一业务意图中已有更新版本"
            "（见上方同域同主题文档清单中，最后修改日期比本文更晚的文档）？"
            "两个条件都满足才判「维护状态已失控」；"
            "只满足其一（只有「很久没更新」而没有同域更新版，"
            "或有同域更新版但本文最后修改日期并不早）都判「维护状态正常」。"
            "合法取值：维护状态已失控 / 维护状态正常 / 无法判断。"
            "①与②互不影响：①只依据正文，不要用同域文档清单作依据；"
            "②只依据最后修改日期与同域文档清单，不要用正文里的时间口径作依据。"
            "任一问题判「无法判断」都必须在 reason 中写明缺什么信息。".format(base=base_date)
        )
        items.append({
            "item_id": "COR-%03d" % i,
            "category": C_COR,
            "source_ref": r["doc_id"],
            "judge_question": question,
            "material": material,
        })
    return items


# ----------------------------------------------------------------- 重复条目
def build_dup_items(rng, src):
    items = []
    groups = sorted(src["dups"], key=lambda g: int(g["group"]))
    for i, g in enumerate(take(rng, groups, 20, key=lambda x: int(x["group"])), start=1):
        members = [m for m in g.get("member_docs", "").split("|") if m]
        member_blocks = []
        for mid in members:
            d = src["docs_by_id"].get(mid, {})
            member_blocks.append(NL.join([
                "  · 文档编号：" + mid,
                "    标题：" + d.get("title", ""),
                "    正文：" + d.get("content", ""),
            ]))
        material = NL.join([
            "【重复组号 group】" + g.get("group", ""),
            "【组内文档数 size】" + g.get("size", ""),
            "【组内成员文档编号 member_docs】" + g.get("member_docs", ""),
            "【组内最大余弦相似度 max_sim】" + g.get("max_sim", ""),
            "【组内成员文档标题与正文】",
        ] + member_blocks)
        question = (
            "重复组 {grp} 中的 {n} 篇文档（{members}）讲的是不是同一件事？"
            "（即同一份内容，或只是换了措辞、调整了句序的近重复。"
            "若只是主题相近但规定的是不同事项，则不算同一件事。）"
            "max_sim 是组内最大余弦相似度，可作参考线索，判断请以标题与正文为准；"
            "若材料不足以判断，判「无法判断」并写明缺什么信息。".format(
                grp=g.get("group", ""), n=g.get("size", ""),
                members=g.get("member_docs", ""))
        )
        items.append({
            "item_id": "DUP-%03d" % i,
            "category": C_DUP,
            "source_ref": "group%s" % g.get("group", ""),
            "judge_question": question,
            "material": material,
        })
    return items


# ----------------------------------------------------------------- 落盘
def write_worklist(path, items):
    """items 已按 category 与 item_id 排好；判定列全部留空。"""
    ordered = sorted(items, key=lambda x: (CATEGORY_ORDER.index(x["category"]), x["item_id"]))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator=NL,
                           extrasaction="ignore")
        w.writeheader()
        for it in ordered:
            row = dict(it)
            for k in ("decision", "decision_content_expiry", "decision_maintenance",
                      "reason", "annotator", "annotated_at"):
                row[k] = ""
            w.writerow(row)
    return ordered


def build_all():
    src = load_sources()
    rng = random.Random(SEED)
    items = (build_doc_items(rng, src)
             + build_ticket_items(rng, src)
             + build_gap_items(src)
             + build_corrupt_items(rng, src)
             + build_dup_items(rng, src))

    # ---- B 卷选样：缺陷清单全量 + 文档类 15 条 + 工单类 15 条
    by_cat = {}
    for it in items:
        by_cat.setdefault(it["category"], []).append(it)
    defect = by_cat[C_GAP] + by_cat[C_COR] + by_cat[C_DUP]
    rng_b = random.Random(SEED)
    doc_items = by_cat[C_DOC]
    tkt_items = by_cat[C_TKT]
    picked_doc_ids = set(take(rng_b, [it["item_id"] for it in doc_items], 15))
    picked_tkt_ids = set(take(rng_b, [it["item_id"] for it in tkt_items], 15))
    b_items = list(defect)
    b_items += [it for it in doc_items if it["item_id"] in picked_doc_ids]
    b_items += [it for it in tkt_items if it["item_id"] in picked_tkt_ids]
    b_items = sorted(b_items, key=lambda x: (CATEGORY_ORDER.index(x["category"]), x["item_id"]))
    return items, b_items


# ----------------------------------------------------------------- 评分模式
def load_truth(src):
    """现场从源产物推导参考真值（不落盘、不写回工作单）。

    * 缺口：意图级真值 = ground_truth.json 的 gap_intents。
    * 腐化：两个口径分别取「被埋设 ∧ 满足本口径判据」为真阳性。
      跨类文档（埋的是另一类成因、但物理上同样满足本口径判据）在两个口径下
      都算真阳性——它是真缺陷，只是成因不止一个。
    * 重复：dup_groups_best.csv 的 is_true_group。
    """
    truth = {}
    intents = aggregate_intents(src["clusters"])
    gt_gap = set(src["ground_truth"]["gap_intents"])
    for name in intents:
        truth[(C_GAP, name)] = "是真缺口" if name in gt_gap else "不是真缺口"

    planted = {d["doc_id"] for d in src["docs"] if (d.get("corrupt_reason") or "").strip()}
    for r in src["corrupt"]:
        doc = src["docs_by_id"][r["doc_id"]]
        reason = doc.get("corrupt_reason") or ""
        ce_hit = int(r["cause_score_content_expiry"]) >= 3
        mt_hit = int(r["cause_score_maintenance"]) >= 3
        t_ce = "正文已过期" if (r["doc_id"] in planted and ce_hit) else "正文未过期"
        t_mt = "维护状态已失控" if (r["doc_id"] in planted and mt_hit) else "维护状态正常"
        truth[(C_COR, r["doc_id"])] = {
            "decision_content_expiry": t_ce,
            "decision_maintenance": t_mt,
            "stratum": corrupt_stratum(r),
            "planted": r["doc_id"] in planted,
            "reason": reason,
        }
    for g in src["dups"]:
        truth[(C_DUP, "group%s" % g["group"])] = \
            "是真重复组" if g.get("is_true_group") == "1" else "不是真重复组"
    return truth


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def confusion(pairs, labels):
    """pairs: [(标注值, 参考值)]；labels: 完整标签集。"""
    m = {a: {b: 0 for b in labels} for a in labels}
    for a, b in pairs:
        if a in m and b in m:
            m[a][b] += 1
    return m


def cohen_kappa(pairs, labels):
    """成对标注的一致性：po 与 pe 的标准二项定义。"""
    n = len(pairs)
    if n == 0:
        return None, None, 0
    agree = sum(1 for a, b in pairs if a == b)
    po = agree / n
    pa = Counter(a for a, _ in pairs)
    pb = Counter(b for _, b in pairs)
    pe = sum((pa[l] / n) * (pb[l] / n) for l in labels)
    if abs(1 - pe) < 1e-12:
        return po, None, n            # Kappa 无定义（期望一致率为 1）
    return po, (po - pe) / (1 - pe), n


def print_confusion(title, mat, labels):
    print(title)
    head = "标注\\参考".ljust(14) + "".join(l.ljust(14) for l in labels) + "合计"
    print(head)
    for a in labels:
        row = sum(mat[a].values())
        print(a.ljust(14) + "".join(str(mat[a][b]).ljust(14) for b in labels) + str(row))


def prf_line(tp, fp, fn):
    p, r, f = prf(tp, fp, fn)
    return "TP=%d FP=%d FN=%d  精确率=%.4f 召回率=%.4f F1=%.4f" % (tp, fp, fn, p, r, f)


def run_score(path_a, path_b):
    src = load_sources()
    rows_a = read_csv(path_a)
    rows_b = read_csv(path_b)
    truth = load_truth(src)

    def key(r):
        return (r["category"], r["source_ref"])

    map_a = {key(r): r for r in rows_a}
    map_b = {key(r): r for r in rows_b}
    overlap = sorted(set(map_a) & set(map_b))

    print("=" * 78)
    print("[score] 文件载入")
    print("  A 卷 %s：%d 条" % (os.path.basename(path_a), len(rows_a)))
    print("  B 卷 %s：%d 条" % (os.path.basename(path_b), len(rows_b)))
    print("  两者重叠条目：%d 条" % len(overlap))
    for name, rows in (("A 卷", rows_a), ("B 卷", rows_b)):
        cnt = Counter(r["category"] for r in rows)
        print("  %s 分类计数：%s" % (name, "，".join("%s %d" % (c, cnt.get(c, 0))
                                              for c in CATEGORY_ORDER)))

    # ---- 1) 标注者之间的一致性（只统计两边都填了的条目）
    print("=" * 78)
    print("[score] 标注者间一致性（A vs B，仅统计两边都填了的条目）")
    for cat in CATEGORY_ORDER:
        pairs = []
        for k in overlap:
            if k[0] != cat:
                continue
            da = (map_a[k].get("decision") or "").strip()
            db = (map_b[k].get("decision") or "").strip()
            if da and db:
                pairs.append((da, db))
        if cat == C_COR:
            for label_col, labels, tag in (("decision_content_expiry", LEGAL_CONTENT_EXPIRY, "内容过期口径"),
                                           ("decision_maintenance", LEGAL_MAINTENANCE, "维护周期口径")):
                ps = []
                for k in overlap:
                    if k[0] != cat:
                        continue
                    da = (map_a[k].get(label_col) or "").strip()
                    db = (map_b[k].get(label_col) or "").strip()
                    if da and db:
                        ps.append((da, db))
                if not ps:
                    print("  腐化清单 / %s：无可比条目" % tag)
                    continue
                po, kappa, n = cohen_kappa(ps, labels)
                print("  腐化清单 / %s：n=%d  逐条一致率=%.4f  Cohen's Kappa=%s"
                      % (tag, n, po, ("%.4f" % kappa) if kappa is not None
                         else "N/A（期望一致率为 1，Kappa 无定义）"))
                print_confusion("    混淆矩阵（行=标注者A，列=标注者B）：",
                                confusion(ps, labels), labels)
            continue
        if not pairs:
            print("  %s：无可比条目" % cat)
            continue
        labels = LEGAL_DECISIONS[cat]
        po, kappa, n = cohen_kappa(pairs, labels)
        print("  %s：n=%d  逐条一致率=%.4f  Cohen's Kappa=%s"
              % (cat, n, po, ("%.4f" % kappa) if kappa is not None
                 else "N/A（期望一致率为 1，Kappa 无定义）"))
        print_confusion("    混淆矩阵（行=标注者A，列=标注者B）：", confusion(pairs, labels), labels)

    # ---- 2) 缺口：意图级真值口径
    print("=" * 78)
    print("[score] 缺口清单：意图级真值（ground_truth.json → gap_intents，%d 个意图）"
          % len(src["ground_truth"]["gap_intents"]))
    for name, rows in (("A 卷", rows_a), ("B 卷", rows_b)):
        pairs = []
        for r in rows:
            if r["category"] != C_GAP:
                continue
            d = (r.get("decision") or "").strip()
            t = truth.get((C_GAP, r["source_ref"]))
            if d and t:
                pairs.append((d, t))
        if not pairs:
            print("  %s：已填条目为 0" % name)
            continue
        tp = sum(1 for d, t in pairs if d == "是真缺口" and t == "是真缺口")
        fp = sum(1 for d, t in pairs if d == "是真缺口" and t != "是真缺口")
        fn = sum(1 for d, t in pairs if d != "是真缺口" and t == "是真缺口")
        po, kappa, n = cohen_kappa(pairs, LEGAL_DECISIONS[C_GAP])
        print("  %s：n=%d  与真值一致率=%.4f  Kappa=%s"
              % (name, n, po, ("%.4f" % kappa) if kappa is not None else "N/A"))
        print("  %s 意图级：%s" % (name, prf_line(tp, fp, fn)))
        disagree = [(r["source_ref"], r.get("decision"), t) for r in rows
                    if r["category"] == C_GAP
                    for t in [truth.get((C_GAP, r["source_ref"]))]
                    if t and (r.get("decision") or "").strip()
                    and r["decision"] != t]
        for ref, d, t in disagree:
            print("      分歧：%s 人工=%s 真值=%s" % (ref, d, t))
    metrics_path = os.path.join(KB, "metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path, "r", encoding="utf-8") as f:
            gm = json.load(f)
        gb = gm.get("gap", {}).get("best", {})
        print("  （系统自身读数，来自 metrics.json：意图级检出 %s 个 / 真值 %s 个，"
              "P=%.4f R=%.4f F1=%.4f）"
              % (gb.get("detected_intents"), gm.get("gap", {}).get("n_gap_intents"),
                 gb.get("precision", 0.0), gb.get("recall", 0.0), gb.get("f1", 0.0)))

    # ---- 3) 腐化：两个口径分别算
    print("=" * 78)
    print("[score] 腐化清单：两个口径分别判定、分别报 P/R/F1，不合成单一 F1")
    truth_ce = set(k for (c, k), t in truth.items()
                   if c == C_COR and t["decision_content_expiry"] == "正文已过期")
    truth_mt = set(k for (c, k), t in truth.items()
                   if c == C_COR and t["decision_maintenance"] == "维护状态已失控")
    print("  参考真值：内容过期口径 %d 篇 / 维护周期口径 %d 篇（口径字典口径："
          "被埋设 ∧ 满足本口径判据，跨类文档在两个口径下都算真阳性）"
          % (len(truth_ce), len(truth_mt)))
    planted_stale_text = sorted(d["doc_id"] for d in src["docs"]
                                if (d.get("corrupt_reason") or "").strip() == "stale_text")
    planted_stale_mtime = sorted(d["doc_id"] for d in src["docs"]
                                 if (d.get("corrupt_reason") or "").strip() == "stale_mtime")
    print("    内容过期口径真值构成：埋设 stale_text %d 篇（其中 1 篇同时满足维护周期判据，"
          "两个口径下都算真阳性）" % len(planted_stale_text))
    print("    维护周期口径真值构成：埋设 stale_mtime %d 篇 + 跨类文档 1 篇 = %d 篇"
          % (len(planted_stale_mtime), len(truth_mt)))
    for label_col, labels, tag, truth_pos, hit_key in (
            ("decision_content_expiry", LEGAL_CONTENT_EXPIRY, "内容过期口径", truth_ce, "content_expiry"),
            ("decision_maintenance", LEGAL_MAINTENANCE, "维护周期口径", truth_mt, "maintenance")):
        print("  —— %s ——" % tag)
        rows_c = [r for r in rows_a if r["category"] == C_COR]
        for name, rows in (("A 卷", rows_a), ("B 卷", rows_b)):
            pairs = []
            for r in rows:
                if r["category"] != C_COR:
                    continue
                d = (r.get(label_col) or "").strip()
                t = truth.get((C_COR, r["source_ref"]))
                if d and t:
                    pairs.append((d, t[label_col]))
            if not pairs:
                print("    %s：已填条目为 0" % name)
                continue
            tp = sum(1 for d, t in pairs if d == labels[0] and t == labels[0])
            fp = sum(1 for d, t in pairs if d == labels[0] and t != labels[0])
            fn = sum(1 for d, t in pairs if d != labels[0] and t == labels[0])
            po, kappa, n = cohen_kappa(pairs, labels)
            print("    %s：n=%d  与真值一致率=%.4f  Kappa=%s"
                  % (name, n, po, ("%.4f" % kappa) if kappa is not None else "N/A"))
            print("    %s 人工读数：%s" % (name, prf_line(tp, fp, fn)))
            for r in rows:
                if r["category"] != C_COR:
                    continue
                d = (r.get(label_col) or "").strip()
                t = truth.get((C_COR, r["source_ref"]))
                if d and t and d != t[label_col]:
                    print("        分歧：%s 人工=%s 真值=%s（分层：%s）"
                          % (r["source_ref"], d, t[label_col], t["stratum"]))
        # 人工标签 vs 系统标签：规则口径下，人工与系统应当高度一致
        sys_label = {r["doc_id"]: (labels[0]
                                   if int(r["cause_score_" + hit_key]) >= 3
                                   else labels[1]) for r in src["corrupt"]}
        for name, rows in (("A 卷", rows_a), ("B 卷", rows_b)):
            ps = []
            for r in rows:
                if r["category"] != C_COR:
                    continue
                d = (r.get(label_col) or "").strip()
                if d:
                    ps.append((d, sys_label.get(r["source_ref"], "")))
            if not ps:
                continue
            po, kappa, n = cohen_kappa(ps, labels)
            print("    %s 人工标签 vs 系统标签：n=%d  一致率=%.4f  Kappa=%s"
                  % (name, n, po, ("%.4f" % kappa) if kappa is not None else "N/A"))
            print_confusion("      混淆矩阵（行=人工，列=系统）：",
                            confusion(ps, labels), labels)
        # 系统在同一批样本上的读数
        tp = fp = fn = 0
        for r in rows_c:
            hit = int(src["corrupt_by_id"][r["source_ref"]]["cause_score_" + hit_key]) >= 3
            pos = r["source_ref"] in truth_pos
            if hit and pos:
                tp += 1
            elif hit and not pos:
                fp += 1
            elif pos and not hit:
                fn += 1
        print("    系统在同一批样本上的读数：%s" % prf_line(tp, fp, fn))
        # 分层报告：系统误报单独列出
        fps = [r for r in rows_c
               if int(src["corrupt_by_id"][r["source_ref"]]["cause_score_" + hit_key]) >= 3
               and r["source_ref"] not in truth_pos]
        print("    分层报告——本批样本中系统判过、但参考真值不成立的条目：%d 条" % len(fps))
        for r in fps:
            t = truth.get((C_COR, r["source_ref"]))
            row = src["corrupt_by_id"][r["source_ref"]]
            a = (map_a.get((C_COR, r["source_ref"])) or {}).get(label_col, "") or "（未填）"
            b = (map_b.get((C_COR, r["source_ref"])) or {}).get(label_col, "") or "（未填）"
            print("        %s（真值=%s；系统误报归因=%s%s） 人工A=%s 人工B=%s"
                  % (r["source_ref"], t[label_col], row.get("fp_reason") or "-",
                     ("，重复件来源=" + row["dup_source"]) if row.get("dup_source") else "",
                     a.strip(), b.strip()))

    # ---- 4) 重复清单
    print("=" * 78)
    print("[score] 重复清单：与 dup_groups_best.csv 的 is_true_group 对照")
    for name, rows in (("A 卷", rows_a), ("B 卷", rows_b)):
        pairs = []
        for r in rows:
            if r["category"] != C_DUP:
                continue
            d = (r.get("decision") or "").strip()
            t = truth.get((C_DUP, r["source_ref"]))
            if d and t:
                pairs.append((d, t))
        if not pairs:
            print("  %s：已填条目为 0" % name)
            continue
        tp = sum(1 for d, t in pairs if d == "是真重复组" and t == "是真重复组")
        fp = sum(1 for d, t in pairs if d == "是真重复组" and t != "是真重复组")
        fn = sum(1 for d, t in pairs if d != "是真重复组" and t == "是真重复组")
        po, kappa, n = cohen_kappa(pairs, LEGAL_DECISIONS[C_DUP])
        print("  %s：n=%d  与真值一致率=%.4f  Kappa=%s"
              % (name, n, po, ("%.4f" % kappa) if kappa is not None else "N/A"))
        print("  %s：%s" % (name, prf_line(tp, fp, fn)))
    print("=" * 78)
    print("[score] 口径提醒：")
    print("        ① 内容过期口径的参考真值与系统规则同源（规则是照生成器的埋设模板写的），")
    print("           满分属循环验证，不能当作独立评测。")
    print("        ② 维护周期口径的系统误报全部落在「只命中维护周期」分层里，")
    print("           其中 6 篇是生成器刻意埋设的「自然陈旧但不算缺陷」对照集，")
    print("           1 篇是重复件继承了主文档的陈旧 last_modified。")
    print("        ③ 缺口类的判定单元是业务意图（分母是 30 个意图），不是意图簇。")
    print("        ④ 判据是公开的：标注者按工作单上写明的判据作答，")
    print("           因此人工标签应与系统标签高度一致；")
    print("           人工标签对埋设真值的 F1 若低于系统读数，说明的是「规则过召」，")
    print("           不是标注错误——那 7 篇对照集/重复件在公开判据下本来就该判「已失控」。")
    print("=" * 78)


# ----------------------------------------------------------------- 入口
def main(argv=None):
    ap = argparse.ArgumentParser(description="生成人工标注工作单 A/B 卷")
    ap.add_argument("--score", action="store_true",
                    help="评分模式：读两份已填好的工作单，算一致率、Cohen's Kappa 与混淆矩阵")
    ap.add_argument("--a", default=os.path.join(HERE, "worklist_A_filled.csv"),
                    help="评分模式下的 A 卷文件路径")
    ap.add_argument("--b", default=os.path.join(HERE, "worklist_B_filled.csv"),
                    help="评分模式下的 B 卷文件路径")
    args = ap.parse_args(argv)

    if args.score:
        run_score(args.a, args.b)
        return 0

    items, b_items = build_all()
    ordered_a = write_worklist(OUT_A, items)
    ordered_b = write_worklist(OUT_B, b_items)

    counts = Counter(it["category"] for it in ordered_a)
    print("=" * 78)
    print("[make_worklist] A 卷：%s（%d 条）" % (os.path.basename(OUT_A), len(ordered_a)))
    for c in CATEGORY_ORDER:
        print("    %-14s %d" % (c, counts.get(c, 0)))
    print("[make_worklist] B 卷：%s（%d 条）" % (os.path.basename(OUT_B), len(ordered_b)))
    bc = Counter(it["category"] for it in ordered_b)
    for c in CATEGORY_ORDER:
        print("    %-14s %d" % (c, bc.get(c, 0)))
    print("[make_worklist] 缺口条目：%d 个业务意图全量纳入（判定单元=业务意图）"
          % counts.get(C_GAP, 0))
    print("[make_worklist] 随机种子 %d，重复执行产出逐字节一致。" % SEED)
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
