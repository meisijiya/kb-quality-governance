# -*- coding: utf-8 -*-
"""granularity.py -- granularity_exp.py 的别名入口（实现全部在 granularity_exp.py）。

用法: python granularity.py  等价于  python granularity_exp.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from granularity_exp import main  # noqa: E402

if __name__ == "__main__":
    main()