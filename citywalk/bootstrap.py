# -*- coding: utf-8 -*-
"""Citywalk 启动配置（须在 import 规划模块前调用）。"""
import logging
import os

from citywalk.core.geo.amap_client import get_amap_key
from citywalk.core.planning import runtime as planning_runtime


def configure_amap_keys():
    """从环境变量注入 planning.runtime。"""
    planning_runtime.AMAP_KEY = os.environ.get("AMAP_KEY", "").strip() or get_amap_key() or ""
    planning_runtime.AMAP_STATIC_MAP_KEY = (
        os.environ.get("AMAP_STATIC_MAP_KEY", "").strip() or planning_runtime.AMAP_KEY
    )
    if not planning_runtime.AMAP_KEY:
        logging.warning("未配置 AMAP_KEY，路线规划接口将不可用")
    return planning_runtime.AMAP_KEY, planning_runtime.AMAP_STATIC_MAP_KEY
