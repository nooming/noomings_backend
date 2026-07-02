"""内容种草·灵感来源（合规版）。

把用户的软性想法解析为主题/关键词（②），再由「灵感来源 Provider」给出
真实存在的候选地点（③）。默认 Provider 用 LLM 自身知识（合规、稳定）；
未来可插拔联网搜索 / 小红书等数据源（须自备合规数据访问）。

注意：小红书无官方开放 API，爬取有 ToS / 版权 / 稳定性风险，故不内置。
"""

import json
import logging
import os
from typing import Any, Dict, List

from citywalk.core.agent.llm_client import chat_json, is_configured

logger = logging.getLogger(__name__)


_THEME_SYSTEM = """你是 Citywalk 选题分析助手。用户用自然语言描述想逛的感觉/主题。
把它解析为结构化的主题与可搜索关键词，供后续找点使用。只输出一个 JSON 对象：
{
  "themes": ["不超过4个中文短词，如 出片、小众、文艺、夜景、复古"],
  "keywords": ["不超过6个适合搜索的中文短词，如 买手店、老洋房、独立咖啡、城市公园"],
  "area": "若用户提到具体片区/商圈则填（如 武康路、南锣鼓巷），否则空字符串"
}
不要编造城市；不要输出 markdown 或多余说明。"""

_SPOTS_SYSTEM = """你是本地 Citywalk 选点专家。根据给定城市、片区与主题关键词，
推荐**真实存在、知名度较高**的具体地点（店铺/景点/街区节点），供后续地理编码与路线串点。

严格要求：
1. 只给真实、可被地图检索到的地点名；**绝不编造**不存在的店名或地址。
2. 名称尽量写**全称 + 所在区/片区**，便于地理编码（如「武康路（武康大楼一带）」「teamLab 上海」）。
3. 与主题/关键词相关，分布在同一城市、尽量集中在给定片区附近。
4. 只输出一个 JSON 对象：
{ "spots": [ { "name": "地点名", "reason": "一句中文推荐理由(≤20字)", "category": "类型如 咖啡馆/书店/公园/展览/街区" } ] }
不要输出 markdown 或多余说明。"""

_WEB_SPOTS_SYSTEM = """你是本地 Citywalk 选点专家。下面给你一批**真实联网搜索结果**（标题+正文摘要）。
请**仅从这些搜索结果里**抽取真实存在、与主题相关的具体地点（店铺/景点/街区节点）。

严格要求：
1. 只提取搜索结果中明确出现的真实地点名；**绝不编造**结果里没有的店名或地址。
2. 名称尽量写**全称 + 所在区/片区**，便于地理编码（如「武康路（武康大楼一带）」）。
3. 优先与给定城市/片区/主题相关、可被地图检索到的地点；过滤掉榜单标题、平台名、无法定位的泛称。
4. 只输出一个 JSON 对象：
{ "spots": [ { "name": "地点名", "reason": "一句中文推荐理由(≤20字)", "category": "类型如 咖啡馆/书店/公园/展览/街区" } ] }
不要输出 markdown 或多余说明。"""


def analyze_intent_themes(query: str, city: str = "") -> Dict[str, Any]:
    """② 用户想法 → 主题/关键词/片区。"""
    q = (query or "").strip()
    if not q or not is_configured():
        return {"themes": [], "keywords": [], "area": ""}
    user = f"城市：{city or '未知'}\n用户描述：{q}"
    try:
        raw = chat_json(_THEME_SYSTEM, user, temperature=0.3)
    except Exception as e:
        logger.warning("主题解析失败: %s", e)
        return {"themes": [], "keywords": [], "area": ""}
    return {
        "themes": _str_list(raw.get("themes"))[:4],
        "keywords": _str_list(raw.get("keywords"))[:6],
        "area": (raw.get("area") or "").strip(),
    }


def suggest_spots(
    city: str,
    area: str = "",
    themes: List[str] = None,
    keywords: List[str] = None,
    count: int = 8,
) -> List[Dict[str, str]]:
    """③ 主题/关键词 → 真实候选地点（经由可插拔 Provider）。"""
    provider = os.environ.get("CW_INSPIRATION_PROVIDER", "llm").strip().lower()
    themes = themes or []
    keywords = keywords or []
    if provider in ("web_search", "tavily", "web"):
        # 联网搜索 grounding；无 key / 无结果时内部回退到 LLM 选点。
        return _web_suggest_spots(city, area, themes, keywords, count)
    if provider not in ("llm",):
        logger.info("未知灵感 Provider=%s，回退 llm", provider)
    return _llm_suggest_spots(city, area, themes, keywords, count)


def _web_suggest_spots(
    city: str, area: str, themes: List[str], keywords: List[str], count: int
) -> List[Dict[str, str]]:
    """联网搜索 + LLM 抽取：先搜真实结果，再让 LLM 只从结果里提取地点名。"""
    from citywalk.core.agent.search_provider import is_search_configured, web_search

    if not city or not is_configured() or not is_search_configured():
        return _llm_suggest_spots(city, area, themes, keywords, count)

    count = max(1, min(12, int(count or 8)))
    # 由 城市+片区+关键词 拼若干搜索 query；关键词缺省时退回主题。
    terms = keywords or themes or ["小众", "出片"]
    queries = [f"{city} {area} {t} 推荐".strip() for t in terms[:4]]
    if not queries:
        queries = [f"{city} {area} citywalk 小众 推荐".strip()]

    snippets: List[str] = []
    seen_url = set()
    for q in queries:
        for r in web_search(q, max_results=5):
            url = r.get("url", "")
            if url and url in seen_url:
                continue
            if url:
                seen_url.add(url)
            line = f"标题：{r.get('title','')}\n摘要：{r.get('content','')}".strip()
            if line:
                snippets.append(line)

    if not snippets:
        # 联网无结果（无 key / 配额 / 网络）→ 回退纯 LLM 选点
        return _llm_suggest_spots(city, area, themes, keywords, count)

    user = (
        f"城市：{city}\n片区：{area or '不限'}\n"
        f"主题：{', '.join(themes) or '无偏好'}\n关键词：{', '.join(keywords) or '无'}\n"
        f"请给出约 {count} 个地点。\n\n"
        f"以下是联网搜索结果（仅从中提取）：\n\n" + "\n\n".join(snippets[:12])
    )
    try:
        raw = chat_json(_WEB_SPOTS_SYSTEM, user, temperature=0.4)
    except Exception as e:
        logger.warning("联网选点抽取失败: %s", e)
        return _llm_suggest_spots(city, area, themes, keywords, count)
    return _dedupe_spots(raw.get("spots"), count)


def _llm_suggest_spots(
    city: str, area: str, themes: List[str], keywords: List[str], count: int
) -> List[Dict[str, str]]:
    if not city or not is_configured():
        return []
    count = max(1, min(12, int(count or 8)))
    user = (
        f"城市：{city}\n片区：{area or '不限'}\n"
        f"主题：{', '.join(themes) or '无偏好'}\n关键词：{', '.join(keywords) or '无'}\n"
        f"请给出约 {count} 个地点。"
    )
    try:
        raw = chat_json(_SPOTS_SYSTEM, user, temperature=0.6)
    except Exception as e:
        logger.warning("灵感选点失败: %s", e)
        return []
    return _dedupe_spots(raw.get("spots"), count)


def _dedupe_spots(items: Any, count: int) -> List[Dict[str, str]]:
    """规整 LLM 返回的 spots：按名称去重、裁字段、限量。两条选点路径共用。"""
    spots: List[Dict[str, str]] = []
    seen = set()
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        spots.append({
            "name": name,
            "reason": (item.get("reason") or "").strip(),
            "category": (item.get("category") or "").strip(),
        })
        if len(spots) >= count:
            break
    return spots


def _str_list(v: Any) -> List[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()]
