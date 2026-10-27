# -*- coding: utf-8 -*-
"""多目标指标：总时间、楼间公平（步行极差）、入口负载方差。"""
import math


def parse_objective_weights(schedule=None, scenario=None):
    sched = schedule or {}
    raw = sched.get("objective_weights")
    if raw is None and scenario:
        raw = (scenario.get("soft_constraints") or {}).get("objective_weights")
    raw = raw or {}
    w_ent = float(raw.get("entrance_balance") or 0)
    w_fair = float(raw.get("fairness_range") or 0)
    return {
        "entrance_balance": max(0.0, w_ent),
        "fairness_range": max(0.0, w_fair),
    }


def entrance_marginal_penalty(entrance_index, entrance_counts, entrance_count, assigned_so_far):
    if entrance_count <= 1 or assigned_so_far <= 0:
        return 0.0
    target = (assigned_so_far + 1) / entrance_count
    projected = entrance_counts[entrance_index] + 1
    return max(0.0, projected - target) ** 2


def compute_objective_metrics(breakdown_items, veh_targets=None):
    """breakdown: vehicle_breakdown 列表，含 walk_time, entrance_index, destination_index。"""
    if not breakdown_items:
        return {
            "total_time": 0.0,
            "fairness_walk_range": 0.0,
            "entrance_load_variance": 0.0,
        }
    total = sum(float(b.get("total_time") or 0) for b in breakdown_items)
    by_building = {}
    for b in breakdown_items:
        bi = int(b.get("destination_index") if b.get("destination_index") is not None else 0)
        wt = float(b.get("walk_time") or 0)
        by_building.setdefault(bi, []).append(wt)
    building_avgs = [sum(v) / len(v) for v in by_building.values() if v]
    fairness = max(building_avgs) - min(building_avgs) if len(building_avgs) >= 2 else 0.0
    ent_counts = {}
    for b in breakdown_items:
        ei = int(b.get("entrance_index") or 0)
        ent_counts[ei] = ent_counts.get(ei, 0) + 1
    counts = list(ent_counts.values())
    if len(counts) <= 1:
        ent_var = 0.0
    else:
        mean_c = sum(counts) / len(counts)
        ent_var = sum((c - mean_c) ** 2 for c in counts) / len(counts)
    return {
        "total_time": total,
        "fairness_walk_range": fairness,
        "entrance_load_variance": ent_var,
    }


def composite_cost(metrics, weights):
    w = parse_objective_weights({"objective_weights": weights}) if isinstance(weights, dict) else weights
    return (
        metrics["total_time"]
        + w["fairness_range"] * metrics["fairness_walk_range"]
        + w["entrance_balance"] * metrics["entrance_load_variance"] * 10.0
    )
