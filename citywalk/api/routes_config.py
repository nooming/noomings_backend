# -*- coding: utf-8 -*-
"""Citywalk 前端公共配置 API（高德 JS Key 注入）。"""
import os

from flask import Blueprint, jsonify, request

bp = Blueprint("config", __name__)


@bp.route("/config/public", methods=["GET", "OPTIONS"])
def config_public():
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    return jsonify({
        "success": True,
        "amap_js_key": os.environ.get("AMAP_JS_KEY", "").strip(),
        "amap_js_security_code": os.environ.get("AMAP_JS_SECURITY_CODE", "").strip(),
    })
