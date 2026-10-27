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
    db.update_job(jid, "running", progress={"phase": "queued", "label": "任务启动", "pct": 0})
    try:
        payload = job["payload"]
        schedule = payload.get("schedule")
        kind = job.get("kind") or "simulate"
        from parking.core.simulator.job_progress import make_db_progress_reporter

        progress_cb = make_db_progress_reporter(jid, db)
        if kind == "precompute_warm":
            from parking.core.optimizer.cost_matrix import warm_layout_precompute

            warm_layout_precompute(payload.get("scenario"), progress_cb=progress_cb)
            db.update_job(
                jid,
                "completed",
                result={"success": True, "warmed": True},
                progress={"phase": "done", "label": "预计算就绪", "pct": 1.0},
            )
            return
        if kind == "monte_carlo_rolling":
            from parking.core.simulator.monte_carlo import run_monte_carlo_rolling

            out = run_monte_carlo_rolling(
                payload.get("scenario"),
                schedule=payload.get("schedule"),
                runs=payload.get("runs") or 20,
                base_seed=payload.get("seed", 42),
                include_static=payload.get("include_static", True),
                progress_cb=progress_cb,
            )
            db.update_job(
                jid,
                "completed",
                result=out,
                progress={"phase": "done", "label": "Monte Carlo 完成", "pct": 1.0},
            )
            return
        if kind == "simulate_rolling":
            from parking.core.simulator.rolling import run_rolling_simulation

            out = run_rolling_simulation(
                payload.get("scenario"), schedule=schedule, progress_cb=progress_cb
            )
            db.update_job(
                jid,
                "completed",
                result=out,
                progress={"phase": "done", "label": "仿真完成", "pct": 1.0},
            )
            return
        result = payload.get("result")
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


@bp.route("/simulate-rolling", methods=["POST", "OPTIONS"])
def simulate_rolling():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    payload = request.get_json(silent=True) or {}
    scenario = payload.get("scenario")
    if not scenario:
        return jsonify({"success": False, "message": "缺少 scenario"}), 400
    schedule = payload.get("schedule")
    async_mode = payload.get("async", True)
    if not async_mode:
        from parking.core.simulator.rolling import run_rolling_simulation

        out = run_rolling_simulation(scenario, schedule=schedule)
        return jsonify({"success": True, **out})
    jid = db.create_job("simulate_rolling", {"scenario": scenario, "schedule": schedule})
    threading.Thread(target=_run_job, args=(jid,), daemon=True).start()
    return jsonify({"success": True, "job_id": jid, "status": "pending"})


@bp.route("/precompute-warm", methods=["POST", "OPTIONS"])
def precompute_warm():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    payload = request.get_json(silent=True) or {}
    scenario = payload.get("scenario")
    if not scenario:
        return jsonify({"success": False, "message": "缺少 scenario"}), 400
    async_mode = payload.get("async", True)
    if not async_mode:
        from parking.core.optimizer.cost_matrix import warm_layout_precompute

        warm_layout_precompute(scenario)
        return jsonify({"success": True, "warmed": True})
    jid = db.create_job("precompute_warm", {"scenario": scenario})
    threading.Thread(target=_run_job, args=(jid,), daemon=True).start()
    return jsonify({"success": True, "job_id": jid, "status": "pending"})


@bp.route("/monte-carlo-rolling", methods=["POST", "OPTIONS"])
def monte_carlo_rolling():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    payload = request.get_json(silent=True) or {}
    scenario = payload.get("scenario")
    if not scenario:
        return jsonify({"success": False, "message": "缺少 scenario"}), 400
    schedule = payload.get("schedule")
    runs = payload.get("runs") or 20
    base_seed = payload.get("seed", 42)
    include_static = payload.get("include_static", True)
    async_mode = payload.get("async", True)
    if not async_mode:
        from parking.core.simulator.monte_carlo import run_monte_carlo_rolling

        out = run_monte_carlo_rolling(
            scenario,
            schedule=schedule,
            runs=runs,
            base_seed=base_seed,
            include_static=include_static,
        )
        return jsonify({"success": True, **out})
    jid = db.create_job(
        "monte_carlo_rolling",
        {
            "scenario": scenario,
            "schedule": schedule,
            "runs": runs,
            "seed": base_seed,
            "include_static": include_static,
        },
    )
    threading.Thread(target=_run_job, args=(jid,), daemon=True).start()
    return jsonify({"success": True, "job_id": jid, "status": "pending"})
