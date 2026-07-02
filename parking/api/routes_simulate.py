# -*- coding: utf-8 -*-
import threading

from flask import Blueprint, jsonify, request

from parking.core.simulator.engine import run_simulation
from parking.core.storage import db

bp = Blueprint("simulate", __name__)


def _run_job(jid):
    job = db.get_job(jid)
    if not job:
        return
    db.update_job(jid, "running")
    try:
        payload = job["payload"]
        result = payload.get("result")
        schedule = payload.get("schedule")
        timeline = run_simulation(result, schedule=schedule)
        db.update_job(jid, "completed", result=timeline)
    except Exception as e:
        db.update_job(jid, "failed", error=str(e))


@bp.route("/simulate", methods=["POST", "OPTIONS"])
def simulate():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    payload = request.get_json(silent=True) or {}
    result = payload.get("result")
    if not result:
        return jsonify({"success": False, "message": "缺少 result（需先优化）"}), 400
    async_mode = payload.get("async", True)
    schedule = payload.get("schedule")
    if not async_mode:
        timeline = run_simulation(result, schedule=schedule)
        return jsonify({"success": True, "timeline": timeline})
    jid = db.create_job("simulate", {"result": result, "schedule": schedule})
    threading.Thread(target=_run_job, args=(jid,), daemon=True).start()
    return jsonify({"success": True, "job_id": jid, "status": "pending"})


@bp.route("/jobs/<job_id>", methods=["GET", "OPTIONS"])
def job_status(job_id):
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    job = db.get_job(job_id)
    if not job:
        return jsonify({"success": False, "message": "未找到"}), 404
    return jsonify({"success": True, "job": job})
