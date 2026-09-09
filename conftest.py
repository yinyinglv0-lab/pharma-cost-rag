# -*- coding: utf-8 -*-
"""pytest 根配置：把项目根加入 sys.path，保证 app 包可导入。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
