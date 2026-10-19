# -*- coding: utf-8 -*-
"""
规模压力测试 —— 决定性证据

四个规模梯度 30 / 60 / 100 / 150 门课, 每个规模跑:
  - 贪心图着色 (largest_first + DSATUR)
  - CP-SAT (30 秒超时)
输出 stress_result.csv:
  scale, algorithm, time_sec, status, hard_violations, periods_used
回答: CP-SAT 在什么规模以下能稳定出解, 超过什么规模开始超时。
"""
import os
import csv

import baseline_greedy
from gen_data import load_json, with_buildings, make_tasks
import solve_cpsat

HERE = os.path.dirname(os.path.abspath(__file__))
SCALES = ["s30", "s60", "s100", "s150"]
TIME_LIMIT = 30

FIELDS = [
    "scale",
    "n_courses",
    "n_tasks",
    "algorithm",
    "time_sec",
    "status",
    "hard_violations",
    "periods_used",
    "n_vars",
    "n_constraints",
    "violation_breakdown",
]


def main():
    rows = []
    print(f"{'规模':<8}{'算法':<24}{'任务数':>7}{'耗时s':>9}  {'状态':<12}{'硬冲突':>8}{'时段数':>8}")
    print("-" * 90)

    for scale in SCALES:
        data = with_buildings(load_json(os.path.join(HERE, f"data_{scale}.json")))
        tasks = make_tasks(data)
        n_courses = len(data["courses"])

        # ---- 贪心 ----
        for r in baseline_greedy.run(scale, verbose=False):
            rows.append(
                {
                    "scale": scale,
                    "n_courses": n_courses,
                    "n_tasks": r["n_tasks"],
                    "algorithm": r["algorithm"],
                    "time_sec": r["time_sec"],
                    "status": r["status"],
                    "hard_violations": r["hard_violations"],
                    "periods_used": r["periods_used"],
                    "n_vars": "",
                    "n_constraints": "",
                    "violation_breakdown": str(r["violation_breakdown"]),
                }
            )
            print(
                f"{scale:<8}{r['algorithm']:<24}{r['n_tasks']:>7}{r['time_sec']:>9.4f}  "
                f"{r['status']:<12}{r['hard_violations']:>8}{r['periods_used']:>8}"
            )

        # ---- CP-SAT ----
        r = solve_cpsat.solve(
            tasks, data, time_limit=TIME_LIMIT, verbose=False, label="cpsat"
        )
        rows.append(
            {
                "scale": scale,
                "n_courses": n_courses,
                "n_tasks": r["n_tasks"],
                "algorithm": "cpsat",
                "time_sec": r["time_sec"],
                "status": r["status"],
                "hard_violations": r["hard_violations"] if r["hard_violations"] is not None else "",
                "periods_used": r["periods_used"] if r["periods_used"] is not None else "",
                "n_vars": r["n_vars"],
                "n_constraints": r["n_constraints"],
                "violation_breakdown": str(r.get("violation_breakdown", {})),
            }
        )
        print(
            f"{scale:<8}{'cpsat':<24}{r['n_tasks']:>7}{r['time_sec']:>9.3f}  "
            f"{r['status']:<12}{str(r['hard_violations']):>8}{str(r['periods_used']):>8}"
        )
        print(
            f"{'':<8}{'  -> 模型规模':<24}{'变量':>7}{r['n_vars']:>9}  "
            f"{'约束':>8}{r['n_constraints']:>8}"
        )

    out = os.path.join(HERE, "stress_result.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n[stress] 已写入 {out} ({len(rows)} 行)")
    return rows


if __name__ == "__main__":
    main()