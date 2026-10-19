# -*- coding: utf-8 -*-
"""
贪心图着色基线 (networkx)

建模:
  顶点 = "课程-节次" 任务单元 (每门课 weekly_hours 个)
  边   = 共享教师 或 共享班级 的互斥关系
  色数 = 所需时段数      <-- 论文建模要点

注意: 纯贪心只处理 "同时"冲突(教师/班级), 不处理教室资源,
      因此贪心结果必然有教室类硬冲突 —— 这正是 CP-SAT 的价值所在。
"""
import time
import networkx as nx

from gen_data import load_json, with_buildings, make_tasks
from conflict_lib import detect_conflicts, count_hard, conflicts_to_schedule


def build_conflict_graph(tasks):
    G = nx.Graph()
    for t in tasks:
        G.add_node(t["task_id"], **t)

    by_teacher = {}
    by_class = {}
    for t in tasks:
        by_teacher.setdefault(t["teacher_id"], []).append(t["task_id"])
        for cid in t["class_ids"]:
            by_class.setdefault(cid, []).append(t["task_id"])

    def add_clique(ids, reason):
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                G.add_edge(ids[i], ids[j], reason=reason)

    for tid, ids in by_teacher.items():
        add_clique(ids, f"teacher:{tid}")
    for cid, ids in by_class.items():
        add_clique(ids, f"class:{cid}")
    return G


def available_strategies():
    """检测本 networkx 版本 greedy_color 支持哪些 strategy"""
    import inspect

    src = ""
    try:
        src = inspect.getsource(nx.coloring.greedy_color)
    except Exception:
        pass
    has_dsatur = "DSATUR" in src
    return has_dsatur


def greedy_schedule(tasks, data, strategy, use_interchange=False):
    """
    返回 (schedule, n_colors, elapsed_sec)
    strategy: 'largest_first' 或 'DSATUR'
    """
    G = build_conflict_graph(tasks)
    t0 = time.perf_counter()
    coloring = nx.coloring.greedy_color(G, strategy=strategy, interchange=use_interchange)
    elapsed = time.perf_counter() - t0
    period_of = {tid: c for tid, c in coloring.items()}

    # 贪心结果没有房间概念 -> 用一个规则匹配的教室,
    # 冲突数量由 detect_conflicts 如实报告 (不粉饰)
    rooms = data["rooms"]
    tmap = {t["task_id"]: t for t in tasks}
    room_of = {}
    used = set()
    for tid, p in period_of.items():
        t = tmap[tid]
        pick = None
        for r in sorted(rooms, key=lambda r: r["capacity"]):
            if r["capacity"] < t["required_capacity"]:
                continue
            if t["needs_lab"] and r["type"] != "lab":
                continue
            if (rid := r["room_id"], p) in used:
                continue
            pick = rid
            break
        if pick is None:
            pick = rooms[0]["room_id"]  # 兜底: 允许产生冲突, 由检测器如实报告
        used.add((pick, p))
        room_of[tid] = pick

    sched = conflicts_to_schedule(tasks, period_of, room_of)
    n_colors = (max(coloring.values()) + 1) if coloring else 0
    return sched, n_colors, elapsed, G, coloring


def run(scale="s60", verbose=True):
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    data = with_buildings(load_json(os.path.join(here, f"data_{scale}.json")))
    tasks = make_tasks(data)
    has_dsatur = available_strategies()

    strategies = [("largest_first", False)]
    if has_dsatur:
        strategies.append(("DSATUR", False))
    else:
        strategies.append(("largest_first", True))

    results = []
    for strat, inter in strategies:
        label = strat + ("+interchange" if inter else "")
        sched, ncol, elapsed, G, _ = greedy_schedule(tasks, data, strat, inter)
        conf = detect_conflicts(sched, data)
        hard = count_hard(conf)
        by_type = {}
        for c in conf:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        results.append(
            {
                "scale": scale,
                "algorithm": f"greedy_{label}",
                "time_sec": round(elapsed, 4),
                "status": "COLORED",
                "hard_violations": hard,
                "periods_used": ncol,
                "n_tasks": len(tasks),
                "n_edges": G.number_of_edges(),
                "violation_breakdown": by_type,
            }
        )
        if verbose:
            print(
                f"[greedy:{label}] tasks={len(tasks)} edges={G.number_of_edges()} "
                f"色数(时段数)={ncol} 耗时={elapsed:.4f}s 硬冲突={hard} 明细={by_type}"
            )
    return results


if __name__ == "__main__":
    import sys

    scale = sys.argv[1] if len(sys.argv) > 1 else "s60"
    print(f"=== 贪心图着色基线 ({scale}) ===")
    print(f"networkx {nx.__version__}, DSATUR strategy 支持: {available_strategies()}")
    run(scale)