# -*- coding: utf-8 -*-
from flask import Blueprint, jsonify, request

from parking.storage import db

bp = Blueprint("scenarios", __name__)


@bp.route("/scenarios", methods=["GET", "OPTIONS"])
def list_scenarios():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    return jsonify({"success": True, "scenarios": db.list_scenarios()})


@bp.route("/scenarios", methods=["POST"])
def create_scenario():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "未命名方案").strip()
    scenario = payload.get("scenario")
    metrics = payload.get("metrics")
    if not scenario:
        return jsonify({"success": False, "message": "缺少 scenario"}), 400
    row = db.save_scenario(name, scenario, metrics=metrics)
    return jsonify({"success": True, "scenario": row})


@bp.route("/scenarios/<scenario_id>", methods=["GET"])
def get_scenario(scenario_id):
    row = db.get_scenario(scenario_id)
    if not row:
        return jsonify({"success": False, "message": "未找到"}), 404
    return jsonify({"success": True, "scenario": row})


@bp.route("/scenarios/<scenario_id>", methods=["PUT"])
def update_scenario(scenario_id):
    payload = request.get_json(silent=True) or {}
    existing = db.get_scenario(scenario_id)
    if not existing:
        return jsonify({"success": False, "message": "未找到"}), 404
    name = (payload.get("name") or existing["name"]).strip()
    scenario = payload.get("scenario") or existing["scenario"]
    metrics = payload.get("metrics") if "metrics" in payload else existing.get("metrics")
    row = db.save_scenario(name, scenario, metrics=metrics, scenario_id=scenario_id)
    return jsonify({"success": True, "scenario": row})


@bp.route("/scenarios/<scenario_id>", methods=["DELETE"])
def delete_scenario(scenario_id):
    db.delete_scenario(scenario_id)
    return jsonify({"success": True})
