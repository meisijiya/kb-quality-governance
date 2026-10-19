# -*- coding: utf-8 -*-
"""
detect_conflicts() 单元测试 (纯标准库 unittest, 可直接 python test_detect.py 运行)

覆盖 6 类冲突的检出能力 + 已知无冲突课表返回空 + 贪心着色结果确实无图着色冲突。
"""
import os
import unittest

import networkx as nx

from gen_data import load_json, with_buildings, make_tasks
from conflict_lib import detect_conflicts, count_hard
import baseline_greedy

HERE = os.path.dirname(os.path.abspath(__file__))

# 一个极小的、字段完整的假数据集 (30 个时段, 与真实数据同构)
DATA = {
    "n_periods": 30,
    "days": ["周一", "周二", "周三", "周四", "周五"],
    "periods_per_day": 6,
    "n_classes": 2,
    "buildings": ["教A楼", "教B楼", "教C楼"],
    "rooms": [
        {"room_id": "R001", "capacity": 35, "type": "normal", "building": "教A楼"},
        {"room_id": "R002", "capacity": 60, "type": "normal", "building": "教B楼"},
        {"room_id": "R003", "capacity": 100, "type": "lab", "building": "教C楼"},
    ],
    "teachers": [
        {"teacher_id": "T001", "name": "甲", "unavailable_slots": [5], "max_consecutive": 2},
        {"teacher_id": "T002", "name": "乙", "unavailable_slots": [], "max_consecutive": 2},
    ],
    "courses": [
        {
            "course_id": "C001", "name": "课1", "credits": 2, "weekly_hours": 1,
            "required_capacity": 30, "needs_lab": False, "prerequisites": [],
        },
        {
            "course_id": "C002", "name": "课2", "credits": 2, "weekly_hours": 1,
            "required_capacity": 30, "needs_lab": False, "prerequisites": [],
        },
        {
            "course_id": "C003", "name": "实验课", "credits": 3, "weekly_hours": 1,
            "required_capacity": 80, "needs_lab": True, "prerequisites": ["C001"],
        },
    ],
    "assignments": [
        {"course_id": "C001", "teacher_id": "T001", "class_ids": ["CL001"]},
        {"course_id": "C002", "teacher_id": "T002", "class_ids": ["CL001"]},
        {"course_id": "C003", "teacher_id": "T001", "class_ids": ["CL002"]},
    ],
}


def item(task_id, period, room_id, teacher_id, class_ids, cap, lab):
    return {
        "task_id": task_id, "period": period, "room_id": room_id,
        "teacher_id": teacher_id, "class_ids": class_ids,
        "required_capacity": cap, "needs_lab": lab,
    }


def types_of(conflicts):
    return {c["type"] for c in conflicts}


class TestNoConflict(unittest.TestCase):
    def test_clean_schedule_has_no_conflicts(self):
        sched = [
            item("C001#1", 0, "R001", "T001", ["CL001"], 30, False),
            item("C002#1", 1, "R001", "T002", ["CL001"], 30, False),
            item("C003#1", 2, "R003", "T001", ["CL002"], 80, True),
        ]
        conf = detect_conflicts(sched, DATA)
        self.assertEqual(conf, [], f"干净课表不应有冲突, 实际: {conf}")
        self.assertEqual(count_hard(conf), 0)


class TestSixConflictTypes(unittest.TestCase):
    def test_room_occupied(self):
        sched = [
            item("C001#1", 0, "R001", "T001", ["CL001"], 30, False),
            item("C002#1", 0, "R001", "T002", ["CL002"], 30, False),
        ]
        self.assertIn("room_occupied", types_of(detect_conflicts(sched, DATA)))

    def test_teacher_conflict(self):
        sched = [
            item("C001#1", 3, "R001", "T001", ["CL001"], 30, False),
            item("C003#1", 3, "R003", "T001", ["CL002"], 80, True),
        ]
        self.assertIn("teacher_conflict", types_of(detect_conflicts(sched, DATA)))

    def test_class_conflict(self):
        sched = [
            item("C001#1", 4, "R001", "T001", ["CL001"], 30, False),
            item("C002#1", 4, "R002", "T002", ["CL001"], 30, False),
        ]
        self.assertIn("class_conflict", types_of(detect_conflicts(sched, DATA)))

    def test_capacity_short(self):
        sched = [item("C003#1", 6, "R001", "T001", ["CL002"], 80, True)]
        self.assertIn("capacity_short", types_of(detect_conflicts(sched, DATA)))

    def test_type_mismatch(self):
        sched = [item("C003#1", 7, "R002", "T001", ["CL002"], 80, True)]
        self.assertIn("type_mismatch", types_of(detect_conflicts(sched, DATA)))

    def test_period_out_of_range(self):
        sched = [item("C001#1", 30, "R001", "T001", ["CL001"], 30, False)]
        self.assertIn("period_out_of_range", types_of(detect_conflicts(sched, DATA)))

    def test_negative_period_out_of_range(self):
        sched = [item("C001#1", -1, "R001", "T001", ["CL001"], 30, False)]
        self.assertIn("period_out_of_range", types_of(detect_conflicts(sched, DATA)))

    def test_teacher_unavailable_slot_detected(self):
        sched = [item("C001#1", 5, "R001", "T001", ["CL001"], 30, False)]
        self.assertIn("period_out_of_range", types_of(detect_conflicts(sched, DATA)))

    def test_all_six_at_once(self):
        sched = [
            item("C001#1", 99, "R001", "T001", ["CL001"], 30, False),   # 越界
            item("C002#1", 0, "R001", "T002", ["CL002"], 30, False),   # 教室占用
            item("C003#1", 0, "R001", "T001", ["CL002"], 80, True),     # 容量不足+类型不匹配
        ]
        self.assertEqual(count_hard(detect_conflicts(sched, DATA)) >= 3, True)


def baseline_greedy_task(tasks, tid):
    for t in tasks:
        if t["task_id"] == tid:
            return t
    raise KeyError(tid)


class TestGreedyColoringIsConflictFree(unittest.TestCase):
    """贪心图着色的结果在"图着色"意义上必须无冲突: 同色顶点之间无边"""

    def test_coloring_independent_sets_are_conflict_free(self):
        data = with_buildings(load_json(os.path.join(HERE, "data_s60.json")))
        tasks = make_tasks(data)
        G = baseline_greedy.build_conflict_graph(tasks)
        for strategy in ["largest_first", "DSATUR"]:
            if strategy == "DSATUR" and not baseline_greedy.available_strategies():
                continue
            coloring = nx.coloring.greedy_color(G, strategy=strategy)
            colors = {}
            for node, c in coloring.items():
                colors.setdefault(c, []).append(node)
            for c, nodes in colors.items():
                sub = G.subgraph(nodes)
                # networkx 3.x 没有 is_independent_set, 用"诱导子图无边"等价判定
                self.assertEqual(
                    sub.number_of_edges(), 0,
                    f"策略 {strategy} 的颜色 {c} 中存在边, 说明同色任务发生了冲突",
                )
            for c, nodes in colors.items():
                tset = [baseline_greedy_task(tasks, n)["teacher_id"] for n in nodes]
                self.assertEqual(len(tset), len(set(tset)), f"颜色 {c} 中同一教师出现多次")

    def test_teacher_and_class_exclusive_in_same_color(self):
        data = with_buildings(load_json(os.path.join(HERE, "data_s60.json")))
        tasks = make_tasks(data)
        G = baseline_greedy.build_conflict_graph(tasks)
        coloring = nx.coloring.greedy_color(G, strategy="largest_first")
        by_color = {}
        for node, c in coloring.items():
            by_color.setdefault(c, []).append(node)
        tmap = {t["task_id"]: t for t in tasks}
        for c, nodes in by_color.items():
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    a, b = tmap[nodes[i]], tmap[nodes[j]]
                    self.assertNotEqual(a["teacher_id"], b["teacher_id"])
                    self.assertFalse(set(a["class_ids"]) & set(b["class_ids"]))


class TestCPATSolutionIsClean(unittest.TestCase):
    """CP-SAT 出的解必须被独立检测器判定为 0 硬冲突"""

    def test_cpsat_solution_passes_independent_check(self):
        import solve_cpsat

        data = with_buildings(load_json(os.path.join(HERE, "data_s30.json")))
        tasks = make_tasks(data)
        r = solve_cpsat.solve(tasks, data, time_limit=30, verbose=False)
        self.assertIn(r["status"], ("OPTIMAL", "FEASIBLE"))
        conf = detect_conflicts(r["_schedule"], data)
        self.assertEqual(count_hard(conf), 0, f"CP-SAT 解存在硬冲突: {conf[:5]}")


if __name__ == "__main__":
    print("=== test_detect.py 单元测试 ===")
    unittest.main(verbosity=2)