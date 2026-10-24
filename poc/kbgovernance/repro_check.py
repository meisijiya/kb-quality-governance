# -*- coding: utf-8 -*-
"""
repro_check.py -- 语料与产物的可复现性证据生成器 / 比对器。

用途:
  1) snapshot  （默认） 扫描本目录产物，算出 md5 清单并写入 repro_check.json
  2) compare  A B        比对两份清单，输出逐产物一致/不一致，退出码 0=全一致 1=有差异
  3) verify             自证模式：连跑两次全链路（gen_data→embed→detect），
                         比对两次快照，把结论写进 repro_check.json

三类口径:
  byte_deterministic  字节确定产物，不含任何计时字段，跨运行逐字节可复现
  normalized          含耗时字段的产物，剔除计时字段后比对
  binary              .npy 向量产物，同机同环境浮点稳定，跨机器不保证

为什么要 normalized 这一类:
  metrics.json / embeddings_meta.json / dup_threshold.csv 里带 encode_seconds /
  total_seconds / seconds 等计时字段，跨机器、跨次运行必然波动，直接比 md5 一定不等。
  AGENTS.md 明确"耗时字段跨机器必然波动，指标值不受影响"——所以正确口径是
  "剔除计时字段后 md5 一致"，而不是笼统宣称"全部产物 md5 完全一致"。

用法:
  python repro_check.py                      # 写 repro_check.json
  python repro_check.py verify               # 连跑两次全链路并自证
  python repro_check.py compare run1.json run2.json
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "repro_check.json")

# 字节确定产物：不含任何计时字段，跨运行逐字节可复现
BYTE_DETERMINISTIC = [
    "docs.csv",
    "tickets.csv",
    "ground_truth.json",
    "gap_threshold.csv",
    "corrupt_rule_ablation.csv",
    "corrupt_docs.csv",
    "dup_groups_best.csv",
    "top15_gaps.csv",
    "granularity.csv",
    "granularity_dup.csv",
    "derived_metrics.csv",
    "standardize/results_auc.csv",
    "standardize/results_transfer.csv",
    "standardize/results_directionC.csv",
    "standardize/results_directions.csv",
    "standardize/results_banking77_zh.csv",
    "standardize/results_banking77_en.csv",
    "standardize/results_xfer_banking77_zh.csv",
    "standardize/results_xfer_banking77_en.csv",
    "standardize/ablation.csv",
    "standardize/mechanism.csv",
    "standardize/banking77_meta.json",
    "standardize/banking77_meta_zh.json",
    "standardize/banking77_meta_en.json",
    "standardize/scenario_meta.json",
]

# 含计时字段的产物：比对前剔除计时字段
NORMALIZED = {
    "metrics.json": ["seconds", "total_seconds", "encode_seconds"],
    "embeddings_meta.json": ["encode_seconds"],
    "dup_threshold.csv": ["seconds"],
}

# 二进制向量产物
BINARY = ["doc_emb.npy", "ticket_emb.npy", "ticket_cover.npy"]

# run_all.sh 三步（gen_data → embed → detect）实际产出的文件。
# verify 模式只比对这批，因为另跑的消融/标准化脚本不在全链路里。
PIPELINE_OUTPUTS = [
    "docs.csv",
    "tickets.csv",
    "ground_truth.json",
    "gap_threshold.csv",
    "corrupt_docs.csv",
    "dup_groups_best.csv",
    "top15_gaps.csv",
    "metrics.json",
    "embeddings_meta.json",
    "dup_threshold.csv",
    "doc_emb.npy",
    "ticket_emb.npy",
    "ticket_cover.npy",
]


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_timing_json(obj, drop_keys):
    """递归剔除计时字段"""
    if isinstance(obj, dict):
        return {k: strip_timing_json(v, drop_keys) for k, v in obj.items()
                if k not in drop_keys}
    if isinstance(obj, list):
        return [strip_timing_json(v, drop_keys) for v in obj]
    return obj


def strip_timing_csv(path, drop_cols):
    """剔除指定列后重算 md5"""
    import csv
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return md5_of(path)
    keep = [i for i, name in enumerate(rows[0]) if name not in drop_cols]
    buf = [",".join(r[i] for i in keep) for r in rows]
    return hashlib.md5("\n".join(buf).encode("utf-8")).hexdigest()


def scan():
    """扫描当前产物，返回清单 dict（不含时间戳，可直接比对）"""
    manifest = {"byte_deterministic": {}, "normalized": {}, "binary": {}, "missing": []}

    for name in BYTE_DETERMINISTIC:
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            manifest["missing"].append(name)
            continue
        manifest["byte_deterministic"][name] = md5_of(p)

    for name, drop in NORMALIZED.items():
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            manifest["missing"].append(name)
            continue
        if name.endswith(".json"):
            with open(p, encoding="utf-8") as f:
                obj = json.load(f)
            norm = strip_timing_json(obj, set(drop))
            digest = hashlib.md5(
                json.dumps(norm, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
        else:
            digest = strip_timing_csv(p, set(drop))
        manifest["normalized"][name] = {
            "normalized_md5": digest,
            "stripped_fields": sorted(drop),
            "raw_md5": md5_of(p),
        }

    for name in BINARY:
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            manifest["missing"].append(name)
            continue
        manifest["binary"][name] = md5_of(p)

    return manifest


def diff(ma, mb):
    """比对两份清单，返回 (是否全一致, 明细列表)"""
    rows = []
    ok = True
    for section, key in (("byte_deterministic", None), ("binary", None)):
        a, b = ma.get(section, {}), mb.get(section, {})
        for name in sorted(set(a) | set(b)):
            same = name in a and name in b and a[name] == b[name]
            ok = ok and same
            rows.append({
                "artifact": name,
                "mode": section,
                "run_a": a.get(name),
                "run_b": b.get(name),
                "identical": same,
            })
    a, b = ma.get("normalized", {}), mb.get("normalized", {})
    for name in sorted(set(a) | set(b)):
        ha = a.get(name, {}).get("normalized_md5")
        hb = b.get(name, {}).get("normalized_md5")
        same = ha is not None and ha == hb
        ok = ok and same
        rows.append({
            "artifact": name,
            "mode": "normalized",
            "run_a": ha,
            "run_b": hb,
            "identical": same,
            "stripped_fields": a.get(name, {}).get("stripped_fields", []),
        })
    return ok, rows


def print_rows(rows, a_label="A", b_label="B"):
    print("=" * 78)
    print(f"{'产物':<46} {'口径':<18} 结果")
    print("-" * 78)
    for r in rows:
        flag = "一致" if r["identical"] else "不一致"
        print(f"{r['artifact']:<46} {r['mode']:<18} {flag}")
        if not r["identical"]:
            print(f"    {a_label}: {r['run_a']}")
            print(f"    {b_label}: {r['run_b']}")
    print("=" * 78)


def validate_verify_block(block, manifest):
    """校验已有的 two_run_verify 证据块是否仍与当前工作树一致。

    verify 模式在临时目录连跑两次全链路，run_a 对应那两次运行的产物。
    之后 run_all.sh 的 snapshot 模式会重写本文件，若不校验，证据块会与当前
    产物脱节——文档引用 `two_run_verify` 作为可复现性依据，必须显式标注它
    是否仍然对应当前工作树。
    """
    if not block:
        return None, []
    stale = []
    for r in block.get("rows", []):
        name, mode = r["artifact"], r["mode"]
        if mode == "normalized":
            cur = manifest["normalized"].get(name, {}).get("normalized_md5")
        else:
            cur = manifest.get(mode, {}).get(name)
        if cur is None or cur != r.get("run_a"):
            stale.append(name)
    return (not stale), stale


def run_pipeline(tag):
    """在临时副本里连跑全链路，避免污染仓库产物。

    临时目录名带进程号：两次 verify 若同时跑，目录名不同才不会互相删掉
    对方的脚本副本（同名时后启动的一次 rmtree 会把前一次正在用的目录删掉）。
    """
    tmp = os.path.join(HERE, f".repro_{tag}_{os.getpid()}")
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    for f in ("gen_data.py", "embed.py", "detect.py"):
        shutil.copy2(os.path.join(HERE, f), tmp)
    env = dict(os.environ)
    env.setdefault("HF_HOME", "D:/hf_cache")
    env["PYTHONIOENCODING"] = "utf-8"
    for step in ("gen_data.py", "embed.py", "detect.py"):
        r = subprocess.run([sys.executable, step], cwd=tmp, env=env,
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            print(r.stdout[-2000:])
            print(r.stderr[-2000:], file=sys.stderr)
            raise SystemExit(f"[repro_check] {step} 失败，退出码 {r.returncode}")
    return tmp


def main():
    ap = argparse.ArgumentParser(description="可复现性证据生成 / 比对")
    ap.add_argument("mode", nargs="?", default="snapshot",
                    choices=["snapshot", "compare", "verify"])
    ap.add_argument("paths", nargs="*", help="compare 模式：两份清单路径")
    ap.add_argument("--out", default=OUT, help="snapshot 输出路径")
    args = ap.parse_args()

    if args.mode == "compare":
        if len(args.paths) != 2:
            raise SystemExit("compare 模式需要两份清单路径")
        with open(args.paths[0], encoding="utf-8") as f:
            ma = json.load(f)
        with open(args.paths[1], encoding="utf-8") as f:
            mb = json.load(f)
        ok, rows = diff(ma, mb)
        print_rows(rows, args.paths[0], args.paths[1])
        print(f"[repro_check] 结论：{'全部一致' if ok else '存在不一致'}")
        return 0 if ok else 1

    if args.mode == "verify":
        print("[repro_check] 第一次全链路运行 ...")
        tmp_a = run_pipeline("a")
        print("[repro_check] 第二次全链路运行 ...")
        tmp_b = run_pipeline("b")
        ma = scan_in(tmp_a, PIPELINE_OUTPUTS)
        mb = scan_in(tmp_b, PIPELINE_OUTPUTS)
        ok, rows = diff(ma, mb)
        print_rows(rows, "run1", "run2")
        worktree = scan()
        still_valid, stale = validate_verify_block(
            {"rows": rows}, worktree)
        result = {
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "note": (
                "byte_deterministic 为逐字节可复现产物；normalized 为剔除计时字段后比对"
                "（计时字段跨运行必然波动，指标值不受影响）；binary 为同机浮点向量产物，"
                "跨机器不保证一致。verify 为连跑两次全链路的自证结果。"
            ),
            "two_run_verify": {
                "identical": ok,
                "scope": "run_all.sh 三步（gen_data.py → embed.py → detect.py）产出的 %d 个文件" % len(PIPELINE_OUTPUTS),
                "n_artifacts_compared": len(rows),
                "n_identical": sum(1 for r in rows if r["identical"]),
                "differing": [r["artifact"] for r in rows if not r["identical"]],
                "still_matches_worktree": still_valid,
                "rows": rows,
            },
            **worktree,
        }
        if stale:
            result["two_run_verify"]["stale_artifacts"] = stale
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        for t in (tmp_a, tmp_b):
            shutil.rmtree(t, ignore_errors=True)
        print(f"[repro_check] 结论：{'两次运行全部一致' if ok else '存在不一致'}")
        print(f"[repro_check] 已写出 {args.out}")
        return 0 if ok else 1

    manifest = scan()
    result = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "note": (
            "byte_deterministic 为逐字节可复现产物；normalized 为剔除计时字段后比对"
            "（计时字段跨运行必然波动，指标值不受影响）；binary 为同机浮点向量产物，"
            "跨机器不保证一致。"
        ),
        **manifest,
    }
    # snapshot 模式会重写本文件，需保留此前 verify 模式留下的两次运行证据块，
    # 否则 run_all.sh 每跑一次就把可复现性证据抹掉，文档引用随之失效。
    if os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as f:
                prev = json.load(f)
        except (ValueError, OSError):
            prev = {}
        block = prev.get("two_run_verify")
        still_valid, stale = validate_verify_block(block, manifest)
        if block:
            block["still_matches_worktree"] = still_valid
            if stale:
                block["stale_artifacts"] = stale
            result["two_run_verify"] = block
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print(f"[repro_check] 可复现性清单已写出: {os.path.relpath(args.out, HERE)}")
    print(f"[repro_check] 字节确定产物 {len(manifest['byte_deterministic'])} 个")
    for k, v in manifest["byte_deterministic"].items():
        print(f"    {v}  {k}")
    print(f"[repro_check] 计时归一化产物 {len(manifest['normalized'])} 个")
    for k, v in manifest["normalized"].items():
        print(f"    {v['normalized_md5']}  {k}  (剔除: {','.join(v['stripped_fields'])})")
    print(f"[repro_check] 二进制向量 {len(manifest['binary'])} 个")
    for k, v in manifest["binary"].items():
        print(f"    {v}  {k}")
    if manifest["missing"]:
        print(f"[repro_check] 缺失 {len(manifest['missing'])} 个: {manifest['missing']}")
    print("=" * 70)
    return 0


def scan_in(directory, only=None):
    """扫描指定目录的产物（用于 verify 模式的临时副本）。
    only 给定时只比对这批文件，其余不计入 missing。"""
    saved = HERE
    saved_lists = (BYTE_DETERMINISTIC, NORMALIZED, BINARY)
    try:
        globals()["HERE"] = directory
        if only is not None:
            only_set = set(only)
            globals()["BYTE_DETERMINISTIC"] = [n for n in BYTE_DETERMINISTIC if n in only_set]
            globals()["NORMALIZED"] = {k: v for k, v in NORMALIZED.items() if k in only_set}
            globals()["BINARY"] = [n for n in BINARY if n in only_set]
        return scan()
    finally:
        globals()["HERE"] = saved
        globals()["BYTE_DETERMINISTIC"], globals()["NORMALIZED"], globals()["BINARY"] = saved_lists


if __name__ == "__main__":
    sys.exit(main())
