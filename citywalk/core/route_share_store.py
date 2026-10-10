# -*- coding: utf-8 -*-
"""已规划路线的短链分享存储（Zeabur volume / 本地目录）。"""

import json
import logging
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_ROUTE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,24}$")
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "shared_routes"
_MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
_TTL_DAYS_DEFAULT = 90


def _data_dir() -> Path:
    raw = os.environ.get("CITYWALK_SHARED_ROUTES_DIR", "").strip()
    if raw:
        return Path(raw)
    return _DEFAULT_DIR


def _ttl_seconds() -> int:
    try:
        days = int(os.environ.get("CITYWALK_ROUTE_SHARE_TTL_DAYS", str(_TTL_DAYS_DEFAULT)))
    except ValueError:
        days = _TTL_DAYS_DEFAULT
    if days <= 0:
        return 0
    return days * 86400


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _prune_expired(base: Path, ttl: int) -> None:
    if ttl <= 0:
        return
    now = time.time()
    try:
        for fp in base.glob("*.json"):
            try:
                if now - fp.stat().st_mtime > ttl:
                    fp.unlink(missing_ok=True)
            except OSError:
                continue
    except OSError as e:
        logging.warning("shared route prune skipped: %s", e)


def _new_id() -> str:
    return secrets.token_urlsafe(8).replace("+", "-").replace("/", "_")[:12]


def save_shared_route(snapshot: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    写入 snapshot JSON，返回 (route_id, error_message)。
    snapshot 须为 dict，且含 result.success === true。
    """
    if not isinstance(snapshot, dict):
        return None, "snapshot 格式无效"
    result = snapshot.get("result")
    if not isinstance(result, dict) or not result.get("success"):
        return None, "仅支持保存已成功规划的路线"
    if not isinstance(result.get("path"), list) or len(result["path"]) < 2:
        return None, "路线折线数据不完整"

    try:
        encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None, "snapshot 无法序列化"
    if len(encoded.encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
        return None, "路线数据过大，暂无法分享"

    base = _data_dir()
    _ensure_dir(base)
    _prune_expired(base, _ttl_seconds())

    now = time.time()
    doc = {
        "v": 1,
        "id": None,
        "created_at": now,
        "expires_at": (now + _ttl_seconds()) if _ttl_seconds() > 0 else None,
        "snapshot": snapshot,
    }

    for _ in range(8):
        rid = _new_id()
        fp = base / f"{rid}.json"
        if fp.exists():
            continue
        doc["id"] = rid
        tmp = base / f".{rid}.{secrets.token_hex(4)}.tmp"
        try:
            tmp.write_text(
                json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            tmp.replace(fp)
            return rid, None
        except OSError as e:
            logging.exception("save shared route failed")
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return None, f"存储失败：{e}"

    return None, "生成分享 id 失败，请重试"


def load_shared_route(route_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """返回 (snapshot, error_message)。"""
    if not route_id or not _ROUTE_ID_RE.match(route_id):
        return None, "分享 id 无效"

    fp = _data_dir() / f"{route_id}.json"
    if not fp.is_file():
        return None, "链接不存在或已过期"

    ttl = _ttl_seconds()
    if ttl > 0:
        try:
            if time.time() - fp.stat().st_mtime > ttl:
                fp.unlink(missing_ok=True)
                return None, "链接已过期"
        except OSError:
            return None, "无法读取分享"

    try:
        raw = fp.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None, "分享数据损坏"

    snapshot = doc.get("snapshot") if isinstance(doc, dict) else None
    if not isinstance(snapshot, dict):
        return None, "分享数据无效"
    result = snapshot.get("result")
    if not isinstance(result, dict) or not result.get("success"):
        return None, "分享数据无效"
    return snapshot, None
