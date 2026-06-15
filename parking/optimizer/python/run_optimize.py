# -*- coding: utf-8 -*-
import math

from .cost_matrix import precompute_from_normalized, vehicle_slot_penalty
from .hungarian import hungarian_rect
from .pack_result import pack_result
from .pso import decode_particle, make_rng, gaussian
from .road_model import road_from_inner, DEFAULT_ROAD_WIDTH
from .scenario_normalize import (
    normalize_scenario,
    normalize_vehicle_destinations,
    N_PARTICLES_DEFAULT,
    N_ITER_DEFAULT,
    W_DEFAULT,
    C1_DEFAULT,
    C2_DEFAULT,
    V_MAX_DEFAULT,
)


def run_optimize(scenario, method="exact", seed=None):
    method_raw = str(method or "exact").strip().lower()
    method = "pso" if method_raw == "pso" else "exact"
    s = normalize_scenario(scenario)
    road = s.get("road") or road_from_inner(s.get("inner"), DEFAULT_ROAD_WIDTH)
    obstacles = s.get("obstacles")
    prep = precompute_from_normalized(s)
    n_slot = prep["nSlot"]
    n_b = prep["nB"]
    err = {
        "error": "需要至少一个车位、一栋楼，且车辆数大于 0。",
        "scenario": s,
        "gbest_value": None,
        "history_best": [],
        "assign": [],
        "veh_targets": [],
        "paths": [],
        "road_segments": [],
        "optimizer": method,
    }
    if not n_slot or not n_b or not s.get("n_veh"):
        return err
    n_veh = min(int(s["n_veh"]), n_slot)
    s["n_veh"] = n_veh
    normalize_vehicle_destinations(s)
    veh_targets = s["vehicle_destinations"][:n_veh]
    veh_entrances = s["vehicle_entrances"][:n_veh]
    entrance_mode = "fixed" if s.get("entrance_mode") == "fixed" else "auto"
    entrance_count = len(prep["entrancesPos"]) or 1
    v_car = 10.0
    v_walk = 1.5

    def resolve_drive_for_vehicle(slot_index, veh_idx):
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

    def build_vehicle_breakdown(best_assign):
        best_entrances = []
        items = []
        for i in range(n_veh):
            slot_index = best_assign[i]
            drive = resolve_drive_for_vehicle(slot_index, i)
            walk_time = prep["walkMat"][slot_index][veh_targets[i]] / v_walk
            penalty = vehicle_slot_penalty(s, i, slot_index)
            best_entrances.append(drive["entranceIndex"])
            items.append({
                "vehicle_index": i,
                "slot_index": slot_index,
                "destination_index": veh_targets[i],
                "entrance_index": drive["entranceIndex"],
                "drive_time": drive["driveTime"],
                "walk_time": walk_time,
                "penalty": penalty,
                "total_time": drive["driveTime"] + walk_time + penalty,
            })
        return {"bestEntrances": best_entrances, "items": items}

    def run_exact_method():
        cost = []
        for i in range(n_veh):
            row = []
            for j in range(n_slot):
                drive = resolve_drive_for_vehicle(j, i)["driveTime"]
                walk = prep["walkMat"][j][veh_targets[i]] / v_walk
                penalty = vehicle_slot_penalty(s, i, j)
                row.append(drive + walk + penalty)
            cost.append(row)
        best_assign = hungarian_rect(cost)
        gbest_value = sum(cost[i][best_assign[i]] for i in range(n_veh))
        breakdown = build_vehicle_breakdown(best_assign)
        return pack_result(s, {
            "gbestValue": gbest_value,
            "historyBest": [gbest_value],
            "bestAssign": best_assign,
            "bestEntrances": breakdown["bestEntrances"],
            "vehicleBreakdown": breakdown["items"],
            "slotsPos": prep["slotsPos"],
            "buildingsPos": prep["buildingsPos"],
            "obstacles": obstacles,
            "vehTargets": veh_targets,
            "boxesByBi": prep["boxesByBi"],
            "navByBi": prep["navByBi"],
            "lot": s["lot"],
            "road": road,
            "optimizer": "exact",
        })

    def run_pso_method():
        rng = make_rng(seed)
        pso = s.get("pso") or {}
        n_particles = max(2, int(pso.get("n_particles") or 0) or N_PARTICLES_DEFAULT)
        n_iter = max(1, int(pso.get("n_iter") or 0) or N_ITER_DEFAULT)
        w_raw = float(pso.get("w", W_DEFAULT) if pso.get("w") is not None else W_DEFAULT)
        w_max = w_raw if w_raw > 0.5 else 0.9
        w_min = 0.4
        c1 = float(pso.get("c1", C1_DEFAULT) if pso.get("c1") is not None else C1_DEFAULT)
        c2 = float(pso.get("c2", C2_DEFAULT) if pso.get("c2") is not None else C2_DEFAULT)
        v_max = float(pso.get("v_max", V_MAX_DEFAULT) if pso.get("v_max") is not None else V_MAX_DEFAULT)
        early_stop_patience = max(80, round(n_iter * 0.2))

        def objective(position):
            assign = decode_particle(position, n_veh, n_slot)
            drive_total = 0.0
            walk_total = 0.0
            for i in range(n_veh):
                slot_index = assign[i]
                drive_total += resolve_drive_for_vehicle(slot_index, i)["driveTime"]
                walk_total += prep["walkMat"][slot_index][veh_targets[i]] / v_walk
                walk_total += vehicle_slot_penalty(s, i, slot_index)
            return drive_total + walk_total

        positions = [[rng() for _ in range(n_veh)] for _ in range(n_particles)]
        velocities = [[gaussian(rng) * 0.1 for _ in range(n_veh)] for _ in range(n_particles)]
        pbest_positions = [p[:] for p in positions]
        pbest_values = [objective(p) for p in positions]
        gbest_idx = 0
        for i in range(1, n_particles):
            if pbest_values[i] < pbest_values[gbest_idx]:
                gbest_idx = i
        gbest_position = pbest_positions[gbest_idx][:]
        gbest_value = pbest_values[gbest_idx]
        history_best = [gbest_value]
        no_improv_count = 0

        for it in range(n_iter):
            w = w_max - (w_max - w_min) * (it / (n_iter - 1)) if n_iter > 1 else w_max
            for i in range(n_particles):
                for d in range(n_veh):
                    r1 = rng()
                    r2 = rng()
                    velocities[i][d] = (
                        w * velocities[i][d]
                        + c1 * r1 * (pbest_positions[i][d] - positions[i][d])
                        + c2 * r2 * (gbest_position[d] - positions[i][d])
                    )
                    velocities[i][d] = max(-v_max, min(v_max, velocities[i][d]))
                    positions[i][d] = max(0, min(1, positions[i][d] + velocities[i][d]))
                val = objective(positions[i])
                if val < pbest_values[i]:
                    pbest_values[i] = val
                    pbest_positions[i] = positions[i][:]
            gbest_idx = 0
            for i in range(1, n_particles):
                if pbest_values[i] < pbest_values[gbest_idx]:
                    gbest_idx = i
            if pbest_values[gbest_idx] < gbest_value:
                gbest_value = pbest_values[gbest_idx]
                gbest_position = pbest_positions[gbest_idx][:]
                no_improv_count = 0
            else:
                no_improv_count += 1
                if no_improv_count >= early_stop_patience:
                    break
            history_best.append(gbest_value)

        best_assign = decode_particle(gbest_position, n_veh, n_slot)
        breakdown = build_vehicle_breakdown(best_assign)
        return pack_result(s, {
            "gbestValue": gbest_value,
            "historyBest": history_best,
            "bestAssign": best_assign,
            "bestEntrances": breakdown["bestEntrances"],
            "vehicleBreakdown": breakdown["items"],
            "slotsPos": prep["slotsPos"],
            "buildingsPos": prep["buildingsPos"],
            "obstacles": obstacles,
            "vehTargets": veh_targets,
            "boxesByBi": prep["boxesByBi"],
            "navByBi": prep["navByBi"],
            "lot": s["lot"],
            "road": road,
            "optimizer": "pso",
        })

    return run_pso_method() if method == "pso" else run_exact_method()
