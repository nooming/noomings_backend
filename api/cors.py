# -*- coding: utf-8 -*-
"""跨域配置（/api/*）。"""
import os

from flask_cors import CORS


def _cors_origins() -> list:
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["*"]


_API_RESOURCE = {
    "origins": _cors_origins(),
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
    "supports_credentials": False,
}


def apply_cors(app):
    CORS(app, resources={r"/api/*": _API_RESOURCE})
