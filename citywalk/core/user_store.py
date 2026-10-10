# -*- coding: utf-8 -*-
"""Citywalk 用户与足迹/收藏同步存储（volume 目录）。"""

import json
import logging
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from citywalk.core.user_auth import hash_password, normalize_email, verify_password

_USER_ID_RE = re.compile(r"^[a-f0-9-]{36}$")
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "users"
_MAX_SYNC_BYTES = 512 * 1024


def _data_dir() -> Path:
    raw = os.environ.get("CITYWALK_USER_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    shared = os.environ.get("CITYWALK_SHARED_ROUTES_DIR", "").strip()
    if shared:
        return Path(shared).parent / "users"
    return _DEFAULT_DIR


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _index_path(base: Path) -> Path:
    return base / "email_index.json"


def _user_path(base: Path, user_id: str) -> Path:
    return base / f"{user_id}.json"


def _load_index(base: Path) -> Dict[str, str]:
    fp = _index_path(base)
    if not fp.is_file():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_index(base: Path, index: Dict[str, str]) -> None:
    _ensure_dir(base)
    fp = _index_path(base)
    tmp = base / f".idx.{secrets.token_hex(4)}.tmp"
    tmp.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(fp)


def _empty_sync() -> Dict[str, Any]:
    return {
        "updated_at": 0,
        "walked": [],
        "favorite_routes": [],
        "favorite_spots": [],
        "planned_routes": {},
    }


def _read_user_doc(base: Path, user_id: str) -> Optional[Dict[str, Any]]:
    if not _USER_ID_RE.match(user_id):
        return None
    fp = _user_path(base, user_id)
    if not fp.is_file():
        return None
    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_user_doc(base: Path, doc: Dict[str, Any]) -> bool:
    user_id = doc.get("user_id")
    if not user_id or not _USER_ID_RE.match(user_id):
        return False
    _ensure_dir(base)
    fp = _user_path(base, user_id)
    tmp = base / f".{user_id}.{secrets.token_hex(4)}.tmp"
    try:
        tmp.write_text(
            json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(fp)
        return True
    except OSError:
        logging.exception("write user doc failed")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def register_user(
    email: str,
    password: str,
    display_name: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    norm = normalize_email(email)
    if not norm:
        return None, "请输入有效邮箱"
    pwd_hash = hash_password(password)
    if not pwd_hash:
        return None, "密码至少 8 位"

    base = _data_dir()
    _ensure_dir(base)
    index = _load_index(base)
    if norm in index:
        return None, "该邮箱已注册，请直接登录"

    user_id = str(uuid.uuid4())
    now = time.time()
    name = (display_name or "").strip() or norm.split("@")[0][:24]
    doc = {
        "user_id": user_id,
        "email": norm,
        "display_name": name,
        "password_hash": pwd_hash,
        "created_at": now,
        "sync": _empty_sync(),
    }
    if not _write_user_doc(base, doc):
        return None, "注册失败，请稍后再试"
    index[norm] = user_id
    try:
        _save_index(base, index)
    except OSError:
        _user_path(base, user_id).unlink(missing_ok=True)
        return None, "注册失败，请稍后再试"

    return {
        "user_id": user_id,
        "email": norm,
        "display_name": name,
    }, None


def authenticate_user(email: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    norm = normalize_email(email)
    if not norm:
        return None, "邮箱或密码不正确"
    base = _data_dir()
    index = _load_index(base)
    user_id = index.get(norm)
    if not user_id:
        return None, "邮箱或密码不正确"
    doc = _read_user_doc(base, user_id)
    if not doc or not verify_password(doc.get("password_hash") or "", password):
        return None, "邮箱或密码不正确"
    return {
        "user_id": user_id,
        "email": doc.get("email") or norm,
        "display_name": doc.get("display_name") or norm.split("@")[0],
    }, None


def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    doc = _read_user_doc(_data_dir(), user_id)
    if not doc:
        return None
    return {
        "user_id": user_id,
        "email": doc.get("email"),
        "display_name": doc.get("display_name"),
    }


def get_user_footprints(user_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    doc = _read_user_doc(_data_dir(), user_id)
    if not doc:
        return None, "用户不存在"
    sync = doc.get("sync")
    if not isinstance(sync, dict):
        sync = _empty_sync()
    return {
        "v": 1,
        "updated_at": sync.get("updated_at") or 0,
        "walked": sync.get("walked") if isinstance(sync.get("walked"), list) else [],
        "favorite_routes": sync.get("favorite_routes") if isinstance(sync.get("favorite_routes"), list) else [],
        "favorite_spots": sync.get("favorite_spots") if isinstance(sync.get("favorite_spots"), list) else [],
        "planned_routes": sync.get("planned_routes") if isinstance(sync.get("planned_routes"), dict) else {},
    }, None


def _validate_sync_payload(body: Dict[str, Any]) -> Optional[str]:
    if not isinstance(body.get("walked"), list):
        return "walked 须为数组"
    if not isinstance(body.get("favorite_routes"), list):
        return "favorite_routes 须为数组"
    if not isinstance(body.get("favorite_spots"), list):
        return "favorite_spots 须为数组"
    planned = body.get("planned_routes")
    if planned is not None and not isinstance(planned, dict):
        return "planned_routes 须为对象"
    try:
        size = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return "数据无法序列化"
    if size > _MAX_SYNC_BYTES:
        return "同步数据过大"
    return None


def save_user_footprints(user_id: str, body: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    err = _validate_sync_payload(body)
    if err:
        return None, err
    base = _data_dir()
    doc = _read_user_doc(base, user_id)
    if not doc:
        return None, "用户不存在"

    now = time.time()
    sync = {
        "updated_at": now,
        "walked": body.get("walked") or [],
        "favorite_routes": body.get("favorite_routes") or [],
        "favorite_spots": body.get("favorite_spots") or [],
        "planned_routes": body.get("planned_routes") if isinstance(body.get("planned_routes"), dict) else {},
    }
    doc["sync"] = sync
    if not _write_user_doc(base, doc):
        return None, "保存失败，请稍后再试"

    return {
        "v": 1,
        "updated_at": now,
        **{k: sync[k] for k in ("walked", "favorite_routes", "favorite_spots", "planned_routes")},
    }, None
