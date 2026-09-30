"""联网搜索（博查 Bocha）。

给灵感选点提供真实网页结果做 grounding：先搜，再让 LLM 仅从结果里提取地点名。
未配 `BOCHA_API_KEY` 或请求失败时返回空列表，调用方回退到纯 LLM 选点。

env：
  CW_SEARCH_PROVIDER  默认 bocha（仅支持 bocha）
  BOCHA_API_KEY       留空 → 不联网，静默降级
"""

import logging
import os
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)


def _provider() -> str:
    return os.environ.get("CW_SEARCH_PROVIDER", "bocha").strip().lower()


def is_search_configured() -> bool:
    """当前搜索是否具备调用条件（provider=bocha 且 key 非空）。"""
    if _provider() != "bocha":
        return False
    return bool(os.environ.get("BOCHA_API_KEY"))


def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """联网搜索；返回 [{title, url, content}]。无 key / 异常 → 返回 []（静默降级）。"""
    q = (query or "").strip()
    if not q or not is_search_configured():
        return []
    try:
        return _bocha_search(q, max_results)
    except Exception as e:  # 网络/配额/格式异常都不应影响主流程
        logger.warning("联网搜索失败(bocha): %s", e)
        return []


def _bocha_search(query: str, max_results: int) -> List[Dict[str, str]]:
    api_key = os.environ.get("BOCHA_API_KEY")
    count = max(1, min(10, int(max_results or 5)))
    resp = requests.post(
        "https://api.bochaai.com/v1/web-search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "count": count,
            "summary": True,
        },
        timeout=15,
    )
    if not resp.ok:
        logger.warning("Bocha HTTP %s", resp.status_code)
        return []
    try:
        data = resp.json() or {}
    except ValueError:
        logger.warning("Bocha 返回非 JSON")
        return []

    items = _bocha_result_items(data)
    out: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = (item.get("name") or item.get("title") or "").strip()
        url = (item.get("url") or item.get("link") or "").strip()
        content = (
            item.get("summary")
            or item.get("snippet")
            or item.get("content")
            or ""
        )
        content = str(content).strip()
        if not title and not url and not content:
            continue
        out.append({"title": title, "url": url, "content": content})
    if not out:
        logger.warning("Bocha 无有效结果")
    return out


def _bocha_result_items(data: Any) -> List[Any]:
    """兼容 data.webPages.value / webPages.value / results 几种响应壳。"""
    if not isinstance(data, dict):
        return []
    for path in (
        ("data", "webPages", "value"),
        ("webPages", "value"),
        ("data", "results"),
        ("results",),
    ):
        cur: Any = data
        ok = True
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok and isinstance(cur, list):
            return cur
    return []
