#!/usr/bin/env bash
# 排课优化 POC 一键复现脚本 (Git Bash)
#
# 用法 (注意: 必须用真正的 Git Bash, 不要用 which bash 解析到的 WSL):
#   "C:/Program Files/Git/bin/bash.exe" -lc 'bash run_all.sh'
#
# 全部脚本都对 CP-SAT 设了超时, 不会挂死。

set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python}

echo "=================================================="
echo " 0) 环境检查"
echo "=================================================="
$PY --version
$PY -c "import numpy, pandas, networkx, ortools; print('numpy', numpy.__version__); print('pandas', pandas.__version__); print('networkx', networkx.__version__); print('ortools OK')"

echo
echo "=================================================="
echo " 1) 生成合成排课数据 (seed=42)"
echo "=================================================="
$PY gen_data.py

echo
echo "=================================================="
echo " 2) 贪心图着色基线 (largest_first + DSATUR)"
echo "=================================================="
$PY baseline_greedy.py s60

echo
echo "=================================================="
echo " 3) CP-SAT 精确求解 + 约束放宽阶梯"
echo "=================================================="
$PY solve_cpsat.py s60

echo
echo "=================================================="
echo " 4) 规模压力测试 30/60/100/150 门课 -> stress_result.csv"
echo "=================================================="
$PY stress_test.py

echo
echo "=================================================="
echo " 5) 软约束权重实验 -> weight_result.csv"
echo "=================================================="
$PY soft_weight.py s60

echo
echo "=================================================="
echo " 6) 冲突检测与可视化数据导出"
echo "=================================================="
$PY visualize.py s60

echo
echo "=================================================="
echo " 7) 单元测试"
echo "=================================================="
$PY test_detect.py

echo
echo "=================================================="
echo " 全部完成。产物:"
ls -1 stress_result.csv weight_result.csv schedule.json conflicts.json matrix.csv
echo "=================================================="