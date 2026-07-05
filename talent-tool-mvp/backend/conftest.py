"""Pytest 配置 - 添加 backend 到 Python 路径."""
import sys
import os

# 把 backend 目录加入 sys.path,使得 `import agents` 等顶级导入可以工作
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)