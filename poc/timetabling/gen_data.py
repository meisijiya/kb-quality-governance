# -*- coding: utf-8 -*-
"""
合成排课数据生成器 —— 毕业设计 POC
模拟一所计算机学院一个学期的排课问题。

规模: 60 门课程 / 24 个班级 / 20 位教师 / 15 间教室 / 每周 5 天 x 6 节 = 30 时段

设计要点:
  - 容量约束是真实约束: 刻意生成一部分 "选课人数落在教室容量档之间" 的课程,
    使解空间存在取舍。
  - 先修课关系只允许从小编号课程指向大编号课程 -> 天然无环 DAG。
  - random.seed(42) 固定, 完全可复现。
"""
import random
import json
import os

SEED = 42

# ---------------- 时段定义 ----------------
DAYS = ["周一", "周二", "周三", "周四", "周五"]
PERIODS_PER_DAY = 6
N_PERIODS = len(DAYS) * PERIODS_PER_DAY


def slot_name(idx):
    return f"{DAYS[idx // PERIODS_PER_DAY]}-第{idx % PERIODS_PER_DAY + 1}节"


def build_courses(n_courses, rng):
    """生成课程, 先修关系只允许从小编号指向大编号 -> 天然 DAG"""
    courses = []
    for i in range(n_courses):
        cid = f"C{i + 1:03d}"
        credits = rng.choice([1, 2, 2, 3, 3, 4])
        weekly_hours = rng.choice([1, 2, 2, 3, 3, 3])
        # 选课人数: 刻意让取值**落在教室容量档之间**, 而不是正好等于档位。
        # 若人数只能取 30/60/80 而教室只有 30/60/100 三档, 每个任务的最小容量
        # 浪费就是常数, 软约束 w2 完全无法优化 (实测四组权重结果一模一样)。
        required_capacity = rng.choice(
            [26, 33, 42, 48, 57, 63, 72, 78, 88, 95]
        )
        needs_lab = rng.random() < 0.35
        # 先修课: 只从编号更小的课程中选, 保证 DAG 无环
        prerequisites = []
        if i >= 6 and rng.random() < 0.45:
            k = rng.randint(1, 2)
            cand = rng.sample(range(i - 6, i), k=min(k, i))
            prerequisites = [f"C{j + 1:03d}" for j in cand]
        courses.append(
            {
                "course_id": cid,
                "name": f"课程{cid}",
                "credits": credits,
                "weekly_hours": weekly_hours,
                "required_capacity": required_capacity,
                "needs_lab": needs_lab,
                "prerequisites": prerequisites,
            }
        )
    return courses


def build_teachers(n_teachers, rng, n_periods):
    teachers = []
    for i in range(n_teachers):
        tid = f"T{i + 1:03d}"
        # 每位教师 4~9 个不可用时段 (备课/例会/答疑/科研), 贴近真实。
        # 2~5 个太宽松时教师一天最多 6 节且分布在 30 个时段里, 几乎不可能连排,
        # 软约束 w1 恒为 0, 权重实验失去区分度 (实测踩过)。
        n_unavail = rng.randint(4, 9)
        unavailable = sorted(rng.sample(range(n_periods), n_unavail))
        teachers.append(
            {
                "teacher_id": tid,
                "name": f"教师{i + 1}",
                "unavailable_slots": unavailable,
                "max_consecutive": 2,
            }
        )
    return teachers


def build_rooms(n_rooms, rng, courses=None):
    """容量分档 35/50/65/80/100/130; 类型 normal/multimedia/lab

    关键设计修正 (三处, 都是实测踩出来的):
      1. lab 必须有最大档, 否则 needs_lab 且人数最大的课程没有任何可行教室
         -> AddExactlyOne([]) -> CP-SAT 秒判 INFEASIBLE。
      2. 教室供给必须按课程需求**成比例配置**。若只按固定比例随机生成,
         在 150 门课规模会出现: 高人数 lab 课程有 32 个, 而 >=65 人的 lab 只有
         1 间 -> 30 时段 x 1 间 = 30 位子 < 32 任务, 必然无解。
         这属于"场地供给不足"而非"求解器算不动", 会掩盖真正的规模时间红线。
      3. 容量档必须**细分**。若只有 30/60/100 三档而人数也恰好取 30/60/80,
         每个任务的最小容量浪费成为常数, 软约束 w2 无从优化 (实测四组权重
         结果完全相同)。因此人数取"档位之间"的值, 容量档取 6 档。
    """
    CAP_TIERS = [35, 50, 65, 80, 100, 130]

    # ---- 统计各容量档的需求量 ----
    def demand_for(courses_, lab_only):
        d = {t: 0 for t in CAP_TIERS}
        if not courses_:
            return d
        for c in courses_:
            if lab_only and not c["needs_lab"]:
                continue
            for t in CAP_TIERS:
                if c["required_capacity"] <= t:
                    d[t] += c["weekly_hours"]  # 按"课程-节次"任务数计
                    break
        return d

    HEADROOM = 22
    rooms = []

    def add(cap, rtype):
        rid = f"R{len(rooms) + 1:03d}"
        rooms.append({"room_id": rid, "capacity": cap, "type": rtype})

    if courses:
        d_all = demand_for(courses, lab_only=False)
        d_lab = demand_for(courses, lab_only=True)
        # 每个容量档至少配 1 间, 且需求量越大配得越多
        for cap in CAP_TIERS:
            n = max(1, -(-d_all[cap] // HEADROOM))  # ceil
            for _ in range(n):
                add(cap, "normal" if rng.random() < 0.5 else "multimedia")
            nl = -(-d_lab[cap] // HEADROOM) if d_lab[cap] else 0
            for _ in range(nl):
                add(cap, "lab")
    else:
        for _ in range(n_rooms):
            rtype = rng.choice(["normal", "normal", "multimedia", "lab"])
            if rtype == "lab":
                add(rng.choice(CAP_TIERS), rtype)
            elif rtype == "multimedia":
                add(rng.choice(CAP_TIERS[2:]), rtype)
            else:
                add(rng.choice(CAP_TIERS), rtype)

    # 规格下限: 题目规定的教室数 (如 s60 = 15 间) 作为下限, 供给不足时才扩配
    while len(rooms) < n_rooms:
        add(rng.choice(CAP_TIERS), rng.choice(["normal", "multimedia"]))

    # 保证至少一间 lab, 且 lab 里至少有一间最大档大实验室
    top = CAP_TIERS[-1]
    if not any(r["type"] == "lab" for r in rooms):
        rooms[0]["type"] = "lab"
        rooms[0]["capacity"] = CAP_TIERS[2]
    if not any(r["type"] == "lab" and r["capacity"] >= CAP_TIERS[-2] for r in rooms):
        for r in rooms:
            if r["type"] == "lab":
                r["capacity"] = top
                break
        else:
            rooms[0]["type"] = "lab"
            rooms[0]["capacity"] = top
    if not any(r["capacity"] >= CAP_TIERS[-2] for r in rooms):
        rooms[-1]["capacity"] = top
    return rooms


def build_assignments(courses, teachers, rooms, n_classes, rng):
    """给每门课分配: 任课教师 + 授课班级"""
    assignments = []
    for course in courses:
        a = {
            "course_id": course["course_id"],
            "teacher_id": rng.choice(teachers)["teacher_id"],
            "class_ids": [],
        }
        # 1~3 个班级合上这门课 (多班合堂 -> 更紧的资源约束)
        k = rng.choice([1, 1, 1, 2, 2, 3])
        a["class_ids"] = rng.sample(
            [f"CL{i + 1:03d}" for i in range(n_classes)], k=min(k, n_classes)
        )
        assignments.append(a)
    return assignments


def generate(n_courses=60, n_teachers=20, n_rooms=15, n_classes=24, seed=SEED):
    rng = random.Random(seed)
    courses = build_courses(n_courses, rng)
    teachers = build_teachers(n_teachers, rng, N_PERIODS)
    rooms = build_rooms(n_rooms, rng, courses=courses)
    assignments = build_assignments(courses, teachers, rooms, n_classes, rng)
    return {
        "courses": courses,
        "teachers": teachers,
        "rooms": rooms,
        "assignments": assignments,
        "n_classes": n_classes,
        "n_periods": N_PERIODS,
        "days": DAYS,
        "periods_per_day": PERIODS_PER_DAY,
        "buildings": ["教A楼", "教B楼", "教C楼"],
    }


def room_building(room_id, rooms):
    """伪造成 3 栋教学楼: 按房间序号轮转分配, 给软约束 w3 用"""
    idx = int(room_id[1:]) - 1
    return rooms["buildings"][idx % len(rooms["buildings"])]


# 额外挂一个 building 字段便于下游使用
def with_buildings(data):
    idx_map = {r["room_id"]: i for i, r in enumerate(data["rooms"])}
    for rid, i in idx_map.items():
        data["rooms"][i]["building"] = data["buildings"][i % len(data["buildings"])]
    return data


def make_tasks(data):
    """把课程展开为 "课程-节次" 任务单元, vertex id = (course_id, k)"""
    tasks = []
    cidx = {c["course_id"]: c for c in data["courses"]}
    for a in data["assignments"]:
        cid = a["course_id"]
        c = cidx[cid]
        for k in range(c["weekly_hours"]):
            tasks.append(
                {
                    "task_id": f"{cid}#{k + 1}",
                    "course_id": cid,
                    "session": k + 1,
                    "teacher_id": a["teacher_id"],
                    "class_ids": a["class_ids"],
                    "required_capacity": c["required_capacity"],
                    "needs_lab": c["needs_lab"],
                }
            )
    return tasks


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for scale, (nc, nt, nr, ncl) in {
        "s30": (30, 11, 9, 14),
        "s60": (60, 20, 15, 24),
        "s100": (100, 33, 24, 38),
        "s150": (150, 48, 34, 54),
    }.items():
        d = with_buildings(generate(nc, nt, nr, ncl))
        save_json(d, os.path.join(here, f"data_{scale}.json"))
        t = make_tasks(d)
        print(f"[gen] {scale}: courses={len(d['courses'])} teachers={len(d['teachers'])} "
              f"rooms={len(d['rooms'])} classes={d['n_classes']} tasks={len(t)}")
        tight = sum(1 for c in d["courses"] if c["required_capacity"] > 35)
        print(f"       人数>35(必须用中/大教室)的课程数 = {tight}")
    print(f"[gen] 时间槽 = {N_PERIODS} (5天 x 6节)  seed={SEED}")