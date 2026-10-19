# -*- coding: utf-8 -*-
"""
冲突检测与可视化数据导出 (不画图, 只输出结构化数据供前端用)

输出:
  schedule.json   课表 (每个任务一行: 时段/教室/教师/班级)
  conflicts.json  冲突清单 (type / involved_tasks / severity)
  matrix.csv      time_slot x room 占用矩阵

冲突检测用 conflict_lib.detect_conflicts —— 与求解器完全独立实现,
不信任求解器自报的结果, 既是系统功能也是测试手段。
"""
import os
import csv
import json
import sys

from gen_data import load_json, with_buildings, make_tasks, slot_name
from conflict_lib import detect_conflicts, count_hard
import solve_cpsat

HERE = os.path.dirname(os.path.abspath(__file__))


def export(scale="s60", time_limit=60):
    data = with_buildings(load_json(os.path.join(HERE, f"data_{scale}.json")))
    tasks = make_tasks(data)
    print(f"=== 求解并导出可视化数据 ({scale}) ===")
    r = solve_cpsat.solve(tasks, data, time_limit=time_limit, verbose=True, label="viz")
    if r["status"] not in ("OPTIMAL", "FEASIBLE"):
        print("未求出可行解, 无法导出")
        return None
    schedule = r["_schedule"]

    # ---- 1. 课表 ----
    roommap = {x["room_id"]: x for x in data["rooms"]}
    course_name = {c["course_id"]: c["name"] for c in data["courses"]}
    rows = []
    for it in sorted(schedule, key=lambda x: (x["period"], x["room_id"] or "")):
        cid = it["task_id"].split("#")[0]
        rows.append(
            {
                "task_id": it["task_id"],
                "course_id": cid,
                "course_name": course_name.get(cid, cid),
                "period": it["period"],
                "slot_name": slot_name(it["period"]),
                "room_id": it["room_id"],
                "room_capacity": roommap[it["room_id"]]["capacity"],
                "room_type": roommap[it["room_id"]]["type"],
                "building": roommap[it["room_id"]]["building"],
                "teacher_id": it["teacher_id"],
                "class_ids": it["class_ids"],
                "required_capacity": it["required_capacity"],
                "needs_lab": it["needs_lab"],
            }
        )
    p = os.path.join(HERE, "schedule.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"[viz] schedule.json 写入 {len(rows)} 条")

    # ---- 2. 冲突清单 (独立检测) ----
    conflicts = detect_conflicts(schedule, data)
    p = os.path.join(HERE, "conflicts.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            {
                "scale": scale,
                "total": len(conflicts),
                "hard": count_hard(conflicts),
                "by_type": {
                    t: sum(1 for c in conflicts if c["type"] == t)
                    for t in sorted({c["type"] for c in conflicts})
                },
                "conflicts": conflicts,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[viz] conflicts.json 写入 {len(conflicts)} 条 (硬冲突 {count_hard(conflicts)})")

    # ---- 3. time_slot x room 占用矩阵 ----
    room_ids = [x["room_id"] for x in data["rooms"]]
    occ = {}
    for it in schedule:
        occ[(it["period"], it["room_id"])] = it["task_id"]
    p = os.path.join(HERE, "matrix.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["period", "slot_name"] + room_ids)
        for per in range(data["n_periods"]):
            w.writerow([per, slot_name(per)] + [occ.get((per, rid), "") for rid in room_ids])
    print(f"[viz] matrix.csv 写入 {data['n_periods']} x {len(room_ids)}")
    return rows, conflicts


if __name__ == "__main__":
    export(sys.argv[1] if len(sys.argv) > 1 else "s60")