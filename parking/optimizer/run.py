# -*- coding: utf-8 -*-
from .python.run_optimize import run_optimize


def compute_metrics(result):
    breakdown = result.get("vehicle_breakdown") or []
    gbest = result.get("gbest_value")
    n_veh = len(breakdown) or (result.get("scenario") or {}).get("n_veh") or 0
    n_slot = len((result.get("scenario") or {}).get("slots") or [])
    walk_times = [float(it.get("walk_time") or 0) for it in breakdown]
    total_times = [float(it.get("total_time") or 0) for it in breakdown]
    penalties = [float(it.get("penalty") or 0) for it in breakdown]
    mismatch_count = sum(1 for p in penalties if p > 0)
    return {
        "gbest_value": gbest,
        "worst_vehicle_time": max(total_times) if total_times else None,
        "avg_walk_time": (sum(walk_times) / len(walk_times)) if walk_times else None,
        "slot_utilization": (n_veh / n_slot) if n_slot else 0,
        "type_match_rate": 1.0 - (mismatch_count / n_veh) if n_veh else 1.0,
        "mismatch_count": mismatch_count,
    }
