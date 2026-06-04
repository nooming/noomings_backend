"""自然语言 → 规划参数。"""

import logging
from typing import Any, Dict, Optional

from planning.constants import normalize_visit_pace
from planning.plan_budget import MAX_PLAN_TIME_MIN, MIN_PLAN_TIME_MIN

from agent.llm_client import chat_json, is_configured
from agent.prompts import (
    POI_TYPES,
    ROUTE_STYLES,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    infer_city_from_text,
    infer_plan_time_from_query,
    normalize_poi_type,
)


def _infer_city_from_place(end: str, start: str = "") -> str:
    """用 place/text 从地标反推城市，补充文本关键词推断。"""
    for keyword in (end, start):
        if not keyword:
            continue
        try:
            from lib.geocoding import infer_city_from_place_keyword
            city = infer_city_from_place_keyword(keyword)
            if city:
                return city.replace("市", "")
        except Exception as exc:
            logger.debug("place 推断城市失败: %s", exc)
    return ""

logger = logging.getLogger(__name__)


def infer_visit_pace_from_query(user_query: str) -> str:
    """从用户话术推断停留节奏。"""
    q = (user_query or "").lower()
    relaxed_kw = ("久留", "坐下来", "慢慢逛", "深度", "多待", "细逛", "发呆")
    if any(k in q for k in relaxed_kw):
        return "relaxed"
    return "checkin"


def clamp_plan_time(value: Any, default: int = 60) -> int:
    try:
        t = int(value)
    except (TypeError, ValueError):
        t = default
    return max(MIN_PLAN_TIME_MIN, min(MAX_PLAN_TIME_MIN, t))


def parse_plan_intent(
        user_query: str,
        default_city: str = "",
        plan_time_override: Optional[int] = None) -> Dict[str, Any]:
    """
    解析用户自然语言为规划意图。
    返回字段含 status: ready|clarify|error，及 message、参数等。
    """
    query = (user_query or "").strip()
    if not query:
        return {
            "status": "clarify",
            "message": "请描述您的 Citywalk 需求，例如：上海静安寺到南京西路，90分钟咖啡路线。",
        }

    if not is_configured():
        return {
            "status": "error",
            "message": "智能规划暂时不可用，稍后再试",
        }

    city_ctx = (default_city or "").replace("市", "").strip()
    system = SYSTEM_PROMPT.replace("{default_city}", city_ctx or "未知")
    user = USER_PROMPT_TEMPLATE.format(query=query, default_city=city_ctx or "未知")

    try:
        raw = chat_json(system, user, temperature=0.25)
    except Exception as e:
        logger.error("LLM 解析失败: %s", e, exc_info=True)
        return {
            "status": "error",
            "message": "没太理解你的描述，换个说法再试试",
        }

    return normalize_intent(
        raw,
        default_city=city_ctx,
        user_query=query,
        plan_time_override=plan_time_override,
    )


def normalize_intent(
        raw: dict,
        default_city: str = "",
        user_query: str = "",
        plan_time_override: Optional[int] = None) -> Dict[str, Any]:
    """校验并规范化 LLM 输出。"""
    status = (raw.get("status") or "").strip().lower()
    message = (raw.get("message") or "").strip()

    if status == "clarify":
        return {
            "status": "clarify",
            "message": message or "请补充起点、终点或游玩时长。",
        }

    if status != "ready":
        return {
            "status": "clarify",
            "message": message or "未能理解您的需求，请补充起点和终点。",
        }

    city = (raw.get("city") or default_city or "").strip().replace("市", "")
    start = (raw.get("start") or "").strip()
    end = (raw.get("end") or "").strip()
    inferred_city = infer_city_from_text(user_query, start, end)
    if inferred_city:
        city = inferred_city
    elif not city or (default_city and city == default_city.replace("市", "")):
        place_city = _infer_city_from_place(end, start)
        if place_city:
            city = place_city
    poi_type = (raw.get("poi_type") or "无偏好").strip()
    route_style = (raw.get("route_style") or "balanced").strip()

    try:
        plan_time = int(raw.get("plan_time") or 60)
    except (TypeError, ValueError):
        plan_time = 60

    if not start or not end:
        return {
            "status": "clarify",
            "message": message or "请说明起点和终点（地标或地址）。",
        }

    if not city:
        return {
            "status": "clarify",
            "message": "请说明在哪座城市进行 Citywalk。",
        }

    poi_type = normalize_poi_type(poi_type)
    if poi_type not in POI_TYPES:
        poi_type = "无偏好"

    if route_style not in ROUTE_STYLES:
        route_style = "balanced"

    if plan_time_override is not None:
        plan_time = clamp_plan_time(plan_time_override, plan_time)
    else:
        query_plan = infer_plan_time_from_query(user_query)
        if query_plan > 0:
            plan_time = query_plan
        plan_time = clamp_plan_time(plan_time, 60)

    visit_pace = normalize_visit_pace(
        raw.get("visit_pace") or infer_visit_pace_from_query(user_query),
    )

    return {
        "status": "ready",
        "message": message or f"已理解：{city}，{start} → {end}，约 {plan_time} 分钟。",
        "city": city,
        "start": start,
        "end": end,
        "plan_time": plan_time,
        "poi_type": poi_type,
        "route_style": route_style,
        "ambience_profile": poi_type,
        "visit_pace": visit_pace,
    }


def intent_to_plan_payload(intent: Dict[str, Any]) -> Dict[str, Any]:
    """将 ready 意图转为 /plan 请求体。"""
    return {
        "start": intent["start"],
        "end": intent["end"],
        "plan_time": intent["plan_time"],
        "poi_type": intent["poi_type"],
        "route_style": intent["route_style"],
        "ambience_profile": intent.get("ambience_profile", intent["poi_type"]),
        "city": intent["city"],
        "visit_pace": intent.get("visit_pace", "checkin"),
    }
