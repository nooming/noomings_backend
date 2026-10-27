# -*- coding: utf-8 -*-

import json

from .nav_grid import build_navigation_grid, recommend_nav_step
from .pathfinding import walk_blocking_boxes, walking_plan
from .path_cost import driving_distance_from_entrance
from .road_model import road_from_inner, DEFAULT_ROAD_WIDTH


def vehicle_slot_penalty(s, veh_idx, slot_idx):
    req = (s.get("vehicle_requirements") or [None])[veh_idx] or "normal"
    if req == "normal":
        return 0.0
    slot_type = (s.get("slot_types") or [None])[slot_idx] or "normal"
    if slot_type == req:
        return 0.0
    return float((s.get("soft_constraints") or {}).get("type_mismatch_penalty") or 0)


def _layout_for_precompute_key(s):
    """预计算只依赖场地几何，与 n_veh、逐车目的地等无关。"""
    return {
        "lot": s.get("lot"),
        "slots": s.get("slots"),
        "buildings": s.get("buildings"),
        "entrances": s.get("entrances"),
        "entrance": s.get("entrance"),
        "obstacles": s.get("obstacles"),
        "obstacle": s.get("obstacle"),
        "inner": s.get("inner"),
        "road": s.get("road"),
        "display": s.get("display"),
    }


def _precompute_cache_key(s):
    return json.dumps(_layout_for_precompute_key(s), sort_keys=True, ensure_ascii=False, default=str)


_PRECOMPUTE_CACHE = {}
_PRECOMPUTE_CACHE_MAX = 12


def clear_precompute_cache():
    _PRECOMPUTE_CACHE.clear()


def warm_layout_precompute(scenario, progress_cb=None):
    from .scenario_normalize import normalize_scenario

    s = normalize_scenario(scenario)
    precompute_from_normalized(s, progress_cb=progress_cb)
    return {"success": True}


def precompute_from_normalized(s, progress_cb=None):
    key = _precompute_cache_key(s)
    cached = _PRECOMPUTE_CACHE.get(key)
    if cached is not None:
        if progress_cb:
            progress_cb("precompute", "路径缓存命中", 1.0)
        return cached
    out = _precompute_from_normalized_impl(s, progress_cb=progress_cb)
    if len(_PRECOMPUTE_CACHE) >= _PRECOMPUTE_CACHE_MAX:
        _PRECOMPUTE_CACHE.pop(next(iter(_PRECOMPUTE_CACHE)))
    _PRECOMPUTE_CACHE[key] = out
    return out


def _report(progress_cb, phase, label, pct):
    if progress_cb:
        progress_cb(phase, label, pct)


def _precompute_from_normalized_impl(s, progress_cb=None):
    road = s.get("road") or road_from_inner(s.get("inner"), DEFAULT_ROAD_WIDTH)
    _report(progress_cb, "precompute", "初始化场地", 0.02)
    obstacles = s.get("obstacles")
    lot = s.get("lot") or {"width": 100, "height": 100}
    meters_per_unit = float(s.get("display", {}).get("meters_per_unit") or 0)
    if meters_per_unit <= 0:
        meters_per_unit = 2.0
    slots_pos = [[float(p[0]), float(p[1])] for p in s.get("slots") or []]
    buildings_pos = [[float(p[0]), float(p[1])] for p in s.get("buildings") or []]
    n_slot = len(slots_pos)
    n_b = len(buildings_pos)
    entrances_pos = [[float(p[0]), float(p[1])] for p in s.get("entrances") or []]
    if not n_slot or not n_b:
        return {
            "driveDistByEntrance": [],
            "walkMat": [],
            "boxesByBi": [],
            "navByBi": [],
            "slotsPos": slots_pos,
            "buildingsPos": buildings_pos,
            "entrancesPos": entrances_pos,
            "nSlot": n_slot,
            "nB": n_b,
        }
    _report(progress_cb, "precompute", "驾车距离矩阵", 0.08)
    drive_dist_by_entrance = [
        [driving_distance_from_entrance(slot, road, ent) * meters_per_unit for ent in entrances_pos]
        for slot in slots_pos
    ]
    boxes_by_bi = [walk_blocking_boxes(obstacles, buildings_pos, bi) for bi in range(n_b)]
    nav_by_bi = []
    for bi in range(n_b):
        lw = float(lot.get("width", 100))
        lh = float(lot.get("height", 100))
        x_min = float(lot.get("x_min", 0) or 0)
        y_min = float(lot.get("y_min", 0) or 0)
        step = recommend_nav_step(lw, lh, len(boxes_by_bi[bi]))
        nav_by_bi.append(build_navigation_grid(boxes_by_bi[bi], lw, lh, step, x_min, y_min))
        if n_b:
            _report(progress_cb, "precompute", f"步行导航网格 {bi + 1}/{n_b}", 0.1 + 0.15 * (bi + 1) / n_b)
    walk_mat = [[0.0] * n_b for _ in range(n_slot)]
    walk_total = max(1, n_slot * n_b)
    walk_done = 0
    for si in range(n_slot):
        for bi in range(n_b):
            walk_mat[si][bi] = walking_plan(
                slots_pos[si],
                buildings_pos[bi],
                obstacles,
                buildings_pos,
                bi,
                boxes_by_bi[bi],
                nav_by_bi[bi],
                lot,
            )[0] * meters_per_unit
            walk_done += 1
            if walk_done == 1 or walk_done == walk_total or walk_done % 4 == 0:
                _report(
                    progress_cb,
                    "precompute",
                    f"步行路径 {walk_done}/{walk_total}",
                    0.25 + 0.65 * walk_done / walk_total,
                )
    _report(progress_cb, "precompute", "预计算完成", 0.92)
    return {
        "driveDistByEntrance": drive_dist_by_entrance,
        "walkMat": walk_mat,
        "boxesByBi": boxes_by_bi,
        "navByBi": nav_by_bi,
        "slotsPos": slots_pos,
        "buildingsPos": buildings_pos,
        "entrancesPos": entrances_pos,
        "nSlot": n_slot,
        "nB": n_b,
        "road": road,
    }
