# -*- coding: utf-8 -*-
"""Flask 路由：/plan、/resolve_location。"""
import logging
from flask import Blueprint, jsonify, request

from lib.geocoding import resolve_location_detail
from planning.plan_service import execute_plan_request

bp = Blueprint("cw_plan", __name__)


@bp.route('/resolve_location', methods=['POST', 'OPTIONS'])
def resolve_location_api():
    """解析地址/地标为坐标（geo + place/text），供前端与 Agent 对齐。"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    try:
        payload = request.get_json(silent=True) or {}
        address = (payload.get("address") or "").strip()
        city = (payload.get("city") or "").strip().replace("市", "")

        if not address:
            return jsonify({
                "success": False,
                "message": "请提供 address",
            }), 400

        detail = resolve_location_detail(address, city or None)
        if not detail:
            return jsonify({
                "success": False,
                "message": f"没能定位「{address}」，请写清城市或换种说法。",
            }), 200

        return jsonify({
            "success": True,
            "lng": detail["lng"],
            "lat": detail["lat"],
            "source": detail.get("source", "unknown"),
        }), 200
    except Exception as e:
        logging.exception("resolve_location 异常")
        return jsonify({
            "success": False,
            "message": "地点解析暂时不可用，请稍后再试",
        }), 500


@bp.route('/plan', methods=['POST', 'OPTIONS'])
def plan_route():
    """最短路线 → 沿路采样选 POI → 筛选 → 重规划路线（支持全国城市）。"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict() or request.args.to_dict()

    body, status, _meta = execute_plan_request(data)
    return jsonify(body), status
