# -*- coding: utf-8 -*-
"""
standardize.py -- 语料基线标准化打分：4 种方案 vs 绝对余弦阈值（意图级 AUC 0.9680 基线）

靶心问题：绝对余弦阈值不可迁移（BGE 中文基线太高，可用窗口只有 0.60-0.64）。
本脚本实测 S1 分位数排名 / S2 标准化 z-score / S3 领域内标准化 / S4 双参考系
在 4 个语料场景下的意图级 AUC 与"阈值跨场景迁移性"，并做消融。

运行：python standardize.py
只读父目录已有产物，所有新文件写在本目录。
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("HF_HOME", "D:/hf_cache")

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, PARENT)

BASE_MODEL = "BAAI/bge-small-zh-v1.5"


# ====================================================================== 基础工具
def auc(pos, neg):
    """pos/neg 为两组分数，方向已统一为「越大越可能是缺口」。"""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    allv = np.concatenate([pos, neg])
    order = np.argsort(allv, kind="mergesort")
    ranks = np.empty(len(allv), float)
    sv = allv[order]
    i = 0
    while i < len(sv):                      # 平均秩，正确处理并列
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    n1, n0 = len(pos), len(neg)
    r1 = ranks[:n1].sum()
    return float((r1 - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def auc_with_ties(y, s):
    """通用版：y 为 0/1。"""
    y = np.asarray(y)
    return auc(s[y == 1], s[y == 0])


def pct_rank(x):
    """分位数排名，返回 (rank, n)，rank 越大表示越靠后（值越大）。"""
    n = len(x)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(n, float)
    sv = x[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sv[j + 1] == sv[i]:
            j += 1
        # 并列取平均秩（1-based）
        ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks / n, n


def zscore(x):
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    sd = sd if sd > 1e-12 else 1.0
    return (x - mu) / sd, mu, sd


def group_zscore(x, g):
    """组内 z-score；单元素组回落到 0。"""
    out = np.zeros(len(x), float)
    for key in np.unique(g):
        m = g == key
        if m.sum() >= 2:
            out[m] = zscore(x[m])[0]
        else:
            out[m] = 0.0
    return out


def group_pct(x, g):
    """组内分位数排名。"""
    out = np.zeros(len(x), float)
    for key in np.unique(g):
        m = g == key
        out[m] = pct_rank(x[m])[0]
    return out


# ============================================================ 四种标准化打分函数
def s1_prank(cover, **_):
    """S1 分位数排名：score = 1 - pct_rank(cover)。越大越差。"""
    return 1.0 - pct_rank(cover)[0]


def s2_zscore(cover, **_):
    """S2 全局 z-score 取负：score = -(cover - mu)/sigma。"""
    return -zscore(cover)[0]


def s3_domain(cover, dom=None, **_):
    """S3 领域内标准化：组内 z-score 取负。"""
    return -group_zscore(cover, dom)


def s4_dual(cover, dom=None, **_):
    """S4 双参考系：score = -max(z_global(cover), z_within(cover))。
    z_within 按业务域分组（业务域偏差的主要来源）。"""
    zg = zscore(cover)[0]
    zw = group_zscore(cover, dom)
    return -np.maximum(zg, zw)


def s4_dual_intent(cover, intent=None, **_):
    """S4 变体：组内参照换成「同意图」而非业务域。"""
    zg = zscore(cover)[0]
    zw = group_zscore(cover, intent)
    return -np.maximum(zg, zw)


def s5_mean_dual(cover, dom=None, **_):
    """S5（自加）双参考系取算术平均而非 max：-(z_g + z_w)/2。"""
    zg = zscore(cover)[0]
    zw = group_zscore(cover, dom)
    return -(zg + zw) / 2.0


def s6_winsor(cover, **_):
    """S6（自加）去极值稳健 z：先按 5%/95% 分位裁剪再标准化。"""
    lo, hi = np.percentile(cover, [5, 95])
    c = np.clip(cover, lo, hi)
    return -zscore(c)[0]


SCORERS = {
    "ABS(绝对阈值)": lambda cover, **kw: -cover,
    "S1 分位数排名": s1_prank,
    "S2 全局z-score": s2_zscore,
    "S3 领域内z": s3_domain,
    "S4 双参考系(域)": s4_dual,
    "S5 双参考系均值": s5_mean_dual,
    "S6 去极值z": s6_winsor,
    "S4b 双参考系(意图)": s4_dual_intent,
}


# ============================================================ 意图级聚合与评估
def intent_level(score, intent_labels, gap_intents):
    """把工单级分数聚合成意图级（取中位数），算意图级 AUC。"""
    df = pd.DataFrame({"intent": intent_labels, "s": score})
    med = df.groupby("intent")["s"].median()
    pos = [v for k, v in med.items() if k in gap_intents]
    neg = [v for k, v in med.items() if k not in gap_intents]
    return auc(pos, neg), med


def best_f1_threshold(score, intent_labels, gap_intents):
    """扫描「score >= thr 判为缺口」的阈值，返回意图级 P/R/F1 最优点。"""
    df = pd.DataFrame({"intent": intent_labels, "s": score})
    med = df.groupby("intent")["s"].median()
    vals = np.sort(med.values)
    cands = np.unique(np.concatenate([[-np.inf], (vals[:-1] + vals[1:]) / 2, [np.inf]]))
    best = (0.0, 0.0, 0.0, np.nan)
    for thr in cands:
        det = {k for k, v in med.items() if v >= thr}
        tp = len(det & gap_intents)
        p = tp / len(det) if det else 0.0
        r = tp / len(gap_intents)
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        if f > best[0] or (f == best[0] and p > best[1]):
            best = (f, p, r, thr)
    return best


def thr_for_recall_k(score, intent_labels, gap_intents, k=None):
    """求「召回 k 个缺口意图」所需的阈值：取第 k 低缺口意图分数（score >= thr 判为缺口）。"""
    df = pd.DataFrame({"intent": intent_labels, "s": score})
    med = df.groupby("intent")["s"].median()
    k = k or len(gap_intents)
    need = np.sort(med[[i for i in med.index if i in gap_intents]].values)
    if len(need) < k:
        return None
    return float(need[-k])


def evaluate(cover, tickets, gap_intents, dom, intent_labels):
    """一个场景下，所有打分方法的意图级指标。"""
    out = {}
    for name, fn in SCORERS.items():
        s = fn(cover, dom=dom, intent=intent_labels)
        a, _ = intent_level(s, intent_labels, gap_intents)
        f1, p, r, thr = best_f1_threshold(s, intent_labels, gap_intents)
        out[name] = dict(auc=a, best_f1=f1, best_p=p, best_r=r, best_thr=thr,
                         thr_recall_all=thr_for_recall_k(s, intent_labels, gap_intents),
                         score=s)
    return out


# ============================================================ 场景构造
def load_base():
    docs = pd.read_csv(os.path.join(PARENT, "docs.csv"), encoding="utf-8-sig")
    tickets = pd.read_csv(os.path.join(PARENT, "tickets.csv"), encoding="utf-8-sig")
    gt = json.load(open(os.path.join(PARENT, "ground_truth.json"), encoding="utf-8"))
    cover = np.load(os.path.join(PARENT, "ticket_cover.npy"))
    T = np.load(os.path.join(PARENT, "ticket_emb.npy"))
    D = np.load(os.path.join(PARENT, "doc_emb.npy"))
    return docs, tickets, gt, cover, T, D


def doc_intent_map(docs):
    import gen_data as G
    names = [i for i, _ in G.COVERED_INTENTS]
    return [next((n for n in names if n in t), None) for t in docs["title"]]


def intent_domain_map():
    """意图 -> 业务域。缺口意图无文档，用工单向量对各域文档的相似度反推。"""
    import gen_data as G
    docs, tickets, gt, cover, T, D = load_base()
    m = {i: c for i, c in G.COVERED_INTENTS}
    cats = sorted(docs["category"].unique())
    for gi in gt["gap_intents"]:
        idx = np.where(tickets["intent_label"].values == gi)[0]
        v = T[idx].mean(axis=0)
        v /= np.linalg.norm(v) + 1e-12
        m[gi] = max(cats, key=lambda c: float(np.mean(D[docs["category"].values == c] @ v)))
    return m


def passages_of(docs, idx=None):
    """对 docs 的指定行切段落，返回 (texts, owner)。owner 是原文行号。"""
    import re
    sel = docs if idx is None else docs.iloc[idx]
    texts, owner = [], []
    for j, (_, r) in enumerate(sel.iterrows()):
        t = f"{r['title']}。{r['content']}"
        parts = [p.strip() for p in re.split(r"[。；]", t) if len(p.strip()) >= 8]
        for p in (parts or [t]):
            texts.append(p)
            owner.append(j)
    return texts, np.asarray(owner, dtype=np.int32)


_ENC = {}


def get_encoder(model=BASE_MODEL):
    if model not in _ENC:
        from FlagEmbedding import FlagModel
        _ENC[model] = FlagModel(model, use_fp16=False)
    return _ENC[model]


def cover_for_docs(docs, doc_idx, tickets, T, model=BASE_MODEL):
    """给定文档子集，重算工单段落级最大余弦覆盖度。"""
    t0 = time.time()
    enc = get_encoder(model)
    ptxt, owner = passages_of(docs, doc_idx)
    P = np.asarray(enc.encode(ptxt, batch_size=64), dtype=np.float32)
    P /= (np.linalg.norm(P, axis=1, keepdims=True) + 1e-12)
    SP = T @ P.T
    n = len(doc_idx)
    starts = np.searchsorted(owner, np.arange(n), side="left")
    ends = np.searchsorted(owner, np.arange(n), side="right")
    if (ends <= starts).any():
        raise ValueError(f"存在没有段落的文档: {np.where(ends <= starts)[0].tolist()}")
    cover = np.maximum.reduceat(SP, starts, axis=1)   # (n_tickets, n_docs)
    assert cover.shape == (len(T), n), cover.shape
    return cover.max(axis=1).astype(np.float64), round(time.time() - t0, 2)


# ============================================================ 主流程
def main():
    import gen_data as G
    t_start = time.time()
    docs, tickets, gt, cover_a, T, D = load_base()
    gap_a = set(gt["gap_intents"])
    ilab = tickets["intent_label"].values
    docs["intent"] = doc_intent_map(docs)
    i2d = intent_domain_map()
    dom = np.array([i2d[i] for i in ilab])
    covered_intents = [i for i, _ in G.COVERED_INTENTS]

    print("=" * 74)
    print("[standardize] 基线核对")
    a0, _ = intent_level(-cover_a.astype(np.float64), ilab, gap_a)
    print(f"[standardize] 段落级 max-cosine 意图级 AUC = {a0:.4f} "
          f"(RESULT.md 记录 0.968)")
    print(f"[standardize] 意图->域 映射: " +
          ", ".join(f"{k}->{v}" for k, v in sorted(i2d.items()) if k in gap_a))

    # ---------------- 场景 alpha：完整语料（直接复用已有 ticket_cover.npy）
    print("\n" + "=" * 74)
    print("[scenario alpha] 完整语料 300 篇 / 2000 条")
    res_alpha = evaluate(cover_a.astype(np.float64), tickets, gap_a, dom, ilab)
    print(f"  cover 分布 min={cover_a.min():.4f} mean={cover_a.mean():.4f} "
          f"max={cover_a.max():.4f} sd={cover_a.std(ddof=1):.4f}")

    # ---------------- 场景 beta：缩小语料（75 篇，固定 seed）
    print("\n" + "=" * 74)
    print("[scenario beta] 缩小语料 75 篇（seed=42 随机抽样）")
    r = np.random.default_rng(42)
    sel_b = np.sort(r.choice(len(docs), 75, replace=False))
    alive_b = set(docs.iloc[sel_b]["intent"].dropna())
    # 重新定义 ground truth：失去全部文档的意图 + 原有缺口意图
    gap_b = gap_a | {i for i in covered_intents if i not in alive_b}
    print(f"  文档 {len(sel_b)} 篇, 存活意图 {len(alive_b)}/25, "
          f"新增缺口意图 {sorted(gap_b - gap_a)}")
    cover_b, sec = cover_for_docs(docs, sel_b, tickets, T)
    print(f"  重新编码+覆盖度耗时 {sec}s, "
          f"cover min={cover_b.min():.4f} mean={cover_b.mean():.4f} max={cover_b.max():.4f}")
    res_beta = evaluate(cover_b, tickets, gap_b, dom, ilab)

    # ---------------- 场景 gamma：领域偏移（只保留 财务+人事+信息+采购 四域 180 篇）
    print("\n" + "=" * 74)
    print("[scenario gamma] 领域偏移 180 篇（财务/人事行政/信息技术/采购合同）")
    doms_g = ["财务管理", "人事行政", "信息技术", "采购合同"]
    sel_g = np.where(docs["category"].isin(doms_g).values)[0]
    alive_g = set(docs.iloc[sel_g]["intent"].dropna())
    # 重新定义 ground truth：本场景下真正没有任何文档支撑的意图
    gap_g = {i for i in covered_intents if i not in alive_g} | gap_a
    print(f"  文档 {len(sel_g)} 篇, 存活意图 {len(alive_g)}/25")
    print(f"  重新定义 ground truth = {len(gap_g)} 个意图 "
          f"(={len(gap_g - gap_a)} 个因域偏移失去覆盖 + 5 个原有缺口)")
    cover_g, sec = cover_for_docs(docs, sel_g, tickets, T)
    print(f"  重新编码+覆盖度耗时 {sec}s, "
          f"cover min={cover_g.min():.4f} mean={cover_g.mean():.4f} max={cover_g.max():.4f}")
    res_gamma = evaluate(cover_g, tickets, gap_g, dom, ilab)

    # ---------------- 场景 gamma-extreme：极端域偏移（只保留财务域 48 篇）
    print("\n" + "=" * 74)
    print("[scenario gamma-X] 极端域偏移 48 篇（只剩财务管理域）")
    sel_gx = np.where(docs["category"].values == "财务管理")[0]
    alive_gx = set(docs.iloc[sel_gx]["intent"].dropna())
    gap_gx = {i for i in covered_intents if i not in alive_gx} | gap_a
    print(f"  文档 {len(sel_gx)} 篇, 存活意图 {len(alive_gx)}/25, "
          f"重新定义 ground truth = {len(gap_gx)} 个意图")
    cover_gx, sec = cover_for_docs(docs, sel_gx, tickets, T)
    print(f"  重新编码+覆盖度耗时 {sec}s, "
          f"cover min={cover_gx.min():.4f} mean={cover_gx.mean():.4f} max={cover_gx.max():.4f}")
    res_gx = evaluate(cover_gx, tickets, gap_gx, dom, ilab)

    # ---------------- 场景 delta：文档翻倍（复制 + 扰动），覆盖度分布变宽
    print("\n" + "=" * 74)
    print("[scenario delta] 文档翻倍 600 篇（原 300 + 复制并做同义扰动）")
    rng = np.random.default_rng(7)
    docs2 = docs.copy()
    extra = docs.copy()
    swap = [("须在", "应当"), ("限于", "仅限"), ("一并", "统一"), ("不得", "严禁"),
            ("由", "经"), ("该", "本"), ("所有", "全部"), ("应当", "须")]
    newc = []
    for t in extra["content"]:
        t2 = t
        for a, b in swap:
            if rng.random() < 0.5:
                t2 = t2.replace(a, b)
        newc.append(t2 + f"（修订副本 {rng.integers(100, 1000)}）")
    extra["content"] = newc
    extra["doc_id"] = [f"DOC{i:04d}" for i in range(300, 600)]
    docs2 = pd.concat([docs, extra], ignore_index=True)
    print(f"  合并后 {len(docs2)} 篇")
    cover_d, sec = cover_for_docs(docs2, np.arange(len(docs2)), tickets, T)
    print(f"  重新编码+覆盖度耗时 {sec}s, "
          f"cover min={cover_d.min():.4f} mean={cover_d.mean():.4f} max={cover_d.max():.4f}")
    res_delta = evaluate(cover_d, tickets, gap_a, dom, ilab)

    # ============================================================ 实验 1：AUC 对照
    print("\n" + "=" * 74)
    print("[EXP1] 意图级 AUC 对照（场景 alpha，基线 0.968）")
    rows = []
    for name in SCORERS:
        v = res_alpha[name]
        rows.append(dict(方法=name, 场景="alpha", AUC=round(v["auc"], 4),
                         best_F1=round(v["best_f1"], 4), P=round(v["best_p"], 4),
                         R=round(v["best_r"], 4), 最优阈值=round(v["best_thr"], 4)))
        print(f"  {name:18s} AUC={v['auc']:.4f}  F1={v['best_f1']:.4f} "
              f"thr={v['best_thr']:+.4f}")
    exp1 = pd.DataFrame(rows)
    exp1.to_csv(os.path.join(HERE, "results_auc.csv"), index=False, encoding="utf-8-sig")

    # ============================================================ 实验 2：阈值可迁移性
    print("\n" + "=" * 74)
    print("[EXP2] 阈值可迁移性")
    scen = {"alpha": res_alpha, "beta": res_beta, "gamma": res_gamma,
            "gamma-X": res_gx, "delta": res_delta}
    auc_rows = []
    for sn, r_ in scen.items():
        for name in SCORERS:
            auc_rows.append(dict(场景=sn, 方法=name, AUC=round(r_[name]["auc"], 4),
                                 best_F1=round(r_[name]["best_f1"], 4),
                                 召回全部门槛的阈值=(round(r_[name]["thr_recall_all"], 4)
                                                    if r_[name]["thr_recall_all"] is not None
                                                    else np.nan)))
    auc_df = pd.DataFrame(auc_rows)
    auc_df.to_csv(os.path.join(HERE, "results_auc.csv"), index=False, encoding="utf-8-sig")
    print("\n  各场景意图级 AUC：")
    piv = auc_df.pivot(index="方法", columns="场景", values="AUC")
    print(piv.reindex(list(SCORERS)).to_string())

    print("\n  「召回全部缺口意图」所需阈值（跨场景是否同量纲）：")
    piv2 = auc_df.pivot(index="方法", columns="场景", values="召回全部门槛的阈值")
    print(piv2.reindex(list(SCORERS)).to_string())

    # 源场景 alpha 的最优阈值 -> 迁移到其它场景
    print("\n  阈值迁移（源=alpha 的最优 F1 阈值，直接搬到别的场景）：")
    tr_rows = []
    for name in SCORERS:
        src_thr = res_alpha[name]["best_thr"]
        for tgt in ["beta", "gamma", "gamma-X", "delta"]:
            s = scen[tgt][name]["score"]
            df = pd.DataFrame({"intent": ilab, "s": s})
            med = df.groupby("intent")["s"].median()
            gap_t = {"alpha": gap_a, "beta": gap_b, "gamma": gap_g,
                     "gamma-X": gap_gx, "delta": gap_a}[tgt]
            det = {k for k, v in med.items() if v >= src_thr}
            tp = len(det & gap_t)
            p = tp / len(det) if det else 0.0
            r = tp / len(gap_t)
            f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            tr_rows.append(dict(方法=name, 源场景="alpha", 源阈值=round(src_thr, 4),
                                目标场景=tgt, 迁移后F1=round(f, 4),
                                迁移后P=round(p, 4), 迁移后R=round(r, 4),
                                检出意图数=len(det), 目标场景最优F1=round(scen[tgt][name]["best_f1"], 4),
                                AUC衰减=round(scen[tgt][name]["auc"] - res_alpha[name]["auc"], 4)))
    tr = pd.DataFrame(tr_rows)
    tr.to_csv(os.path.join(HERE, "results_transfer.csv"), index=False, encoding="utf-8-sig")
    print(tr.to_string(index=False))

    # ============================================================ 实验 3：消融
    print("\n" + "=" * 74)
    print("[EXP3] 消融")
    ab = []

    def add(name, desc, sc):
        a, _ = intent_level(sc, ilab, gap_a)
        f1, p, r, thr = best_f1_threshold(sc, ilab, gap_a)
        ab.append(dict(变体=name, 说明=desc, alpha_AUC=round(a, 4),
                       alpha_F1=round(f1, 4), 最优阈值=round(thr, 4)))
        print(f"  {name:26s} AUC={a:.4f} F1={f1:.4f} thr={thr:+.4f}  {desc}")

    add("ABS 绝对余弦", "-cover（基线 0.968）", -cover_a.astype(np.float64))
    add("S1 分位数排名", "1 - pct_rank(cover)", s1_prank(cover_a.astype(np.float64)))
    add("S2 全局z", "-(cover-mu)/sigma", s2_zscore(cover_a.astype(np.float64)))
    add("S6 去极值z", "5%/95%裁剪后 z", s6_winsor(cover_a.astype(np.float64)))
    zg = zscore(cover_a.astype(np.float64))[0]
    zw_d = group_zscore(cover_a.astype(np.float64), dom)
    zw_i = group_zscore(cover_a.astype(np.float64), ilab)
    add("S4 完整(域内)", "-max(zg, zw_domain)", -np.maximum(zg, zw_d))
    add("S4 去掉域内(仅全局)", "-zg", -zg)
    add("S4 去掉全局(仅域内)", "-zw_domain", -zw_d)
    add("S4 换成意图片", "-max(zg, zw_intent)", -np.maximum(zg, zw_i))
    add("S4 min 聚合", "-min(zg, zw_domain)", -np.minimum(zg, zw_d))
    add("S5 均值聚合", "-(zg+zw_domain)/2", -(zg + zw_d) / 2.0)
    add("S3 域内分位数", "-pct_rank_within_domain", -group_pct(cover_a.astype(np.float64), dom))
    add("S3 意图片分位数", "-pct_rank_within_intent", -group_pct(cover_a.astype(np.float64), ilab))
    # max 的两半单独看
    add("消融: max 选出域内", "仅当 zw_domain>zg 时取 zw", -np.where(zw_d > zg, zw_d, zg))
    add("消融: max 选出全局", "仅当 zg>zw_domain 时取 zg", -np.where(zg > zw_d, zg, zw_d))
    ablation = pd.DataFrame(ab)
    ablation.to_csv(os.path.join(HERE, "ablation.csv"), index=False, encoding="utf-8-sig")

    # 消融里获胜/接近获胜的变体，放到其它场景验证迁移
    print("\n  关键变体跨场景 AUC：")
    variants = ["S1 分位数排名", "S2 全局z", "S3 域内分位数", "S4 完整(域内)",
                "S4 min聚合", "S5 均值聚合"]
    ab_scen = []
    covers = {"alpha": (cover_a.astype(np.float64), gap_a),
              "beta": (cover_b, gap_b), "gamma": (cover_g, gap_g),
              "gamma-X": (cover_gx, gap_gx), "delta": (cover_d, gap_a)}

    def variant_score(vn, cv):
        if vn == "S1 分位数排名":
            return s1_prank(cv)
        if vn == "S2 全局z":
            return s2_zscore(cv)
        if vn == "S3 域内分位数":
            return -group_pct(cv, dom)
        z1 = zscore(cv)[0]
        z2 = group_zscore(cv, dom)
        if vn == "S4 完整(域内)":
            return -np.maximum(z1, z2)
        if vn == "S4 min聚合":
            return -np.minimum(z1, z2)
        return -(z1 + z2) / 2.0

    for vn in variants:
        for sn, (cv, gt_sn) in covers.items():
            sc = variant_score(vn, cv)
            a, _ = intent_level(sc, ilab, gt_sn)
            f1, p, r, thr = best_f1_threshold(sc, ilab, gt_sn)
            ab_scen.append(dict(变体=vn, 场景=sn, AUC=round(a, 4), F1=round(f1, 4),
                                最优阈值=round(thr, 4)))
            print(f"    {vn:16s} {sn:6s} AUC={a:.4f} F1={f1:.4f} thr={thr:+.4f}")
    pd.DataFrame(ab_scen).to_csv(os.path.join(HERE, "ablation.csv"),
                                 index=False, encoding="utf-8-sig", mode="a")

    # ============================================================ 机制分析：为什么 S1/S2 打不过也不能赢
    print("\n" + "=" * 74)
    print("[MECH] 机制分析：与 cover 的 Spearman 秩相关（=1 即单调等价，AUC 必然相同）")
    from scipy.stats import spearmanr
    mech_rows = []
    cv0 = cover_a.astype(np.float64)
    for name, fn in SCORERS.items():
        s = fn(cv0, dom=dom, intent=ilab)
        rho = float(spearmanr(cv0, s).statistic)
        a, _ = intent_level(s, ilab, gap_a)
        mono = bool(abs(rho + 1.0) < 1e-9 or abs(rho - 1.0) < 1e-9)
        mech_rows.append(dict(方法=name, spearman_与cover=round(rho, 6),
                              alpha_AUC=round(a, 4), 是否单调等价=mono))
        print(f"  {name:18s} rho={rho:+.6f}  AUC={a:.4f}  "
              f"{'单调等价 -> AUC 数学上不可能改变' if mono else '非单调 -> 可改变排序'}")
    pd.DataFrame(mech_rows).to_csv(os.path.join(HERE, "mechanism.csv"), index=False,
                                   encoding="utf-8-sig")

    # 场景统计落盘，供报告引用
    meta = dict(
        baseline_auc=round(a0, 4),
        cover_stats={k: dict(min=round(float(v.min()), 4), mean=round(float(v.mean()), 4),
                             max=round(float(v.max()), 4), sd=round(float(v.std(ddof=1)), 4))
                     for k, (v, _) in covers.items()},
        gap_sets={k: sorted(v) for k, v in dict(alpha=gap_a, beta=gap_b,
                                                gamma=gap_g, **{"gamma-X": gap_gx},
                                                delta=gap_a).items()},
        n_docs={k: int(v) for k, v in
                dict(alpha=len(docs), beta=len(sel_b), gamma=len(sel_g),
                     **{"gamma-X": len(sel_gx)}, delta=len(docs2)).items()},
        total_seconds=round(time.time() - t_start, 1),
        mechanism=mech_rows,
        best_f1_by_scenario={sn: {n: round(v["best_f1"], 4) for n, v in r_.items()}
                             for sn, r_ in scen.items()},
    )
    json.dump(meta, open(os.path.join(HERE, "scenario_meta.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n[standardize] 完成，总耗时 {meta['total_seconds']}s")


if __name__ == "__main__":
    main()