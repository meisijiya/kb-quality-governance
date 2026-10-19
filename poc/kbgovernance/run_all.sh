#!/usr/bin/env bash
# run_all.sh -- 一键跑通 全链路：生成数据 -> 向量化 -> 三模块检测 -> 出结果
#
# 用法 (Git Bash):
#   cd D:/26code/毕设/poc/kbgovernance
#   bash run_all.sh
#
# 注意：本机 `which bash` 会解析到 WSL(C:\Windows\System32\bash.exe)，
#       WSL 里没有 WindowsApps 的 python 垫片，必须显式调用 Git Bash：
#       "C:\Program Files\Git\bin\bash.exe" run_all.sh
#
# 环境变量:
#   HF_HOME   模型缓存目录（默认 D:/hf_cache，避免撑爆 C 盘）
#   PY        python 解释器（留空则自动探测）

set -euo pipefail

cd "$(dirname "$0")"

export HF_HOME="${HF_HOME:-D:/hf_cache}"
export PYTHONIOENCODING="utf-8"

# 自动探测 Python 解释器：Git Bash / WSL / cmd 下可用的命令名不一样
detect_py() {
  for c in "${PY:-}" python python3 python.exe py; do
    [ -n "$c" ] || continue
    if command -v "$c" >/dev/null 2>&1 && "$c" --version >/dev/null 2>&1; then
      echo "$c"; return 0
    fi
  done
  return 1
}
if ! PY="$(detect_py)"; then
  echo "错误：找不到可用的 Python 解释器。" >&2
  echo "请先安装 Python 3.10+ 并加入 PATH，或用 PY=/path/to/python bash run_all.sh" >&2
  exit 1
fi

mkdir -p "$HF_HOME"

echo "############################################################"
echo "# PoC 全链路运行  $(date '+%Y-%m-%d %H:%M:%S')"
echo "# python : $($PY --version 2>&1)"
echo "# HF_HOME: $HF_HOME"
echo "############################################################"

# ---------- 步骤 0: 环境自检 ----------
echo
echo ">>> [0/4] 环境自检"
$PY - <<'EOF'
import sys
missing = []
for mod in ("numpy", "pandas", "sklearn"):
    try:
        __import__(mod)
    except ImportError:
        missing.append(mod)
if missing:
    sys.exit(f"缺少基础包 {missing}，请先执行: pip install numpy pandas scikit-learn")
try:
    import FlagEmbedding  # noqa: F401
    print("  FlagEmbedding 可用")
except ImportError:
    print("  警告: FlagEmbedding 不可用，embed.py 将自动降级 "
          "(sentence-transformers -> TF-IDF)")
import sklearn
from sklearn.cluster import HDBSCAN
print(f"  sklearn {sklearn.__version__}, HDBSCAN 可用")
EOF

# ---------- 步骤 1: 生成合成数据 ----------
echo
echo ">>> [1/4] 生成合成数据 (gen_data.py)"
time $PY gen_data.py

# ---------- 步骤 2: 语义向量化 ----------
echo
echo ">>> [2/4] 语义向量化 (embed.py)"
time $PY embed.py

# ---------- 步骤 3: 三模块检测 ----------
echo
echo ">>> [3/4] 缺陷检测 (detect.py)"
time $PY detect.py

# ---------- 步骤 4: 产物核对 ----------
echo
echo ">>> [4/4] 产物核对"
for f in docs.csv tickets.csv ground_truth.json \
         doc_emb.npy ticket_emb.npy ticket_cover.npy embeddings_meta.json \
         gap_threshold.csv dup_threshold.csv corrupt_docs.csv \
         dup_groups_best.csv top15_gaps.csv metrics.json; do
  if [ -f "$f" ]; then
    printf '  [OK]   %-24s %s bytes\n' "$f" "$(wc -c < "$f" | tr -d ' ')"
  else
    printf '  [缺失] %-24s\n' "$f"
  fi
done

echo
echo "############################################################"
echo "# 完成  $(date '+%Y-%m-%d %H:%M:%S')"
echo "# 关键指标见 metrics.json；完整报告见 RESULT.md"
echo "############################################################"
