# -*- coding: utf-8 -*-
"""Flask 路由：已规划路线的短链分享（POST 保存 / GET 读取）。"""
import logging

from flask import Blueprint, jsonify, request

from citywalk.core.route_share_store import load_shared_route, save_shared_route

bp = Blueprint("cw_share", __name__)


@bp.route("/routes/share", methods=["POST", "OPTIONS"])
def create_shared_route():
    if request.method == "OPTIONS":
        return jsonify({"success": True})

    try:
        payload = request.get_json(silent=True) or {}
        snapshot = payload.get("snapshot")
        route_id, err = save_shared_route(snapshot)
        if err:
            status = 413 if "过大" in err else 400
            return jsonify({"success": False, "message": err}), status
        return jsonify({"success": True, "id": route_id}), 201
    except Exception:
        logging.exception("create_shared_route")
        return jsonify({
            "success": False,
            "message": "分享暂不可用，请稍后再试",
        }), 500


@bp.route("/routes/share/<route_id>", methods=["GET", "OPTIONS"])
def get_shared_route(route_id: str):
    if request.method == "OPTIONS":
        return jsonify({"success": True})

    try:
        snapshot, err = load_shared_route(route_id)
        if err:
            status = 404 if "不存在" in err or "过期" in err else 400
            return jsonify({"success": False, "message": err}), status
        return jsonify({"success": True, "id": route_id, "snapshot": snapshot}), 200
    except Exception:
        logging.exception("get_shared_route")
        return jsonify({
            "success": False,
            "message": "读取分享失败，请稍后再试",
        }), 500
