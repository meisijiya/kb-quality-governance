# -*- coding: utf-8 -*-
"""
软约束权重实验 —— 论文的算法贡献点

三个软约束 (全部**线性化进 CP-SAT 目标函数**, 而不是事后在解上打分):
  ① w1 同一教师连排 —— 惩罚"连续 maxc+1 节课"的全占窗口。
     一个长度 L 的连排段, 其长度为 maxc+1 的全占窗口恰有 L-maxc 个,
     因此窗口计数 == 连排违反量, 数值上精确等价, 而不是近似。
  ② w2 容量浪费 —— gap[t] = 教室容量(所选) - required[t], 是 x 的线性函数:
     gap[t] = sum_r capacity[r]*x[t,r] - required[t]
  ③ w3 同一班级跨教学楼 —— y[c,B] = 该班是否用过楼 B,
     最小化 sum_{c,B} y[c,B] 等价于最小化 (用到的不同楼数 - 1)。

四组权重:
  baseline     (1,1,1)
  balanced     (2,2,2)
  focus_teacher(10,1,1)
  focus_capacity(1,10,1)

重要修正记录 (实测踩出来的):
  v1 最初把教室容量只分 30/60/100 三档, 且人数恰好取 30/60/80,
     导致每个任务的最小容量浪费成为常数, w2 完全无从优化,
     四组权重结果一模一样。
  v2 最初教师不可用时段只有 2~5 个, 教师负载太松, 连排根本不会发生,
     w1 恒为 0。
  v3 最初用"保持硬约束不变的加权局部搜索"来做, focus_capacity 与 baseline
     仍然完全相同 —— 爬山法在容量项已占绝对多数时两者收敛到同一局部最优。
     -> 改为直接把软约束线性化进 CP-SAT 目标, 由求解器做全局权衡。
  v4 窗口变量只写了单向蕴含, 导致连排惩罚恒为 0。必须双向等价。
  v5 OR 编码不能用 AddBoolOr + AddBoolAnd(OnlyEnforceIf(Not)) 的组合,
     CP-SAT 9.15.6755 会判 INFEASIBLE。必须用 AddMaxEquality。
输出 weight_result.csv
"""
import os
import csv
import time
from collections import defaultdict

from ortools.sat.python import cp_model

from gen_data import load_json, with_buildings, make_tasks
from conflict_lib import detect_conflicts, count_hard
import solve_cpsat

HERE = os.path.dirname(os.path.abspath(__file__))
PERIODS_PER_DAY = 6

WEIGHT_SETS = [
    ("baseline", (1, 1, 1)),
    ("balanced", (2, 2, 2)),
    ("focus_teacher", (10, 1, 1)),
    ("focus_capacity", (1, 10, 1)),
]

TIME_LIMIT = 60
# 高利用率场景每组需要更长时间才能拿到有意义的解
HIGH_UTIL_TIME_LIMIT = 240


def build_high_util(scale="s150", fixed_rooms=15):
    """
    高利用率场景: 课程规模取 s150, 但**教室数固定为 15 间**(模拟一所真实学院
    固定的教学资源, 而不是随课程数一起膨胀的"虚拟资源")。

    为什么要这个场景 —— 本 POC 最关键的实测结论:
      教室利用率 = 任务数 / (教室数 x 时段数)。
      s60/15 间/30 时段 = 127/450 = 28%  -> 任何任务都能拿到最贴合的教室,
        三个软约束同时处于各自最优, 任何权重都得到同一张课表 (无区分度)。
      s150/15 间/30 时段 = 343/450 = 76% -> 教室开始抢手, 但模型大到
        240 秒仍不收敛, 只能拿到 FEASIBLE, 结果不可复现 (见 RESULT.md 6.2)。
    """
    data = with_buildings(load_json(os.path.join(HERE, f"data_{scale}.json")))
    rooms_all = data["rooms"]
    tiers = [35, 50, 65, 80, 100, 130]
    must = [r for r in rooms_all if r["type"] == "lab"]
    for c in tiers:  # 每个容量档至少保留 1 间, 否则高层需求无解
        cand = [r for r in rooms_all if r["capacity"] == c and r not in must]
        if cand:
            must.append(cand[0])
    others = [r for r in rooms_all if r not in must]
    sel = must + others[: max(0, fixed_rooms - len(must))]
    data = with_buildings(dict(data, rooms=sel))
    for t in data["teachers"]:
        t["max_consecutive"] = 1  # 真实学院常见偏好: 教师尽量不连排
    tasks = make_tasks(data)
    util = len(tasks) / (len(sel) * data["n_periods"]) * 100
    return data, tasks, util


def add_soft_objective(model, x, start, present, tasks, data, w):
    """把三个软约束线性化进目标函数, 返回 (objective_expr, 统计用容器)"""
    rooms = {r["room_id"]: r for r in data["rooms"]}
    buildings = data["buildings"]
    teachers = {t["teacher_id"]: t for t in data["teachers"]}
    tmap = {t["task_id"]: t for t in tasks}

    terms = []

    # ---------- w2 容量浪费 ----------
    gaps = []
    for tid, roommap in x.items():
        req = tmap[tid]["required_capacity"]
        g = model.NewIntVar(0, 200, f"gap[{tid}]")
        model.Add(g == sum(rooms[r]["capacity"] * lit for r, lit in roommap.items()) - req)
        gaps.append(g)
    terms.append(w[1] * sum(gaps))

    # ---------- w1 教师连排 ----------
    # occ[t,p] <=> start[t] == p
    occ = {}
    _teachers = {t["teacher_id"]: t for t in data["teachers"]}
    for tid, sv in start.items():
        vals = solve_cpsat.allowed_periods(tmap[tid], _teachers, data["n_periods"])
        b = {}
        for p in vals:
            v = model.NewBoolVar(f"occ[{tid},{p}]")
            model.Add(sv == p).OnlyEnforceIf(v)
            model.Add(sv != p).OnlyEnforceIf(v.Not())
            b[p] = v
        occ[tid] = b

    by_teacher = defaultdict(list)
    for tid, t in tmap.items():
        by_teacher[t["teacher_id"]].append(tid)

    consec_terms = []
    for tid_teacher, tids in by_teacher.items():
        maxc = teachers[tid_teacher].get("max_consecutive", 2)
        win = maxc + 1  # 窗口长度 = maxc+1, 全占窗口数 == 连排违反量
        if win > PERIODS_PER_DAY:
            continue
        for day in range(PERIODS_PER_DAY):
            day_occ = {}
            for p in range(PERIODS_PER_DAY):
                lits = [
                    occ[tid][day * PERIODS_PER_DAY + p]
                    for tid in tids
                    if (day * PERIODS_PER_DAY + p) in occ[tid]
                ]
                if not lits:
                    continue
                if len(lits) == 1:
                    day_occ[p] = lits[0]
                else:
                    o = model.NewBoolVar(f"tocc[{tid_teacher},{day},{p}]")
                    # 必须用 AddMaxEquality (布尔上的 OR)。
                    # 实测陷阱: 用 AddBoolOr(lits).OnlyEnforceIf(o) 配
                    # AddBoolAnd(lits).OnlyEnforceIf(o.Not()) 写等价 OR 时,
                    # CP-SAT 9.15.6755 会直接判 INFEASIBLE (两个方向单独都 OPTIMAL,
                    # 合在一起才炸)。
                    model.AddMaxEquality(o, lits)
                    day_occ[p] = o
            for p0 in range(0, PERIODS_PER_DAY - win + 1):
                ps = [p0 + k for k in range(win)]
                if not all(q in day_occ for q in ps):
                    continue
                v = model.NewBoolVar(f"cons[{tid_teacher},{day},{p0}]")
                lits = [day_occ[q] for q in ps]
                # 必须是**双向等价**。只写正向 (v=1 => 全占) 的话 v 恒可取 0,
                # 连排惩罚会被整体抹掉。
                # 反向用子句级 AddBoolOr([...Not()]), 避免上面记录的陷阱。
                model.AddBoolAnd(lits).OnlyEnforceIf(v)
                model.AddBoolOr([L.Not() for L in lits]).OnlyEnforceIf(v.Not())
                consec_terms.append(v)
    if consec_terms:
        terms.append(w[0] * sum(consec_terms))

    # ---------- w3 班级跨教学楼 ----------
    class_terms = []
    bldg_of = defaultdict(list)
    for rid, r in rooms.items():
        bldg_of[r["building"]].append(rid)
    z = {}
    for tid, roommap in x.items():
        for B in buildings:
            lits = [roommap[r] for r in bldg_of.get(B, []) if r in roommap]
            if not lits:
                continue
            v = model.NewBoolVar(f"z[{tid},{B}]")
            if len(lits) == 1:
                model.Add(lits[0] == v)
            else:
                model.AddMaxEquality(v, lits)
            z[(tid, B)] = v
    by_class = defaultdict(list)
    for tid, t in tmap.items():
        for cid in t["class_ids"]:
            by_class[cid].append(tid)
    for cid, tids in by_class.items():
        for B in buildings:
            lits = [z[(tid, B)] for tid in tids if (tid, B) in z]
            if not lits:
                continue
            v = model.NewBoolVar(f"y[{cid},{B}]")
            if len(lits) == 1:
                model.Add(lits[0] == v)
            else:
                model.AddMaxEquality(v, lits)
            class_terms.append(v)
    if class_terms:
        terms.append(w[2] * sum(class_terms))

    obj = sum(terms)
    model.Minimize(obj)
    return obj, {"gaps": gaps, "consec": consec_terms, "cls": class_terms}


def measure(assign, tasks, data):
    """在解上独立统计三个软约束的真实数量 (用于校验建模是否正确)"""
    roommap = {r["room_id"]: r for r in data["rooms"]}
    building = {r["room_id"]: r["building"] for r in data["rooms"]}
    teachers = {t["teacher_id"]: t for t in data["teachers"]}
    tmap = {t["task_id"]: t for t in tasks}

    by_t = defaultdict(lambda: defaultdict(set))
    for tid, (p, _r) in assign.items():
        by_t[tmap[tid]["teacher_id"]][p // PERIODS_PER_DAY].add(p % PERIODS_PER_DAY)
    # 与模型口径一致: 每个连排段长度 L 贡献 max(0, L-maxc), 逐段累加。
    consec = 0
    for tid_, days in by_t.items():
        maxc = teachers[tid_].get("max_consecutive", 2)
        for _d, ps in days.items():
            run = 0
            for pp in range(PERIODS_PER_DAY + 1):
                if pp in ps:
                    run += 1
                else:
                    consec += max(0, run - maxc)
                    run = 0

    waste = sum(
        roommap[rid]["capacity"] - tmap[tid]["required_capacity"]
        for tid, (_p, rid) in assign.items()
    )
    by_class = defaultdict(set)
    for tid, (_p, rid) in assign.items():
        for cid in tmap[tid]["class_ids"]:
            by_class[cid].add(building[rid])
    spread = sum(len(v) - 1 for v in by_class.values())
    return {
        "teacher_consecutive": consec,
        "capacity_waste": waste,
        "building_spread": spread,
    }


def run_group(tasks, data, w, label, time_limit=TIME_LIMIT, tight_periods=None):
    tmap = {t["task_id"]: t for t in tasks}
    model, x, start, present = solve_cpsat.build_model(tasks, data, relax_level=0)
    # 资源收紧: 把可用时段数压到 tight_periods (模拟紧凑排课)。
    if tight_periods is not None:
        for tid, sv in start.items():
            model.AddLinearConstraint(sv, 0, tight_periods - 1)
    n_var_base = len(model.proto.variables)
    add_soft_objective(model, x, start, present, tasks, data, w)
    n_var_soft = len(model.proto.variables)
    n_con = len(model.proto.constraints)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    t0 = time.perf_counter()
    status = solver.Solve(model)
    el = time.perf_counter() - t0
    sname = solver.StatusName(status)
    out = {
        "weight_set": label,
        "w_teacher": w[0],
        "w_capacity": w[1],
        "w_building": w[2],
        "status": sname,
        "time_sec": round(el, 3),
        "n_tasks": len(tasks),
        "n_vars_hard_only": n_var_base,
        "n_vars_with_soft": n_var_soft,
        "n_constraints": n_con,
    }
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assign = {}
        for tid in x:
            assign[tid] = (solver.Value(start[tid]), None)
        for tid, rm in x.items():
            for rid, lit in rm.items():
                if solver.Value(lit):
                    assign[tid] = (assign[tid][0], rid)
                    break
        costs = measure(assign, tasks, data)
        sched = [
            {
                "task_id": tid,
                "period": p,
                "room_id": rid,
                "teacher_id": tmap[tid]["teacher_id"],
                "class_ids": tmap[tid]["class_ids"],
                "required_capacity": tmap[tid]["required_capacity"],
                "needs_lab": tmap[tid]["needs_lab"],
            }
            for tid, (p, rid) in assign.items()
        ]
        out["hard_violations"] = count_hard(detect_conflicts(sched, data))
        out["objective"] = solver.ObjectiveValue()
        out["best_bound"] = round(solver.BestObjectiveBound(), 2)
        out.update(costs)
        out["soft_total"] = sum(costs.values())
        out["_assign"] = assign
    else:
        out["hard_violations"] = ""
        out["teacher_consecutive"] = ""
        out["capacity_waste"] = ""
        out["building_spread"] = ""
        out["soft_total"] = ""
    return out


def main(scale="s60", tight_periods=None, mode="loose", time_limit=None):
    if mode == "high-util":
        data, tasks, util = build_high_util()
        scen = f"高利用率(s150课程/15教室, 利用率{util:.0f}%)"
        tl = time_limit or HIGH_UTIL_TIME_LIMIT
    else:
        data = with_buildings(load_json(os.path.join(HERE, f"data_{scale}.json")))
        tasks = make_tasks(data)
        util = len(tasks) / (len(data["rooms"]) * data["n_periods"]) * 100
        scen = f"宽松({scale}, 利用率{util:.0f}%)"
        if tight_periods:
            scen = f"紧凑({scale}, {tight_periods} 时段, 利用率{util:.0f}%)"
        tl = time_limit or TIME_LIMIT

    print(f"=== 软约束权重实验 [{scen}] ===")
    print(f"每个权重组 = 一次完整的 CP-SAT 建模+求解, 软约束已线性化进目标函数")
    print(f"超时 = {tl}s, 8 workers\n")

    hdr = f"{'权重组':<18}{'状态':<11}{'教师连排':>9}{'容量浪费':>10}{'跨楼':>7}{'软合计':>9}{'硬冲突':>8}{'目标值':>10}{'耗时s':>9}"
    print(hdr)
    print("-" * len(hdr))

    rows = []
    for label, w in WEIGHT_SETS:
        r = run_group(tasks, data, w, label, time_limit=tl, tight_periods=tight_periods)
        r["scenario"] = scen
        rows.append(r)
        print(
            f"{label:<18}{r['status']:<11}{str(r['teacher_consecutive']):>9}"
            f"{str(r['capacity_waste']):>10}{str(r['building_spread']):>7}"
            f"{str(r['soft_total']):>9}{str(r['hard_violations']):>8}"
            f"{str(round(r['objective'],1)) if 'objective' in r else '-':>10}{r['time_sec']:>9.2f}"
        )

    if rows and "n_vars_with_soft" in rows[0]:
        print(
            f"\n模型规模: 硬约束模型变量={rows[0]['n_vars_hard_only']}, "
            f"加软约束后变量={rows[0]['n_vars_with_soft']}, 约束={rows[0]['n_constraints']}"
        )

    FIELDS = [
        "scale", "scenario", "weight_set", "w_teacher", "w_capacity", "w_building",
        "status", "teacher_consecutive", "capacity_waste", "building_spread",
        "soft_total", "hard_violations", "objective", "best_bound",
        "n_vars_hard_only", "n_vars_with_soft", "n_constraints", "time_sec",
    ]
    out_csv = os.path.join(HERE, "weight_result.csv")
    exists = os.path.exists(out_csv)
    with open(out_csv, "w" if not exists else "a", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if not exists:
            wr.writeheader()
        for r in rows:
            r2 = dict(r)
            r2["scale"] = scale
            if "objective" in r2:
                r2["objective"] = round(r2["objective"], 2)
            wr.writerow(r2)
    print(f"[soft] 已写入 {out_csv}")
    return rows


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("scale", nargs="?", default="s60")
    ap.add_argument("--mode", choices=["loose", "high-util", "both"], default="both")
    ap.add_argument("--time-limit", type=int, default=None)
    a = ap.parse_args()
    if a.mode in ("loose", "both"):
        main(a.scale, mode="loose", time_limit=a.time_limit)
        print()
    if a.mode in ("high-util", "both"):
        main(a.scale, mode="high-util", time_limit=a.time_limit)