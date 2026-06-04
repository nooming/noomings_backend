# -*- coding: utf-8 -*-
"""智能规划：地图兜底与 payload 合并。"""
import logging
from typing import Any, Dict, Optional, Tuple

from planning.constants import ROUTE_STYLE_CONFIG
from planning.plan_budget import MAX_PLAN_TIME_MIN, MIN_PLAN_TIME_MIN
from planning.poi_selection import normalize_poi_type

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
    from agent.orchestrator import clamp_plan_time

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
        "_plan_mode": mode,
    }


def _resolve_agent_intent(
        query: str,
        default_city: str,
        payload: Dict[str, Any],
) -> Dict[str, Any]:
    """LLM 解析 + 地图选点兜底；返回已 merge 的 ready 意图或 clarify/error。"""
    from agent.orchestrator import parse_plan_intent

    query = (query or "").strip()
    default_city = (default_city or "").strip()
    plan_override = _plan_time_from_payload(payload)
    map_ready = _map_endpoints_ready(payload)

    if not query and not map_ready:
        return {
            "status": "clarify",
            "message": "请描述您的 Citywalk 需求，或在地图上选好起终点。",
        }

    intent: Optional[Dict[str, Any]] = None
    if query:
        intent = parse_plan_intent(
            query, default_city=default_city, plan_time_override=plan_override,
        )
        if intent.get("status") == "error":
            return intent

    if map_ready and (not query or intent.get("status") == "clarify"):
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
    from agent.orchestrator import clamp_plan_time

    plan_override = _plan_time_from_payload(payload)
    if plan_override is not None:
        intent["plan_time"] = clamp_plan_time(plan_override, intent.get("plan_time", 60))

    city = (payload.get("city") or "").strip().replace("市", "")
    if city:
        intent["city"] = city

    poi = (payload.get("poi_type") or "").strip()
    if poi:
        intent["poi_type"] = normalize_poi_type(poi)

    rs = (payload.get("route_style") or "").strip()
    if rs in ROUTE_STYLE_CONFIG:
        intent["route_style"] = rs

    mode = (payload.get("mode") or "").strip().lower()
    if mode in ("route", "loop"):
        intent["_plan_mode"] = mode

    start_xy = _coords_pair_from_payload(payload.get("start"))
    end_xy = _coords_pair_from_payload(payload.get("end"))
    if start_xy:
        intent["_map_start"] = [start_xy[0], start_xy[1]]
    if end_xy:
        intent["_map_end"] = [end_xy[0], end_xy[1]]
    return intent


def _intent_to_agent_plan_data(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 意图 → 规划引擎请求体（含地图坐标与 loop 模式）。"""
    from agent.orchestrator import intent_to_plan_payload

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
