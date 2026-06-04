"""联网搜索 Provider（可插拔）。

给灵感选点提供「真实联网搜索结果」做 grounding：先搜，再让 LLM 仅从
真实结果里提取地点名，显著降低编造、提升新店/小众点覆盖。

默认 Provider 用 Tavily（AI 原生搜索 API，返回已清洗正文）。未配 key 时
`web_search` 返回空列表，调用方据此回退到纯 LLM 选点（见 inspiration.py）。

env：
  CW_SEARCH_PROVIDER  默认 tavily
  TAVILY_API_KEY      留空 → 不联网，静默降级
"""

import logging
import os
from typing import Dict, List

import requests

logger = logging.getLogger(__name__)


def _provider() -> str:
    return os.environ.get("CW_SEARCH_PROVIDER", "tavily").strip().lower()


def is_search_configured() -> bool:
    """当前所选 Provider 是否具备调用条件（有 key）。"""
    p = _provider()
    if p == "tavily":
        return bool(os.environ.get("TAVILY_API_KEY"))
    # serper / brave 等留作未来插拔点
    if p == "serper":
        return bool(os.environ.get("SERPER_API_KEY"))
    if p == "brave":
        return bool(os.environ.get("BRAVE_API_KEY"))
    return False


def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """联网搜索；返回 [{title, url, content}]。无 key / 异常 → 返回 []（静默降级）。"""
    q = (query or "").strip()
    if not q or not is_search_configured():
        return []
    p = _provider()
    try:
        if p == "tavily":
            return _tavily_search(q, max_results)
        # 未来：elif p == "serper": return _serper_search(...) / "brave": ...
        logger.info("未知搜索 Provider=%s，跳过联网", p)
        return []
    except Exception as e:  # 网络/配额/格式异常都不应影响主流程
        logger.warning("联网搜索失败(%s): %s", p, e)
        return []


def _tavily_search(query: str, max_results: int) -> List[Dict[str, str]]:
    api_key = os.environ.get("TAVILY_API_KEY")
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max(1, min(10, int(max_results or 5))),
            "search_depth": "basic",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json() or {}
    out: List[Dict[str, str]] = []
    for item in (data.get("results") or []):
        if not isinstance(item, dict):
            continue
        out.append({
            "title": (item.get("title") or "").strip(),
            "url": (item.get("url") or "").strip(),
            "content": (item.get("content") or "").strip(),
        })
    return out
