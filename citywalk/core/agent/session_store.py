"""Agent 会话内存存储（单机）。"""

import time
import uuid
from typing import Any, Dict, List, Optional

SESSION_TTL_SEC = 7200
MAX_SESSIONS = 200
MAX_MESSAGES_PER_SESSION = 24

_sessions: Dict[str, Dict[str, Any]] = {}


def _prune_expired() -> None:
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s.get("updated_at", 0) > SESSION_TTL_SEC]
    for sid in expired:
        _sessions.pop(sid, None)
    if len(_sessions) > MAX_SESSIONS:
        ordered = sorted(_sessions.items(), key=lambda x: x[1].get("updated_at", 0))
        for sid, _ in ordered[: len(_sessions) - MAX_SESSIONS]:
            _sessions.pop(sid, None)


def create_session(
    plan_params: Optional[dict] = None,
    route_summary: Optional[dict] = None,
) -> str:
    _prune_expired()
    sid = str(uuid.uuid4())
    now = time.time()
    _sessions[sid] = {
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "plan_params": plan_params or {},
        "route_summary": route_summary or {},
    }
    return sid


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    _prune_expired()
    session = _sessions.get(session_id)
    if not session:
        return None
    if time.time() - session.get("updated_at", 0) > SESSION_TTL_SEC:
        _sessions.pop(session_id, None)
        return None
    return session


def update_session(
    session_id: str,
    *,
    plan_params: Optional[dict] = None,
    route_summary: Optional[dict] = None,
    append_message: Optional[dict] = None,
) -> bool:
    session = get_session(session_id)
    if not session:
        return False
    if plan_params is not None:
        session["plan_params"] = plan_params
    if route_summary is not None:
        session["route_summary"] = route_summary
    if append_message:
        session["messages"].append(append_message)
        if len(session["messages"]) > MAX_MESSAGES_PER_SESSION:
            session["messages"] = session["messages"][-MAX_MESSAGES_PER_SESSION:]
    session["updated_at"] = time.time()
    return True
