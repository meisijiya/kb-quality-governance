# -*- coding: utf-8 -*-
"""
独立的冲突检测库 —— 关键: 不信任任何求解器, 自己重新算一遍。

detect_conflicts(schedule, data) 检测 6 类冲突:
  1. room_occupied      同一时段同一教室被多任务占用
  2. teacher_conflict   同一时段同一教师被多任务占用
  3. class_conflict     同一时段同一班级被多任务占用
  4. capacity_short     教室容量 < required_capacity
  5. type_mismatch      needs_lab 的任务被排进非 lab 教室
  6. period_out_of_range 时段索引越界 (或落在教师不可用时段)

schedule: list of dict, 每项:
  {"task_id", "period"(int 0..N_PERIODS-1), "room_id", "teacher_id",
   "class_ids": [...], "required_capacity", "needs_lab"}
"""
from collections import defaultdict


def _conflict_entry(ctype, involved, severity, detail=""):
    return {
        "type": ctype,
        "involved_tasks": sorted(involved),
        "severity": severity,
        "detail": detail,
    }


def detect_conflicts(schedule, data):
    """独立实现: 从 schedule 出发重算全部硬约束违反"""
    n_periods = data["n_periods"]
    rooms = {r["room_id"]: r for r in data["rooms"]}
    teachers = {t["teacher_id"]: t for t in data["teachers"]}
    conflicts = []

    # ---- 6. 时段越界 ----
    valid = []
    for it in schedule:
        p = it.get("period")
        if not isinstance(p, int) or p < 0 or p >= n_periods:
            conflicts.append(
                _conflict_entry(
                    "period_out_of_range",
                    [it.get("task_id", "?")],
                    "hard",
                    f"period={p} 超出合法范围 [0,{n_periods - 1}]",
                )
            )
            continue
        valid.append(it)

    # ---- 1. 教室占用 ----
    by_room_slot = defaultdict(list)
    for it in valid:
        by_room_slot[(it.get("room_id"), it["period"])].append(it)
    for (rid, p), items in by_room_slot.items():
        if rid is None or len(items) < 2:
            continue
        conflicts.append(
            _conflict_entry(
                "room_occupied",
                [i["task_id"] for i in items],
                "hard",
                f"教室 {rid} 在 period={p} 被 {len(items)} 个任务同时占用",
            )
        )

    # ---- 2. 教师冲突 ----
    by_t_slot = defaultdict(list)
    for it in valid:
        by_t_slot[(it.get("teacher_id"), it["period"])].append(it)
    for (tid, p), items in by_t_slot.items():
        if tid is None or len(items) < 2:
            continue
        conflicts.append(
            _conflict_entry(
                "teacher_conflict",
                [i["task_id"] for i in items],
                "hard",
                f"教师 {tid} 在 period={p} 被排了 {len(items)} 节课",
            )
        )

    # ---- 3. 班级冲突 ----
    by_c_slot = defaultdict(list)
    for it in valid:
        for cid in it.get("class_ids", []) or []:
            by_c_slot[(cid, it["period"])].append(it)
    for (cid, p), items in by_c_slot.items():
        if len(items) < 2:
            continue
        conflicts.append(
            _conflict_entry(
                "class_conflict",
                [i["task_id"] for i in items],
                "hard",
                f"班级 {cid} 在 period={p} 被排了 {len(items)} 节课",
            )
        )

    # ---- 4. 容量不足 / 5. 类型不匹配 ----
    for it in valid:
        rid = it.get("room_id")
        room = rooms.get(rid)
        if room is None:
            conflicts.append(
                _conflict_entry(
                    "type_mismatch",
                    [it["task_id"]],
                    "hard",
                    f"教室 {rid} 不存在",
                )
            )
            continue
        need = it.get("required_capacity", 0)
        if room["capacity"] < need:
            conflicts.append(
                _conflict_entry(
                    "capacity_short",
                    [it["task_id"]],
                    "hard",
                    f"{it['task_id']} 需 {need} 人, 教室 {rid} 仅 {room['capacity']} 人",
                )
            )
        if it.get("needs_lab") and room["type"] != "lab":
            conflicts.append(
                _conflict_entry(
                    "type_mismatch",
                    [it["task_id"]],
                    "hard",
                    f"{it['task_id']} 需要 lab, 却排进 {room['type']} 教室 {rid}",
                )
            )

    # ---- 教师不可用时段 (同 6 类中的越界子情形, 单列便于论文展示) ----
    for it in valid:
        t = teachers.get(it.get("teacher_id"))
        if t and it["period"] in t.get("unavailable_slots", []):
            conflicts.append(
                _conflict_entry(
                    "period_out_of_range",
                    [it["task_id"]],
                    "hard",
                    f"{it['task_id']} 排在教师 {t['teacher_id']} 的不可用时段 {it['period']}",
                )
            )

    return conflicts


def count_hard(conflicts):
    return sum(1 for c in conflicts if c["severity"] == "hard")


def conflicts_to_schedule(tasks, period_of, room_of):
    """把 solver 的结果转成 detect_conflicts 认识的 schedule 格式"""
    sched = []
    for t in tasks:
        tid = t["task_id"]
        if period_of.get(tid) is None:
            continue
        sched.append(
            {
                "task_id": tid,
                "period": int(period_of[tid]),
                "room_id": room_of.get(tid),
                "teacher_id": t["teacher_id"],
                "class_ids": t["class_ids"],
                "required_capacity": t["required_capacity"],
                "needs_lab": t["needs_lab"],
            }
        )
    return sched