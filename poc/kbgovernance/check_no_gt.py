#!/usr/bin/env python
"""校验「无真值也能跑」这条口径（准备清单 C5）。

检测模块要同时支持两种输入：

* 有真值（PoC 语料）——输出 P/R/F1，阈值按真值择优；
* 无真值（自有语料）——阈值走固定参数，只报检出数，**真值侧指标一律留空**。

无真值时如果照常套公式，等于把「所有检出的文档」当成误报，报出一组凭空
捏造的 P/R/F1。这条校验就是钉住这个行为：无真值时凡是真值侧字段，都必须
是 null（含义是「不可得」），而不是 0（含义是「可得且为零」）。

用法：
    python check_no_gt.py          # 跑检测到临时目录并校验，退出码 0 = 通过
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DETECT = os.path.join(HERE, "detect.py")

# 跑检测所需的输入（无 ground_truth.json —— 这正是本用例的前提）
INPUTS = (
    "docs.csv",
    "tickets.csv",
    "doc_emb.npy",
    "ticket_emb.npy",
    "ticket_cover.npy",
    "embeddings_meta.json",
)

# 真值侧字段：这些只有在有真值时才可得
TRUTH_FIELDS = (
    ("corrupt", "embedded"),
    ("corrupt", "covered"),
    ("corrupt", "fn"),
    ("corrupt", "fp"),
    ("dup", "embedded_groups"),
    ("dup", "embedded_docs"),
)

# 真值侧的 P/R/F1 出现位置：(节路径, 键)
TRUTH_METRIC_PATHS = (
    ("gap", "best", "precision"),
    ("gap", "best", "recall"),
    ("gap", "best", "f1"),
    ("dup", "best", "group_precision"),
    ("dup", "best", "group_recall"),
    ("dup", "best", "group_f1"),
    ("dup", "best", "doc_precision"),
    ("dup", "best", "doc_recall"),
    ("dup", "best", "doc_f1"),
)

CAUSES = ("content_expiry", "maintenance")

FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  [不通过] " + msg)


def ok(msg):
    print("  [通过] " + msg)


def dig(obj, path):
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return "__missing__"
        cur = cur[key]
    return cur


def main():
    tmp = tempfile.mkdtemp(prefix="nogt-")
    try:
        for name in INPUTS:
            src = os.path.join(HERE, name)
            if not os.path.exists(src):
                fail("缺少输入文件 " + name)
                return 1
            shutil.copy2(src, os.path.join(tmp, name))

        proc = subprocess.run(
            [sys.executable, DETECT, "--no-gt", "--out-dir", tmp],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            fail("detect.py --no-gt 退出码 %d\n%s"
                 % (proc.returncode, (proc.stderr or "")[-800:]))
            return 1
        ok("detect.py --no-gt 退出码 0，流程未报错")

        mpath = os.path.join(tmp, "metrics.json")
        if not os.path.exists(mpath):
            fail("未产出 metrics.json")
            return 1
        with open(mpath, encoding="utf-8") as f:
            m = json.load(f)

        if m.get("has_ground_truth") is not False:
            fail("has_ground_truth 应为 false，实际 %r" % m.get("has_ground_truth"))
        else:
            ok("has_ground_truth = false")

        # 1) 真值侧计数必须是 null，而不是 0
        for sec, key in TRUTH_FIELDS:
            val = dig(m, (sec, key))
            if val is not None:
                fail("%s.%s 应为 null（不可得），实际 %r" % (sec, key, val))
        if not FAILS:
            ok("真值侧计数（embedded / covered / fn / fp / embedded_groups / "
               "embedded_docs）全部为 null")

        # 2) P/R/F1 必须是 null
        for path in TRUTH_METRIC_PATHS:
            val = dig(m, path)
            if val is not None:
                fail("%s 应为 null（不可得），实际 %r" % (".".join(path), val))
        ok("缺口与重复的 P/R/F1 全部为 null")

        # 3) 腐化两个口径：检出数要有值，真值侧要为空
        for name in CAUSES:
            cause = dig(m, ("corrupt", "by_cause", name))
            if cause == "__missing__":
                fail("corrupt.by_cause 缺 %s" % name)
                continue
            if not cause.get("detected"):
                fail("%s 的检出数应为正数，实际 %r" % (name, cause.get("detected")))
            for key in ("planted_of_this_nature", "tp", "fp", "fn"):
                if cause.get(key) is not None:
                    fail("corrupt.by_cause.%s.%s 应为 null，实际 %r"
                         % (name, key, cause.get(key)))
            for key in ("precision", "recall", "f1"):
                if cause.get(key) is not None:
                    fail("corrupt.by_cause.%s.%s 应为 null，实际 %r"
                         % (name, key, cause.get(key)))
        ok("腐化两个口径：检出数有值、真值侧与 P/R/F1 为 null")

        # 4) 无真值时仍要产出三张清单
        for name in ("gap_intents_best.csv", "corrupt_docs.csv",
                     "dup_groups_best.csv"):
            path = os.path.join(tmp, name)
            if not os.path.exists(path):
                fail("未产出 " + name)
            elif os.path.getsize(path) == 0:
                fail(name + " 是空文件")
        ok("缺口 / 腐化 / 重复三张清单均已产出")

        # 5) 逐篇真值列不能写成 0（0 会被读成「不是对照文档」）
        import csv
        with open(os.path.join(tmp, "corrupt_docs.csv"), encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if rows:
            bad = [r["doc_id"] for r in rows if r.get("in_control_sample", "") != ""]
            if bad:
                fail("corrupt_docs.csv 的 in_control_sample 在无真值时写了值：%s"
                     % ", ".join(bad[:5]))
            else:
                ok("corrupt_docs.csv 的 in_control_sample 留空（未写成 0）")
        else:
            fail("corrupt_docs.csv 没有数据行")

        if FAILS:
            print("\n[check_no_gt] 不通过：%d 条" % len(FAILS))
            return 1
        print("\n[check_no_gt] 通过：无真值时流程跑通、清单照产、真值侧指标一律留空")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
