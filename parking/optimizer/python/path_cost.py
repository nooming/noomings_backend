# -*- coding: utf-8 -*-

from .geometry import project_point_to_road, road_distance_between_points
from .road_model import road_from_inner, DEFAULT_ROAD_WIDTH


def arc_length_from_blccw(px, py, road_or_inner):
    road = road_or_inner if road_or_inner.get("centerline") else road_from_inner(road_or_inner or {}, DEFAULT_ROAD_WIDTH)
    proj = project_point_to_road(px, py, {"road": road})
    return float(proj.get("along") or 0) if proj else 0.0


def perimeter_distance_between(ax, ay, bx, by, road_or_inner):
    road = road_or_inner if road_or_inner.get("centerline") else road_from_inner(road_or_inner or {}, DEFAULT_ROAD_WIDTH)
    return road_distance_between_points([ax, ay], [bx, by], {"road": road})


def driving_distance_from_entrance(slot_xy, road_or_inner, entrance):
    road = road_or_inner if road_or_inner.get("centerline") else road_from_inner(road_or_inner or {}, DEFAULT_ROAD_WIDTH)
    ex = float(entrance[0])
    ey = float(entrance[1])
    sx = float(slot_xy[0])
    sy = float(slot_xy[1])
    p_slot = project_point_to_road(sx, sy, {"road": road})
    if not p_slot:
        return 0.0
    on_road_dist = perimeter_distance_between(ex, ey, p_slot["point"][0], p_slot["point"][1], road)
    return on_road_dist + p_slot["distance"]
