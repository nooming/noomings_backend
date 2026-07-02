"""内容种草·景点增强（①）：为打卡点生成一句有调性的中文描述（LLM）。

图片走高德官方 photos（在 app 启动流程侧抓取，需 AMAP_KEY）；
本模块只负责合规、可缓存的文案生成。结果带进程内缓存（POI 基本不变）。
"""

import logging
import threading
from typing import Optional

from citywalk.core.agent.llm_client import chat_text, is_configured

logger = logging.getLogger(__name__)

_DESC_SYSTEM = """你是 Citywalk 文案助手。给定一个真实地点的名称、类型与所在城市/片区，
写**一句**（≤30字）有调性、具体、不浮夸的中文介绍，让人想去逛。
要求：不编造未提供的事实（如营业时间、价格）；不堆 emoji；只输出这句话本身。"""

# 简单进程内缓存（key -> 描述）；POI 描述基本不变，缓存可长期复用
_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 2000


def describe_poi(name: str, category: str = "", city: str = "", area: str = "") -> str:
    """为单个 POI 生成一句描述；失败或未配置时返回空串（前端降级）。"""
    name = (name or "").strip()
    if not name:
        return ""
    key = f"{name}|{category}|{city}|{area}"
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    if not is_configured():
        return ""

    user = (
        f"地点名：{name}\n类型：{category or '未知'}\n"
        f"城市：{city or '未知'}\n片区：{area or '不限'}"
    )
    try:
        text = chat_text(_DESC_SYSTEM, user, temperature=0.7)
    except Exception as e:
        logger.warning("景点描述生成失败: %s", e)
        return ""

    text = (text or "").strip().strip('"“”').replace("\n", " ")
    if len(text) > 60:
        text = text[:60]

    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[key] = text
    return text


def cached_description(name: str, category: str = "", city: str = "", area: str = "") -> Optional[str]:
    """只读缓存（不触发 LLM），供需要快速返回的场景。"""
    key = f"{name}|{category}|{city}|{area}"
    with _cache_lock:
        return _cache.get(key)
