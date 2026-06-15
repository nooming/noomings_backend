# -*- coding: utf-8 -*-
"""pytest 路径：确保仓库根在 sys.path。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
