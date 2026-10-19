# -*- coding: utf-8 -*-
"""
CP-SAT 精确求解 (OR-Tools)

模型:
  变量
    assign[task_id, room_id]  布尔  —— 该任务是否占用该教室
    start[task_id]            整数  —— 该任务的时段 (0..N_PERIODS-1)
    present[task_id]          布尔  —— 任务的"存在"指示 (用于 OptionalIntervalVar)
  硬约束
    H1 每任务恰好一个教室          AddExactlyOne
    H2 同时段同一教室至多一任务      NoOverlap(按房间)
    H3 同时段同一教师至多一任务      NoOverlap(按教师)
    H4 同时段同一班级至多一任务      NoOverlap(按班级)
    H5 教室类型匹配 (needs_lab->lab) 通过变量过滤: 不合法教室根本不存在变量
    H6 教室容量 >= required_capacity  同上, 只为容量足够的教室建变量
    H7 教师不可用时段排除            限定 start 的取值域

超时: solver.parameters.max_time_in_seconds = 30
"""
import os
import time

from ortools.sat.python import cp_model

from gen_data import load_json, with_buildings, make_tasks
from conflict_lib import detect_conflicts, count_hard, conflicts_to_schedule

TIME_LIMIT = 30


def feasible_rooms(task, rooms):
    """H5 + H6: 只保留类型与容量都合法的教室"""
    out = []
    for r in rooms:
        if r["capacity"] < task["required_capacity"]:
            continue
        if task["needs_lab"] and r["type"] != "lab":
            continue
        out.append(r)
    return out


def allowed_periods(task, teachers, n_periods):
    """H7: 剔除该教师不可用的时段"""
    unavail = set(teachers[task["teacher_id"]]["unavailable_slots"])
    return [p for p in range(n_periods) if p not in unavail]


def build_model(tasks, data, relax_level=0):
    """
    relax_level 用于 INFEASIBLE 时的逐级放宽实验:
      0 = 全部硬约束 (基准)
      1 = 放宽 H7 (不排除教师不可用时段)
      2 = 再放宽 H6 (允许容量不足)
    返回 (model, x, start, present)
    """
    rooms = data["rooms"]
    teachers = {t["teacher_id"]: t for t in data["teachers"]}
    n_periods = data["n_periods"]

    model = cp_model.CpModel()
    x, start, present = {}, {}, {}

    for t in tasks:
        tid = t["task_id"]
        rs = feasible_rooms(t, rooms) if relax_level < 2 else rooms
        lits = [model.NewBoolVar(f"x[{tid},{r['room_id']}]") for r in rs]
        x[tid] = dict(zip([r["room_id"] for r in rs], lits))
        model.AddExactlyOne(lits)  # H1

        dom = (
            allowed_periods(t, teachers, n_periods)
            if relax_level < 1
            else list(range(n_periods))
        )
        start[tid] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(dom), f"start[{tid}]"
        )
        present[tid] = model.NewBoolVar(f"present[{tid}]")
        # 关键1: present 必须恒为 1。否则 CP-SAT 会把所有 present 置 0,
        #         使 NoOverlap 全部变成空约束 -> 退化成"所有任务挤在同一时段"的伪最优解。
        model.Add(present[tid] == 1)
        # 关键2: 蕴含方向必须是 lit => present (选中某个教室 => 该区间存在)。
        #         若误写成 present => lit, 因为 present 恒为 1, 会强制所有教室
        #         字面量同时为 1, 与 AddExactlyOne 直接矛盾 -> 秒判 INFEASIBLE。
        for lit in lits:
            model.AddImplication(lit, present[tid])

    def add_nooverlap(groups, tag, presence_of):
        """H2/H3/H4: 同组内同时段至多一个任务

        groups: {group_key: [task_id, ...]}
        presence_of(task_id, group_key) -> 该区间是否存在的布尔字面量
        """
        for key, tids in groups.items():
            ivs = []
            for tid in tids:
                p = presence_of(tid, key)
                ivs.append(
                    model.NewOptionalIntervalVar(
                        start[tid], 1, start[tid] + 1, p, f"{tag}:{key}:{tid}"
                    )
                )
            if len(ivs) > 1:
                model.AddNoOverlap(ivs)

    # H2 教室维度。
    # 关键3: 教室维度的区间存在性必须用"该任务选中该教室"的字面量 x[tid][rid],
    #        不能用恒为 1 的 present[tid]。否则一个任务会同时占住它所有候选教室,
    #        NoOverlap 立刻超载 -> 秒判 INFEASIBLE。
    room_groups = {}
    for tid, roommap in x.items():
        for rid in roommap:
            room_groups.setdefault(rid, []).append(tid)
    add_nooverlap(room_groups, "room", lambda tid, rid: x[tid][rid])

    # H3 教师维度
    tmap = {t["task_id"]: t for t in tasks}
    teacher_groups = {}
    for tid, t in tmap.items():
        teacher_groups.setdefault(t["teacher_id"], []).append(tid)
    add_nooverlap(teacher_groups, "teacher", lambda tid, key: present[tid])

    # H4 班级维度
    class_groups = {}
    for tid, t in tmap.items():
        for cid in t["class_ids"]:
            class_groups.setdefault(cid, []).append(tid)
    add_nooverlap(class_groups, "class", lambda tid, key: present[tid])

    return model, x, start, present


def solve(tasks, data, time_limit=TIME_LIMIT, relax_level=0, verbose=True, label=""):
    model, x, start, present = build_model(tasks, data, relax_level)
    n_var = len(model.proto.variables)
    n_con = len(model.proto.constraints)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = False

    t0 = time.perf_counter()
    status = solver.Solve(model)
    elapsed = time.perf_counter() - t0

    status_str = solver.StatusName(status)
    result = {
        "label": label,
        "time_sec": round(elapsed, 3),
        "status": status_str,
        "status_code": int(status),
        "hard_violations": None,
        "periods_used": None,
        "n_tasks": len(tasks),
        "n_vars": n_var,
        "n_constraints": n_con,
        "relax_level": relax_level,
    }

    if verbose:
        print(
            f"[cpsat{(':' + label) if label else ''}] 任务数={len(tasks)} "
            f"变量数={n_var} 约束数={n_con} 状态={status_str} "
            f"耗时={elapsed:.3f}s relax_level={relax_level}"
        )

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        period_of, room_of = {}, {}
        for tid in x:
            p = solver.Value(start[tid])
            period_of[tid] = p
            for rid, lit in x[tid].items():
                if solver.Value(lit):
                    room_of[tid] = rid
                    break
        sched = conflicts_to_schedule(tasks, period_of, room_of)
        conf = detect_conflicts(sched, data)
        hard = count_hard(conf)
        by_type = {}
        for c in conf:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        result["hard_violations"] = hard
        result["periods_used"] = len(set(period_of.values()))
        result["violation_breakdown"] = by_type
        if verbose:
            print(
                f"    独立复核: 硬冲突={hard} 使用时段数={result['periods_used']} "
                f"明细={by_type}"
            )
        result["_schedule"] = sched
    else:
        if verbose:
            print("    未找到可行解 (INFEASIBLE / UNKNOWN)")
    return result


def run_with_relaxation(tasks, data, scale="s60"):
    """INFEASIBLE 时逐级放宽约束 —— 这个过程本身是论文实验素材"""
    print(f"\n=== 约束放宽阶梯实验 ({scale}) ===")
    descs = {
        0: "基准: 全部硬约束 (含教师不可用时段排除、容量、类型)",
        1: "放宽 H7: 不再排除教师不可用时段",
        2: "放宽 H6: 不再要求容量>=人数 (任何教室都可排)",
    }
    rows = []
    for lvl in [0, 1, 2]:
        print(f"\n-- relax_level={lvl}: {descs[lvl]}")
        r = solve(tasks, data, relax_level=lvl, label=f"L{lvl}")
        r["relax_desc"] = descs[lvl]
        rows.append(r)
        if r["status"] in ("OPTIMAL", "FEASIBLE"):
            print(f"   >> 在 relax_level={lvl} 找到可行解, 放宽实验到此为止")
            break
    return rows


if __name__ == "__main__":
    import sys

    scale = sys.argv[1] if len(sys.argv) > 1 else "s60"
    here = os.path.dirname(os.path.abspath(__file__))
    data = with_buildings(load_json(os.path.join(here, f"data_{scale}.json")))
    tasks = make_tasks(data)
    print(f"=== CP-SAT 求解 ({scale}) ===")
    r = solve(tasks, data, label="base")
    if r["status"] not in ("OPTIMAL", "FEASIBLE"):
        run_with_relaxation(tasks, data, scale)