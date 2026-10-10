# -*- coding: utf-8 -*-
"""Citywalk 用户登录：密码哈希与 Bearer Token（HMAC）。"""

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

from werkzeug.security import check_password_hash, generate_password_hash

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TOKEN_TTL_SEC = 30 * 86400


def _auth_secret() -> bytes:
    raw = os.environ.get("CITYWALK_AUTH_SECRET", "").strip()
    if not raw:
        raw = os.environ.get("AMAP_KEY", "").strip() or "citywalk-dev-insecure-change-me"
    return raw.encode("utf-8")


def normalize_email(email: str) -> Optional[str]:
    e = (email or "").strip().lower()
    if not e or not _EMAIL_RE.match(e):
        return None
    return e


def hash_password(password: str) -> Optional[str]:
    pwd = password or ""
    if len(pwd) < 8:
        return None
    return generate_password_hash(pwd, method="scrypt")


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or not password:
        return False
    try:
        return check_password_hash(password_hash, password)
    except ValueError:
        return False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + _TOKEN_TTL_SEC}
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_auth_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url(sig)}"


def verify_token(token: str) -> Optional[str]:
    if not token or "." not in token:
        return None
    body, sig_part = token.rsplit(".", 1)
    try:
        expected = hmac.new(_auth_secret(), body.encode("ascii"), hashlib.sha256).digest()
        got = _b64url_decode(sig_part)
        if not hmac.compare_digest(expected, got):
            return None
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = int(payload.get("exp") or 0)
    if exp < time.time():
        return None
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        return None
    return sub


def user_id_from_authorization_header(header: Optional[str]) -> Optional[str]:
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return verify_token(parts[1].strip())
