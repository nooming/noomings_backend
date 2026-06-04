# -*- coding: utf-8 -*-
"""Flask 路由：/agent/*、/poi/enrich。"""
import logging
import os
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from planning.plan_budget import MAX_PLAN_TIME_MIN, MIN_PLAN_TIME_MIN
from planning.plan_service import execute_plan_request, fetch_poi_photos
from planning.poi_selection import normalize_poi_type
from planning.constants import ROUTE_STYLE_CONFIG
from planning.runtime import AMAP_KEY
from api.agent_intent import (
    _plan_time_from_payload,
    _resolve_agent_intent,
    _intent_to_agent_plan_data,
)

bp = Blueprint("cw_agent", __name__)

@bp.route('/agent/plan_once', methods=['POST', 'OPTIONS'])
def agent_plan_once():
    """自然语言 → 解析参数 → 调用规划引擎 → 返回路线与解析结果。"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    blocked = _agent_rate_check()
    if blocked:
        return blocked

    try:
        payload = request.get_json(silent=True) or {}
        query = (payload.get("query") or "").strip()
        default_city = (payload.get("city") or "").strip()

        intent = _resolve_agent_intent(query, default_city, payload)
        plan_override = _plan_time_from_payload(payload)

        if intent.get("status") == "clarify":
            return jsonify({
                "success": False,
                "agent_status": "clarify",
                "message": intent.get("message", "请补充更多信息"),
            }), 200

        if intent.get("status") == "error":
            return jsonify({
                "success": False,
                "agent_status": "error",
                "message": intent.get("message", "智能规划不可用"),
            }), 200

        plan_data = _intent_to_agent_plan_data(intent)
        selected = _clean_selected_spots(payload.get("selected_spots"))
        if selected:
            plan_data["seed_pois"] = selected
        logging.info(
            "agent_plan_once plan_override=%s intent_plan_time=%s mode=%s map_start=%s selected_spots=%s",
            plan_override,
            intent.get("plan_time"),
            plan_data.get("mode"),
            bool(intent.get("_map_start")),
            len(selected),
        )
        body, status, meta = execute_plan_request(plan_data)

        parsed = {
            "city": intent.get("city"),
            "start": intent.get("start"),
            "end": intent.get("end"),
            "plan_time": intent.get("plan_time"),
            "poi_type": intent.get("poi_type"),
            "route_style": intent.get("route_style"),
            "visit_pace": intent.get("visit_pace", "checkin"),
            "start_coords": meta.get("start_coords"),
            "end_coords": meta.get("end_coords"),
        }

        if not body.get("success"):
            agent_fail = (
                "clarify"
                if status == 400 or meta.get("validation_failed")
                else "plan_failed"
            )
            return jsonify(_agent_fail_payload(body, agent_fail, parsed)), 200

        from agent.session_store import create_session, update_session
        from agent.chat_handler import build_route_summary

        session_id = create_session(
            plan_params=plan_data,
            route_summary=build_route_summary(body) if body.get("success") else {},
        )
        update_session(
            session_id,
            append_message={"role": "user", "content": query},
        )
        update_session(
            session_id,
            append_message={"role": "assistant", "content": intent.get("message", "")},
        )

        response = {
            **body,
            "agent_status": "ready",
            "agent_message": intent.get("message", ""),
            "parsed": parsed,
            "session_id": session_id,
        }
        return jsonify(response), 200
    except Exception as e:
        logging.exception("agent_plan_once 异常")
        return jsonify({
            "success": False,
            "agent_status": "error",
            "message": "智能规划暂时不可用，稍后再试",
        }), 200


def _agent_fail_payload(body: dict, agent_status: str, parsed: dict, **extra) -> dict:
    """Agent 规划失败响应体：保证 message 非空，并透传 quota_exceeded。"""
    msg = (body.get("message") or "").strip()
    if not msg:
        msg = "这条路线没能规划出来，请换个说法试试"
    out = {
        "success": False,
        "agent_status": agent_status,
        "message": msg,
        "parsed": parsed,
    }
    if body.get("quota_exceeded"):
        out["quota_exceeded"] = True
        out["retry_after"] = body.get("retry_after", 30)
    out.update(extra)
    return out


def _agent_client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()


def _agent_rate_check():
    from agent.rate_limit import allow_request
    if not allow_request(_agent_client_ip()):
        return jsonify({
            "success": False,
            "agent_status": "error",
            "message": "请求过于频繁，请稍后再试",
        }), 429
    return None


# ==================== Agent：多轮对话 ====================
@bp.route('/agent/chat', methods=['POST', 'OPTIONS'])
def agent_chat():
    """多轮调整路线或咨询当前规划。"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    blocked = _agent_rate_check()
    if blocked:
        return blocked

    try:
        payload = request.get_json(silent=True) or {}
        message = (payload.get("message") or "").strip()
        session_id = (payload.get("session_id") or "").strip() or None
        context = payload.get("context") or {}

        from agent.chat_handler import handle_chat

        result = handle_chat(
            message=message,
            session_id=session_id,
            context=context,
            plan_fn=execute_plan_request,
        )
        status = 200
        if result.get("agent_status") == "plan_failed" and not result.get("success"):
            status = 400 if "plan_time" in str(result.get("message", "")) else 200
        return jsonify(result), status
    except Exception as e:
        logging.exception("agent_chat 异常")
        return jsonify({
            "success": False,
            "agent_status": "error",
            "message": "对话出了点小状况，请再说一次",
        }), 200


# ==================== Agent：游玩攻略文案 ====================
@bp.route('/agent/guide', methods=['POST', 'OPTIONS'])
def agent_guide():
    """根据路线结果生成 AI 攻略，失败时前端回退模板。"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    blocked = _agent_rate_check()
    if blocked:
        return blocked

    payload = request.get_json(silent=True) or {}
    from agent.guide import generate_guide

    result = generate_guide(payload)
    code = 200 if result.get("success") else 503
    return jsonify(result), code


# ==================== 内容种草流水线 ====================
@bp.route('/agent/inspire', methods=['POST', 'OPTIONS'])
def agent_inspire():
    """②③ 用户想法 → 主题/关键词 → 真实候选地点（已地理编码）。"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    blocked = _agent_rate_check()
    if blocked:
        return blocked

    try:
        payload = request.get_json(silent=True) or {}
        query = (payload.get("query") or "").strip()[:500]
        city = (payload.get("city") or "").strip().replace("市", "")

        from agent.inspiration import analyze_intent_themes, suggest_spots

        analysis = analyze_intent_themes(query, city)
        spots = suggest_spots(
            city, analysis.get("area", ""),
            analysis.get("themes"), analysis.get("keywords"), count=8,
        )

        # 并发地理编码各候选点（executor.map 保序），解析失败者丢弃。
        # 串行 N 次高德调用既慢又增 CUQPS 风险，与仓内其它 fan-out 用法一致。
        def _geocode_spot(s):
            coords = resolve_location(s["name"], city or None)
            if not coords:
                return None
            return {**s, "lng": coords[0], "lat": coords[1]}

        out = []
        if spots:
            with ThreadPoolExecutor(
                    max_workers=min(AMAP_POOL_WORKERS, len(spots))
            ) as executor:
                for res in executor.map(_geocode_spot, spots):
                    if res:
                        out.append(res)

        return jsonify({
            "success": True,
            "themes": analysis.get("themes", []),
            "keywords": analysis.get("keywords", []),
            "area": analysis.get("area", ""),
            "spots": out,
        })
    except Exception:
        logging.exception("agent_inspire 异常")
        return jsonify({"success": False, "message": "灵感推荐暂时不可用，稍后再试"}), 200


@bp.route('/poi/enrich', methods=['POST', 'OPTIONS'])
def poi_enrich():
    """① 单个打卡点增强：高德官方图片 + 一句 LLM 描述（前端懒加载）。"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    blocked = _agent_rate_check()
    if blocked:
        return blocked

    try:
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "message": "缺少地点名"}), 400
        city = (payload.get("city") or "").strip().replace("市", "")
        category = (payload.get("category") or "").strip()
        area = (payload.get("area") or "").strip()
        lng = payload.get("lng")
        lat = payload.get("lat")

        from agent.enrichment import describe_poi

        photos = fetch_poi_photos(
            name, city,
            float(lng) if lng is not None else None,
            float(lat) if lat is not None else None,
        )
        description = describe_poi(name, category, city, area)
        return jsonify({
            "success": True,
            "name": name,
            "photos": photos,
            "description": description,
        })
    except Exception:
        logging.exception("poi_enrich 异常")
        return jsonify({"success": False, "message": "增强信息暂时不可用"}), 200


def _clean_selected_spots(raw: Any) -> List[Dict[str, Any]]:
    """规整前端勾选的灵感卡片：保留带有效坐标的项，最多 8 个。"""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in raw[:16]:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name or name in seen:
            continue
        try:
            lng = float(item.get("lng"))
            lat = float(item.get("lat"))
        except (TypeError, ValueError):
            continue
        seen.add(name)
        out.append({
            "name": name,
            "reason": (item.get("reason") or "").strip(),
            "category": (item.get("category") or "").strip(),
            "lng": lng,
            "lat": lat,
        })
        if len(out) >= 8:
            break
    return out


@bp.route('/agent/plan_inspired', methods=['POST', 'OPTIONS'])
def agent_plan_inspired():
    """②③④ 一体：想法 → 参数 + 种草候选点 → 注入规划引擎。

    `selected_spots`（可选）：前端「灵感卡片」勾选的带坐标候选点；给出则跳过自动选点。
    """
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    blocked = _agent_rate_check()
    if blocked:
        return blocked

    try:
        payload = request.get_json(silent=True) or {}
        query = (payload.get("query") or "").strip()[:500]
        default_city = (payload.get("city") or "").strip()

        from agent.inspiration import analyze_intent_themes, suggest_spots

        intent = _resolve_agent_intent(query, default_city, payload)
        plan_override = _plan_time_from_payload(payload)
        if intent.get("status") == "clarify":
            return jsonify({
                "success": False, "agent_status": "clarify",
                "message": intent.get("message", "请补充更多信息"),
            }), 200
        if intent.get("status") == "error":
            return jsonify({
                "success": False, "agent_status": "error",
                "message": intent.get("message", "智能规划不可用"),
            }), 200

        plan_data = _intent_to_agent_plan_data(intent)
        city = intent.get("city") or default_city.replace("市", "")

        # 用户在「灵感卡片」里已勾选候选点（带坐标）→ 直接用，跳过重新选点。
        selected = _clean_selected_spots(payload.get("selected_spots"))
        if selected:
            analysis = {"themes": [], "keywords": [], "area": ""}
            spots = selected
        else:
            inspire_query = query or "沿地图所选起终点漫步，无特别偏好"
            analysis = analyze_intent_themes(inspire_query, city)
            spots = suggest_spots(
                city, analysis.get("area", ""),
                analysis.get("themes"), analysis.get("keywords"), count=6,
            )
        if spots:
            plan_data["seed_pois"] = spots  # 带坐标则直接用，仅名称则 execute_plan_request 内部地理编码

        logging.info(
            "agent_plan_inspired plan_override=%s intent_plan_time=%s mode=%s map_start=%s user_selected=%s",
            plan_override,
            intent.get("plan_time"),
            plan_data.get("mode"),
            bool(intent.get("_map_start")),
            len(selected),
        )
        body, status, meta = execute_plan_request(plan_data)

        parsed = {
            "city": intent.get("city"),
            "start": intent.get("start"),
            "end": intent.get("end"),
            "plan_time": intent.get("plan_time"),
            "poi_type": intent.get("poi_type"),
            "route_style": intent.get("route_style"),
            "visit_pace": intent.get("visit_pace", "checkin"),
            "start_coords": meta.get("start_coords"),
            "end_coords": meta.get("end_coords"),
        }
        inspiration = {
            "themes": analysis.get("themes", []),
            "keywords": analysis.get("keywords", []),
            "area": analysis.get("area", ""),
            "spots": spots,
            "seed_poi_count": meta.get("seed_poi_count", 0),
            "seed_matched_names": meta.get("seed_matched_names", []),
            "user_selected_names": [s.get("name") for s in selected] if selected else [],
        }

        if not body.get("success"):
            agent_fail = "clarify" if status == 400 or meta.get("validation_failed") else "plan_failed"
            return jsonify(
                _agent_fail_payload(body, agent_fail, parsed, inspiration=inspiration),
            ), 200

        from agent.session_store import create_session, update_session
        from agent.chat_handler import build_route_summary

        session_id = create_session(
            plan_params=plan_data,
            route_summary=build_route_summary(body),
        )
        update_session(session_id, append_message={"role": "user", "content": query})
        update_session(session_id, append_message={"role": "assistant", "content": intent.get("message", "")})

        return jsonify({
            **body,
            "agent_status": "ready",
            "agent_message": intent.get("message", ""),
            "parsed": parsed,
            "inspiration": inspiration,
            "session_id": session_id,
        }), 200
    except Exception:
        logging.exception("agent_plan_inspired 异常")
        return jsonify({
            "success": False, "agent_status": "error",
            "message": "灵感规划暂时不可用，稍后再试",
        }), 200

