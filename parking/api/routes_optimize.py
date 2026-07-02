# -*- coding: utf-8 -*-
from flask import Blueprint, jsonify, request

from parking.core.optimizer.run import compute_metrics, run_optimize
from parking.core.planner.auto_slots import suggest_plans, suggest_slots
from parking.core.storage import db

bp = Blueprint("optimize", __name__)


@bp.route("/optimize", methods=["POST", "OPTIONS"])
def optimize():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    payload = request.get_json(silent=True) or {}
    scenario = payload.get("scenario")
    if not scenario:
        return jsonify({"success": False, "message": "缺少 scenario"}), 400
    method = payload.get("method") or "exact"
    seed = payload.get("seed")
    try:
        result = run_optimize(scenario, method=method, seed=seed)
        metrics = compute_metrics(result)
        return jsonify({"success": True, "result": result, "metrics": metrics})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/plan/auto-slots", methods=["POST", "OPTIONS"])
def auto_slots():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    payload = request.get_json(silent=True) or {}
    scenario = payload.get("scenario") or {}
    count = payload.get("count")
    slots, meta = suggest_slots(scenario, count=count)
    return jsonify({"success": True, "slots": slots, "meta": meta})


@bp.route("/plan/suggest", methods=["POST", "OPTIONS"])
def plan_suggest():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    payload = request.get_json(silent=True) or {}
    scenario = payload.get("scenario")
    if not scenario:
        return jsonify({"success": False, "message": "缺少 scenario"}), 400

    def _opt(s, m):
        return run_optimize(s, method=m)

    plans = suggest_plans(scenario, _opt)
    for p in plans:
        if p.get("result"):
            p["metrics"] = compute_metrics(p["result"])
    return jsonify({"success": True, "plans": plans})


@bp.route("/compare", methods=["POST", "OPTIONS"])
def compare_scenarios():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    payload = request.get_json(silent=True) or {}
    ids = payload.get("scenario_ids") or []
    if not ids:
        return jsonify({"success": False, "message": "缺少 scenario_ids"}), 400
    rows = []
    for sid in ids[:4]:
        row = db.get_scenario(sid)
        if row:
            rows.append(row)
    return jsonify({"success": True, "scenarios": rows})
