# -*- coding: utf-8 -*-

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


def precompute_from_normalized(s):
    road = s.get("road") or road_from_inner(s.get("inner"), DEFAULT_ROAD_WIDTH)
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
    walk_mat = [[0.0] * n_b for _ in range(n_slot)]
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
