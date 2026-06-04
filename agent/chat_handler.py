"""多轮对话：改参重规划 / 解释 / 追问。"""

import logging
from typing import Any, Callable, Dict, Optional, Tuple

from agent.llm_client import chat_json, is_configured
from agent.orchestrator import intent_to_plan_payload, normalize_intent
from agent.prompts import CHAT_SYSTEM_PROMPT, POI_TYPES, ROUTE_STYLES, normalize_poi_type
from agent.session_store import create_session, get_session, update_session

logger = logging.getLogger(__name__)


def merge_plan_params(base: dict, delta: Optional[dict]) -> dict:
    """合并会话参数与 LLM 增量。"""
    out = dict(base or {})
    if not delta:
        return out
    for key in ("city", "start", "end", "poi_type", "route_style"):
        val = delta.get(key)
        if val is not None and str(val).strip():
            out[key] = str(val).strip().replace("市", "") if key == "city" else str(val).strip()
    if delta.get("plan_time") is not None:
        try:
            out["plan_time"] = int(delta["plan_time"])
        except (TypeError, ValueError):
            pass
    if out.get("poi_type"):
        out["poi_type"] = normalize_poi_type(out["poi_type"])
    if out.get("poi_type") not in POI_TYPES:
        out["poi_type"] = "无偏好"
    if out.get("route_style") not in ROUTE_STYLES:
        out["route_style"] = "balanced"
    out["ambience_profile"] = out.get("poi_type", "无偏好")
    if out.get("plan_time"):
        out["plan_time"] = max(30, min(240, int(out["plan_time"])))
    return out


# 对话可触发的页面操作白名单（前端有对应的分发实现）
ALLOWED_UI_COMMANDS = {
    "generate_guide",
    "generate_share_image",
    "highlight_poi",
    "switch_city",
    "reset",
}


def build_route_summary(plan_body: dict) -> dict:
    pois = plan_body.get("pois") or []
    return {
        "distance_m": plan_body.get("distance"),
        "duration_min": plan_body.get("duration"),
        "poi_count": len(pois),
        "poi_names": [p.get("name") for p in pois[:12] if p.get("name")],
        # 结构化打卡点明细：让 explain/replan 能基于真实数据回答
        "pois": [
            {
                "index": i + 1,
                "name": p.get("name"),
                "type": p.get("type") or p.get("category"),
                "reason": p.get("recommendation_reason"),
                "stay_time": p.get("stay_time"),
            }
            for i, p in enumerate(pois[:12])
            if p.get("name")
        ],
    }


def _sanitize_ui_command(command: Optional[str], args: Optional[dict]) -> Tuple[Optional[str], dict]:
    """校验 LLM 给出的页面指令，非法则返回 (None, {})。"""
    cmd = (command or "").strip()
    if cmd not in ALLOWED_UI_COMMANDS:
        return None, {}
    safe_args: Dict[str, Any] = {}
    src = args or {}
    if cmd == "highlight_poi":
        try:
            idx = int(src.get("index"))
        except (TypeError, ValueError):
            return None, {}
        if idx < 1:
            return None, {}
        safe_args["index"] = idx
    elif cmd == "switch_city":
        city = str(src.get("city") or "").strip().replace("市", "")
        if not city:
            return None, {}
        safe_args["city"] = city
    return cmd, safe_args


def handle_chat(
    message: str,
    session_id: Optional[str],
    context: Optional[dict],
    plan_fn: Callable[[dict], Tuple[dict, int, dict]],
) -> Dict[str, Any]:
    """
    处理对话消息。plan_fn 即 execute_plan_request。
    """
    text = (message or "").strip()
    if not text:
        return {
            "success": False,
            "agent_status": "clarify",
            "message": "请输入您想调整或咨询的内容。",
            "session_id": session_id,
        }

    if not is_configured():
        return {
            "success": False,
            "agent_status": "error",
            "message": "对话暂时不可用，稍后再试",
            "session_id": session_id,
        }

    session = get_session(session_id) if session_id else None
    plan_params = (session or {}).get("plan_params") or {}
    route_summary = (session or {}).get("route_summary") or {}

    if context:
        if context.get("plan_params"):
            plan_params = {**plan_params, **context["plan_params"]}
        if context.get("route_summary"):
            route_summary = {**route_summary, **context["route_summary"]}

    if not session_id:
        session_id = create_session(plan_params=plan_params, route_summary=route_summary)
        session = get_session(session_id)

    user_prompt = _format_chat_user(text, plan_params, route_summary, session)

    try:
        raw = chat_json(CHAT_SYSTEM_PROMPT, user_prompt, temperature=0.35)
    except Exception as e:
        logger.error("对话 LLM 失败: %s", e, exc_info=True)
        return {
            "success": False,
            "agent_status": "error",
            "message": "对话出了点小状况，请再说一次",
            "session_id": session_id,
        }

    action = (raw.get("action") or "reply").strip().lower()
    reply_msg = (raw.get("message") or "").strip()
    param_delta = raw.get("param_delta") or {}

    update_session(
        session_id,
        append_message={"role": "user", "content": text},
    )

    if action == "clarify":
        update_session(session_id, append_message={"role": "assistant", "content": reply_msg})
        return {
            "success": False,
            "agent_status": "clarify",
            "message": reply_msg or "请补充更多信息。",
            "session_id": session_id,
        }

    if action in ("explain", "reply"):
        update_session(session_id, append_message={"role": "assistant", "content": reply_msg})
        return {
            "success": True,
            "agent_status": action,
            "message": reply_msg or "好的。",
            "session_id": session_id,
        }

    if action == "ui_command":
        cmd, safe_args = _sanitize_ui_command(raw.get("command"), raw.get("args"))
        if not cmd:
            # 指令非法 → 退化为普通回复，避免前端收到无法执行的命令
            update_session(session_id, append_message={"role": "assistant", "content": reply_msg})
            return {
                "success": True,
                "agent_status": "reply",
                "message": reply_msg or "好的。",
                "session_id": session_id,
            }
        update_session(session_id, append_message={"role": "assistant", "content": reply_msg})
        return {
            "success": True,
            "agent_status": "ui_command",
            "command": cmd,
            "args": safe_args,
            "message": reply_msg or "好的，这就为你操作。",
            "session_id": session_id,
        }

    if action == "replan":
        merged = merge_plan_params(plan_params, param_delta)
        if not merged.get("start") or not merged.get("end"):
            return {
                "success": False,
                "agent_status": "clarify",
                "message": reply_msg or "请先完成一次路线规划，或说明起点和终点。",
                "session_id": session_id,
            }
        intent = normalize_intent(
            {
                "status": "ready",
                "city": merged.get("city") or "北京",
                "start": merged["start"],
                "end": merged["end"],
                "plan_time": merged.get("plan_time") or 60,
                "poi_type": merged.get("poi_type") or "无偏好",
                "route_style": merged.get("route_style") or "balanced",
                "message": reply_msg,
            },
            default_city=merged.get("city") or "",
        )
        if intent.get("status") != "ready":
            return {
                "success": False,
                "agent_status": "clarify",
                "message": intent.get("message", "参数不完整"),
                "session_id": session_id,
            }

        plan_data = intent_to_plan_payload(intent)
        body, status, meta = plan_fn(plan_data)
        route_summary = build_route_summary(body) if body.get("success") else route_summary
        update_session(
            session_id,
            plan_params=plan_data,
            route_summary=route_summary,
            append_message={"role": "assistant", "content": reply_msg or "已为您重新规划路线。"},
        )
        parsed = {
            "city": intent.get("city"),
            "start": intent.get("start"),
            "end": intent.get("end"),
            "plan_time": intent.get("plan_time"),
            "poi_type": intent.get("poi_type"),
            "route_style": intent.get("route_style"),
            "start_coords": meta.get("start_coords"),
            "end_coords": meta.get("end_coords"),
        }
        return {
            **body,
            "success": body.get("success", False),
            "agent_status": "replan" if body.get("success") else "plan_failed",
            "agent_message": reply_msg or intent.get("message", ""),
            "message": reply_msg or body.get("message", ""),
            "session_id": session_id,
            "parsed": parsed,
        }

    update_session(session_id, append_message={"role": "assistant", "content": reply_msg})
    return {
        "success": True,
        "agent_status": "reply",
        "message": reply_msg or "好的。",
        "session_id": session_id,
    }


def _format_chat_user(
    text: str,
    plan_params: dict,
    route_summary: dict,
    session: Optional[dict],
) -> str:
    history = ""
    if session and session.get("messages"):
        lines = []
        for m in session["messages"][-8:]:
            role = "用户" if m.get("role") == "user" else "助手"
            lines.append(f"{role}：{m.get('content', '')}")
        history = "\n".join(lines)

    return (
        f"用户新消息：{text}\n\n"
        f"当前规划参数：{plan_params}\n"
        f"当前路线摘要：{route_summary}\n"
        f"近期对话：\n{history or '（无）'}"
    )
