# -*- coding: utf-8 -*-
"""智能规划：地图兜底与 payload 合并。"""
import logging
from typing import Any, Dict, Optional, Tuple

from citywalk.core.planning.constants import ROUTE_STYLE_CONFIG, normalize_visit_pace
from citywalk.core.planning.plan_budget import MAX_PLAN_TIME_MIN, MIN_PLAN_TIME_MIN
from citywalk.core.planning.poi_selection import normalize_poi_type

# 时段规划提示（轻量 hint，不新增重模型）
TIME_OF_DAY_HINTS = {
    "now": "",
    "afternoon": "午后时段，可偏咖啡馆与轻松逛点",
    "evening": "傍晚时段，偏好夜景、灯光与咖啡馆",
    "night": "夜晚时段，偏好夜景、灯光与咖啡馆",
}


def normalize_time_of_day(raw: Any) -> str:
    t = (raw or "").strip().lower() if isinstance(raw, str) else ""
    aliases = {
        "现在": "now", "now": "now",
        "午后": "afternoon", "afternoon": "afternoon",
        "傍晚": "evening", "evening": "evening",
        "夜晚": "night", "night": "night",
    }
    return aliases.get(t, "now")


def time_of_day_query_clause(time_of_day: Any) -> str:
    key = normalize_time_of_day(time_of_day)
    return TIME_OF_DAY_HINTS.get(key, "")

def _coords_pair_from_payload(raw: Any) -> Optional[Tuple[float, float]]:
    if isinstance(raw, list) and len(raw) == 2:
        try:
            return float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            return None
    return None


def _map_endpoints_ready(payload: Dict[str, Any]) -> bool:
    """前端已传合法起终点坐标（环线仅需起点）。"""
    mode = (payload.get("mode") or "route").strip().lower()
    start = _coords_pair_from_payload(payload.get("start"))
    if not start:
        return False
    if mode == "loop":
        return True
    return _coords_pair_from_payload(payload.get("end")) is not None


def _build_intent_from_map(payload: Dict[str, Any], default_city: str = "") -> Dict[str, Any]:
    """地图已选点、描述未写起终点时，构造 ready 意图。"""
    from citywalk.core.agent.orchestrator import clamp_plan_time

    mode = (payload.get("mode") or "route").strip().lower()
    if mode not in ("route", "loop"):
        mode = "route"
    city = (payload.get("city") or default_city or "").strip().replace("市", "")
    plan_override = _plan_time_from_payload(payload)
    plan_time = clamp_plan_time(plan_override, 60) if plan_override is not None else 60
    start_label = (payload.get("start_label") or "").strip() or "地图起点"
    end_label = (payload.get("end_label") or "").strip() or "地图终点"
    poi = normalize_poi_type((payload.get("poi_type") or "无偏好").strip() or "无偏好")
    rs = (payload.get("route_style") or "balanced").strip()
    if rs not in ROUTE_STYLE_CONFIG:
        rs = "balanced"
    visit_pace = normalize_visit_pace(payload.get("visit_pace"))
    end_text = end_label if mode != "loop" else start_label
    return {
        "status": "ready",
        "message": "已按地图所选起终点规划",
        "city": city,
        "start": start_label,
        "end": end_text,
        "plan_time": plan_time,
        "poi_type": poi,
        "route_style": rs,
        "visit_pace": visit_pace,
        "_plan_mode": mode,
    }


def _resolve_agent_intent(
        query: str,
        default_city: str,
        payload: Dict[str, Any],
) -> Dict[str, Any]:
    """LLM 解析 + 地图选点兜底；返回已 merge 的 ready 意图或 clarify/error。"""
    from citywalk.core.agent.orchestrator import parse_plan_intent

    query = (query or "").strip()
    default_city = (default_city or "").strip()
    plan_override = _plan_time_from_payload(payload)
    map_ready = _map_endpoints_ready(payload)

    if not query and not map_ready:
        return {
            "status": "clarify",
            "message": "请描述您的 Citywalk 需求，或在地图上选好起终点。",
        }

    # 时段 hint 并入解析文本，便于 LLM / 关键词推断；不阻塞规划
    tod_clause = time_of_day_query_clause(payload.get("time_of_day"))
    parse_query = query
    if query and tod_clause and tod_clause not in query:
        parse_query = f"{query}（{tod_clause}）"

    intent: Optional[Dict[str, Any]] = None
    if parse_query:
        intent = parse_plan_intent(
            parse_query, default_city=default_city, plan_time_override=plan_override,
        )
        if intent.get("status") == "error":
            return intent

    if map_ready and (not parse_query or (intent and intent.get("status") == "clarify")):
        intent = _build_intent_from_map(payload, default_city)
        logging.info("智能规划：地图起终点兜底（query=%r map_ready=True）", query[:80] if query else "")

    if not intent or intent.get("status") == "clarify":
        return intent or {
            "status": "clarify",
            "message": "请补充起点、终点或游玩时长。",
        }

    return _merge_payload_into_intent(intent, payload)


def _merge_payload_into_intent(intent: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """将侧栏滑块、地图选点、模式写入 ready 意图。"""
    if intent.get("status") != "ready":
        return intent
    from citywalk.core.agent.orchestrator import clamp_plan_time

    plan_override = _plan_time_from_payload(payload)
    if plan_override is not None:
        intent["plan_time"] = clamp_plan_time(plan_override, intent.get("plan_time", 60))

    city = (payload.get("city") or "").strip().replace("市", "")
    if city:
        intent["city"] = city

    # 偏好芯片：用户显式选择时优先生效；默认「无偏好」不覆盖 LLM 从描述解析的类型
    poi = (payload.get("poi_type") or "").strip()
    poi_locked = bool(payload.get("poi_type_locked"))
    if poi:
        if poi_locked or poi != "无偏好":
            intent["poi_type"] = normalize_poi_type(poi)
            intent["ambience_profile"] = intent["poi_type"]

    rs = (payload.get("route_style") or "").strip()
    if rs in ROUTE_STYLE_CONFIG:
        intent["route_style"] = rs

    if payload.get("visit_pace") is not None and str(payload.get("visit_pace")).strip() != "":
        intent["visit_pace"] = normalize_visit_pace(payload.get("visit_pace"))

    mode = (payload.get("mode") or "").strip().lower()
    if mode in ("route", "loop"):
        intent["_plan_mode"] = mode

    # 傍晚/夜晚且仍无偏好时，轻量偏置（用户显式锁定「无偏好」时不改写）
    tod = normalize_time_of_day(payload.get("time_of_day"))
    if (
        tod in ("evening", "night")
        and (intent.get("poi_type") or "无偏好") == "无偏好"
        and not (poi_locked and poi == "无偏好")
    ):
        intent["poi_type"] = "咖啡甜品"
        intent["ambience_profile"] = "咖啡甜品"

    start_xy = _coords_pair_from_payload(payload.get("start"))
    end_xy = _coords_pair_from_payload(payload.get("end"))
    if start_xy:
        intent["_map_start"] = [start_xy[0], start_xy[1]]
    if end_xy:
        intent["_map_end"] = [end_xy[0], end_xy[1]]
    return intent


def _intent_to_agent_plan_data(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 意图 → 规划引擎请求体（含地图坐标与 loop 模式）。"""
    from citywalk.core.agent.orchestrator import intent_to_plan_payload

    plan_data = intent_to_plan_payload(intent)
    mode = intent.get("_plan_mode")
    if mode in ("route", "loop"):
        plan_data["mode"] = mode
    if intent.get("_map_start"):
        plan_data["start"] = intent["_map_start"]
    if mode == "loop":
        plan_data.pop("end", None)
    elif intent.get("_map_end"):
        plan_data["end"] = intent["_map_end"]
    return plan_data


def _plan_time_from_payload(payload: Dict[str, Any]) -> Optional[int]:
    """侧栏计划时长滑块：plan_time_min 或 plan_time，合法则返回 int。"""
    raw = payload.get("plan_time_min")
    if raw is None:
        raw = payload.get("plan_time")
    if raw is None:
        return None
    try:
        t = int(raw)
    except (TypeError, ValueError):
        return None
    if t < MIN_PLAN_TIME_MIN or t > MAX_PLAN_TIME_MIN:
        return None
    return t
