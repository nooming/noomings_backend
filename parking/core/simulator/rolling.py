# -*- coding: utf-8 -*-
"""
在线滚动分配：车辆按到达顺序、仅依据已到达信息与当前空车位分配（不预知未来到达）。
"""
import copy
import math

from parking.core.optimizer.cost_matrix import precompute_from_normalized, vehicle_slot_penalty
from parking.core.optimizer.pack_result import pack_result
from parking.core.optimizer.run_optimize import run_optimize
from parking.core.optimizer.scenario_normalize import (
    normalize_scenario,
    normalize_slot_and_vehicle_types,
    normalize_vehicle_destinations,
    normalize_vehicle_entrances,
)
from parking.core.simulator.engine import run_simulation
from parking.core.simulator.entrance_schedule import schedule_drive_times
from parking.core.simulator.objective_metrics import (
    composite_cost,
    compute_objective_metrics,
    entrance_marginal_penalty,
    parse_objective_weights,
)
from parking.core.simulator.schedule_parse import build_arrivals, sim_options

from parking.core.optimizer.road_model import road_from_inner, DEFAULT_ROAD_WIDTH


def _dwell_overbook_vehicle_count(schedule, n_slot, raw_n_veh):
    sched = dict(schedule or {})
    opts = sim_options(sched)
    if float(opts.get("dwell_s") or 0) <= 0 or not n_slot:
        return None
    mode = str(sched.get("mode") or "uniform").strip().lower()
    arr = list(sched.get("arrivals_sec") or sched.get("arrivals") or [])
    want = int(sched.get("count") or raw_n_veh or len(arr) or 0)
    if mode == "explicit" and arr:
        want = max(want, len(arr))
    return want if want > n_slot else None


def _build_cost_context(scenario, schedule=None, progress_cb=None):
    raw_n = int((scenario or {}).get("n_veh") or 0)
    s = normalize_scenario(copy.deepcopy(scenario))
    road = s.get("road") or road_from_inner(s.get("inner"), DEFAULT_ROAD_WIDTH)
    prep = precompute_from_normalized(s, progress_cb=progress_cb)
    n_slot = prep["nSlot"]
    n_b = prep["nB"]
    overbook = _dwell_overbook_vehicle_count(schedule, n_slot, raw_n)
    if overbook and overbook > int(s.get("n_veh") or 0):
        s["n_veh"] = overbook
        normalize_vehicle_destinations(s)
        normalize_vehicle_entrances(s)
        normalize_slot_and_vehicle_types(s)
    n_veh = int(s.get("n_veh") or 0)
    if not n_veh or not n_slot or not n_b:
        return None
    s["n_veh"] = n_veh
    veh_targets = s["vehicle_destinations"][:n_veh]
    veh_entrances = s["vehicle_entrances"][:n_veh]
    entrance_mode = "fixed" if s.get("entrance_mode") == "fixed" else "auto"
    entrance_count = len(prep["entrancesPos"]) or 1
    v_car = 10.0
    v_walk = 1.5

    def resolve_drive(slot_index, veh_idx):
        if entrance_mode == "fixed":
            ei_raw = float(veh_entrances[veh_idx])
            ei = max(0, min(entrance_count - 1, int(ei_raw))) if math.isfinite(ei_raw) else 0
            return {
                "driveTime": prep["driveDistByEntrance"][slot_index][ei] / v_car,
                "entranceIndex": ei,
            }
        best_ei = 0
        best_drive = prep["driveDistByEntrance"][slot_index][0] / v_car
        for ei in range(1, entrance_count):
            cur = prep["driveDistByEntrance"][slot_index][ei] / v_car
            if cur < best_drive:
                best_drive = cur
                best_ei = ei
        return {"driveTime": best_drive, "entranceIndex": best_ei}

    cost = []
    for i in range(n_veh):
        row = []
        for j in range(n_slot):
            drive = resolve_drive(j, i)["driveTime"]
            walk = prep["walkMat"][j][veh_targets[i]] / v_walk
            penalty = vehicle_slot_penalty(s, i, j)
            row.append(drive + walk + penalty)
        cost.append(row)
    return {
        "scenario": s,
        "road": road,
        "prep": prep,
        "n_veh": n_veh,
        "n_slot": n_slot,
        "veh_targets": veh_targets,
        "resolve_drive": resolve_drive,
        "cost": cost,
        "v_walk": v_walk,
    }


def _apply_prefix_assignments(n_veh, n_slot, prefix, assign, free_slots):
    """schedule.prefix_assign: 固定前若干辆车的车位（逐车增量调试）。"""
    if not prefix:
        return None
    if not isinstance(prefix, (list, tuple)):
        return "prefix_assign 格式无效"
    if len(prefix) > n_veh:
        return "prefix_assign 长度超过车辆数"
    used = set()
    for vi, slot in enumerate(prefix):
        if slot is None:
            continue
        try:
            sj = int(slot)
        except (TypeError, ValueError):
            return f"prefix_assign[{vi}] 无效"
        if sj < 0 or sj >= n_slot:
            return f"prefix_assign[{vi}] 车位索引越界"
        if sj in used:
            return "prefix_assign 车位重复"
        used.add(sj)
        assign[vi] = sj
        free_slots.discard(sj)
    return None


def run_rolling_simulation(scenario, schedule=None, progress_cb=None):
    """
    按到达顺序 FIFO + 每车在当前空车位中取代价最小者。
    返回与 optimize 类似的 result 结构 + timeline + rolling 元数据。
    schedule.prefix_assign: 可选，固定前若干辆已分配车位。
    """
    if progress_cb:
        progress_cb("rolling", "准备滚动仿真", 0.01)
    sched = dict(schedule or {})
    ctx = _build_cost_context(scenario, schedule=sched, progress_cb=progress_cb)
    if not ctx:
        return {
            "success": False,
            "message": "场景无效",
            "timeline": {"frames": [], "stats": {}, "duration": 0},
        }
    s = ctx["scenario"]
    n_veh = ctx["n_veh"]
    n_slot = ctx["n_slot"]
    cost = ctx["cost"]
    arrivals = build_arrivals(n_veh, sched)
    opts = sim_options(sched)
    cap = opts["entrance_capacity"]
    weights = parse_objective_weights(sched, s)
    prep = ctx["prep"]
    entrance_count = len(prep["entrancesPos"]) or 1
    entrance_counts = [0] * entrance_count

    dwell_s = float(opts.get("dwell_s") or 0)
    free_slots = set(range(n_slot))
    slot_free_at = [0.0] * n_slot
    assign = [-1] * n_veh

    def _slot_release_time(veh_idx, slot_index):
        drive_t = ctx["resolve_drive"](slot_index, veh_idx)["driveTime"]
        walk_t = ctx["prep"]["walkMat"][slot_index][ctx["veh_targets"][veh_idx]] / ctx["v_walk"]
        return arrivals[veh_idx] + drive_t + walk_t + dwell_s

    prefix_err = _apply_prefix_assignments(n_veh, n_slot, sched.get("prefix_assign"), assign, free_slots)
    if prefix_err:
        return {
            "success": False,
            "message": prefix_err,
            "timeline": {"frames": [], "stats": {}, "duration": 0},
        }
    if dwell_s > 0:
        for vi in range(n_veh):
            if assign[vi] >= 0:
                sj = assign[vi]
                slot_free_at[sj] = max(slot_free_at[sj], _slot_release_time(vi, sj))
    for vi in range(n_veh):
        if assign[vi] >= 0:
            ei = ctx["resolve_drive"](assign[vi], vi)["entranceIndex"]
            if 0 <= ei < entrance_count:
                entrance_counts[ei] += 1
    order = sorted(range(n_veh), key=lambda i: (arrivals[i], i))
    assignment_log = []

    if progress_cb:
        progress_cb("rolling", "滚动分配车位", 0.93)

    for vi in order:
        if assign[vi] >= 0:
            sj = assign[vi]
            assignment_log.append(
                {
                    "vehicle_index": vi,
                    "arrival": arrivals[vi],
                    "slot_index": sj,
                    "status": "prefixed",
                    "marginal_cost": cost[vi][sj],
                }
            )
            continue
        assigned_so_far = sum(entrance_counts)
        t_arr = arrivals[vi]
        if dwell_s > 0:
            candidate_slots = [j for j in range(n_slot) if slot_free_at[j] <= t_arr + 1e-6]
        else:
            candidate_slots = list(free_slots)
        if not candidate_slots:
            assignment_log.append(
                {"vehicle_index": vi, "arrival": arrivals[vi], "status": "rejected_no_slot"}
            )
            continue
        best_j = None
        best_c = float("inf")
        for j in candidate_slots:
            c = cost[vi][j]
            drive_meta = ctx["resolve_drive"](j, vi)
            ei = drive_meta["entranceIndex"]
            c += weights["entrance_balance"] * entrance_marginal_penalty(
                ei, entrance_counts, entrance_count, assigned_so_far
            )
            if c < best_c:
                best_c = c
                best_j = j
        if dwell_s > 0:
            slot_free_at[best_j] = _slot_release_time(vi, best_j)
        else:
            free_slots.remove(best_j)
        assign[vi] = best_j
        ei_assigned = ctx["resolve_drive"](best_j, vi)["entranceIndex"]
        if 0 <= ei_assigned < entrance_count:
            entrance_counts[ei_assigned] += 1
        assignment_log.append(
            {
                "vehicle_index": vi,
                "arrival": arrivals[vi],
                "slot_index": best_j,
                "status": "assigned",
                "marginal_cost": best_c,
            }
        )

    if any(a < 0 for a in assign):
        return {
            "success": False,
            "message": "车位不足，无法为全部到达车辆分配",
            "assignment_log": assignment_log,
            "timeline": {"frames": [], "stats": {}, "duration": 0},
        }

    breakdown_items = []
    best_entrances = []
    gbest = 0.0
    for i in range(n_veh):
        j = assign[i]
        drive = ctx["resolve_drive"](j, i)
        walk_t = ctx["prep"]["walkMat"][j][ctx["veh_targets"][i]] / ctx["v_walk"]
        pen = vehicle_slot_penalty(s, i, j)
        gbest += drive["driveTime"] + walk_t + pen
        best_entrances.append(drive["entranceIndex"])
        breakdown_items.append(
            {
                "vehicle_index": i,
                "slot_index": j,
                "destination_index": ctx["veh_targets"][i],
                "entrance_index": drive["entranceIndex"],
                "drive_time": drive["driveTime"],
                "walk_time": walk_t,
                "penalty": pen,
                "total_time": drive["driveTime"] + walk_t + pen,
            }
        )

    prep = ctx["prep"]
    result = pack_result(
        s,
        {
            "gbestValue": gbest,
            "historyBest": [gbest],
            "bestAssign": assign,
            "bestEntrances": best_entrances,
            "vehicleBreakdown": breakdown_items,
            "slotsPos": prep["slotsPos"],
            "buildingsPos": prep["buildingsPos"],
            "obstacles": s.get("obstacles"),
            "vehTargets": ctx["veh_targets"],
            "boxesByBi": prep["boxesByBi"],
            "navByBi": prep["navByBi"],
            "lot": s["lot"],
            "road": ctx["road"],
            "optimizer": "rolling",
        },
    )

    sched.setdefault("realistic", True)
    if not sched.get("mode"):
        sched["mode"] = "uniform"
    if progress_cb:
        progress_cb("timeline", "生成运营回放", 0.96)
    timeline = run_simulation(result, schedule=sched)
    if progress_cb:
        progress_cb("timeline", "仿真完成", 1.0)

    obj_metrics = compute_objective_metrics(breakdown_items)
    obj_weights = weights

    static_ref = None
    if sched.get("include_static_reference"):
        try:
            static_ref = run_optimize(s, method="exact")
        except Exception:
            static_ref = None

    return {
        "success": True,
        "result": result,
        "timeline": timeline,
        "assignment_log": assignment_log,
        "policy": "rolling_fifo_greedy",
        "schedule_realized": {
            "mode": sched.get("mode"),
            "arrivals_sec": arrivals,
            "seed": sched.get("seed"),
        },
        "objective_metrics": obj_metrics,
        "objective_weights": obj_weights,
        "composite_cost": composite_cost(obj_metrics, obj_weights),
        "static_reference_value": (
            float(
                static_ref.get("composite_cost")
                if static_ref.get("composite_cost") is not None
                else static_ref.get("gbest_value")
            )
            if static_ref
            and (
                static_ref.get("composite_cost") is not None
                or static_ref.get("gbest_value") is not None
            )
            else None
        ),
        "rolling_total_cost": gbest,
    }
