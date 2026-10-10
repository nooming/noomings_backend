# -*- coding: utf-8 -*-
"""Flask：Citywalk 注册 / 登录 / 足迹云同步。"""
import logging

from flask import Blueprint, jsonify, request

from citywalk.core.user_auth import issue_token, user_id_from_authorization_header
from citywalk.core.user_store import (
    authenticate_user,
    get_user_footprints,
    get_user_profile,
    register_user,
    save_user_footprints,
)

bp = Blueprint("cw_auth", __name__)


def _current_user_id():
    return user_id_from_authorization_header(request.headers.get("Authorization"))


@bp.route("/auth/register", methods=["POST", "OPTIONS"])
def auth_register():
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    try:
        payload = request.get_json(silent=True) or {}
        profile, err = register_user(
            payload.get("email") or "",
            payload.get("password") or "",
            payload.get("display_name"),
        )
        if err:
            return jsonify({"success": False, "message": err}), 400
        token = issue_token(profile["user_id"])
        return jsonify({
            "success": True,
            "token": token,
            "user": profile,
        }), 201
    except Exception:
        logging.exception("auth_register")
        return jsonify({"success": False, "message": "注册暂不可用"}), 500


@bp.route("/auth/login", methods=["POST", "OPTIONS"])
def auth_login():
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    try:
        payload = request.get_json(silent=True) or {}
        profile, err = authenticate_user(
            payload.get("email") or "",
            payload.get("password") or "",
        )
        if err:
            return jsonify({"success": False, "message": err}), 401
        token = issue_token(profile["user_id"])
        return jsonify({
            "success": True,
            "token": token,
            "user": profile,
        }), 200
    except Exception:
        logging.exception("auth_login")
        return jsonify({"success": False, "message": "登录暂不可用"}), 500


@bp.route("/auth/me", methods=["GET", "OPTIONS"])
def auth_me():
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    uid = _current_user_id()
    if not uid:
        return jsonify({"success": False, "message": "未登录"}), 401
    profile = get_user_profile(uid)
    if not profile:
        return jsonify({"success": False, "message": "用户不存在"}), 404
    return jsonify({"success": True, "user": profile}), 200


@bp.route("/user/footprints", methods=["GET", "PUT", "OPTIONS"])
def user_footprints():
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    uid = _current_user_id()
    if not uid:
        return jsonify({"success": False, "message": "未登录"}), 401

    if request.method == "GET":
        data, err = get_user_footprints(uid)
        if err:
            return jsonify({"success": False, "message": err}), 404
        return jsonify({"success": True, "footprints": data}), 200

    try:
        body = request.get_json(silent=True) or {}
        data, err = save_user_footprints(uid, body)
        if err:
            status = 413 if "过大" in err else 400
            return jsonify({"success": False, "message": err}), status
        return jsonify({"success": True, "footprints": data}), 200
    except Exception:
        logging.exception("user_footprints PUT")
        return jsonify({"success": False, "message": "保存失败"}), 500
