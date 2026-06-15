# -*- coding: utf-8 -*-
import math

from .geometry import closest_point_on_segment, build_road_segments, project_point_to_road
from .road_model import DEFAULT_ROAD_WIDTH, road_from_inner

SLOT_SNAP_MARGIN = 0.45
SLOT_HALF_BERTH_W = 1.3


def normalize_angle(theta):
    t = float(theta)
    if not math.isfinite(t):
        return 0.0
    out = t
    while out <= -math.pi:
        out += math.pi * 2
    while out > math.pi:
        out -= math.pi * 2
    return out


def parse_lot_extents(lot_or_w, lot_h=None):
    if isinstance(lot_or_w, dict):
        x_min = float(lot_or_w.get("x_min", 0) or 0)
        y_min = float(lot_or_w.get("y_min", 0) or 0)
        w = float(lot_or_w.get("width", 100) or 100)
        h = float(lot_or_w.get("height", 100) or 100)
        return x_min, y_min, x_min + w, y_min + h, w, h
    w = float(lot_or_w or 100)
    h = float(lot_h or 100)
    return 0.0, 0.0, w, h, w, h


def _clamp(v, mn, mx):
    return max(mn, min(mx, v))


def snap_point_to_inner_perimeter(x, y, road_or_inner, lot_or_w, lot_h=None):
    x_min, y_min, x_max, y_max, _, _ = parse_lot_extents(lot_or_w, lot_h)
    road = road_or_inner if road_or_inner.get("centerline") else road_from_inner(road_or_inner or {}, DEFAULT_ROAD_WIDTH)
    proj = project_point_to_road(float(x), float(y), {"road": road})
    qx = proj["point"][0] if proj else float(x)
    qy = proj["point"][1] if proj else float(y)
    return [_clamp(qx, x_min, x_max), _clamp(qy, y_min, y_max)]


def build_road_guide_segments(road, lot_or_w, lot_h=None, margin=SLOT_SNAP_MARGIN):
    x_min, y_min, x_max, y_max, _, _ = parse_lot_extents(lot_or_w, lot_h)
    segs = build_road_segments({"road": road})
    strips = []
    offset = max(0.8, float(road.get("width", DEFAULT_ROAD_WIDTH) or DEFAULT_ROAD_WIDTH) / 2 + SLOT_HALF_BERTH_W + margin)
    x_lo = x_min + SLOT_HALF_BERTH_W + 0.05
    x_hi = x_max - SLOT_HALF_BERTH_W - 0.05
    y_lo = y_min + SLOT_HALF_BERTH_W + 0.05
    y_hi = y_max - SLOT_HALF_BERTH_W - 0.05
    for i, (a, b) in enumerate(segs):
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx = -dy / length
        ny = dx / length
        side_defs = [
            {"sign": 1, "id": f"left-{i}"},
            {"sign": -1, "id": f"right-{i}"},
        ]
        for side in side_defs:
            x1 = a[0] + nx * offset * side["sign"]
            y1 = a[1] + ny * offset * side["sign"]
            x2 = b[0] + nx * offset * side["sign"]
            y2 = b[1] + ny * offset * side["sign"]
            strips.append({
                "id": side["id"],
                "x1": _clamp(x1, x_lo, x_hi),
                "y1": _clamp(y1, y_lo, y_hi),
                "x2": _clamp(x2, x_lo, x_hi),
                "y2": _clamp(y2, y_lo, y_hi),
                "tx": dx / length,
                "ty": dy / length,
                "theta": math.atan2(dy, dx),
                "len": math.hypot(x2 - x1, y2 - y1),
            })
    return strips


def snap_slot_to_road(x, y, road_or_inner, lot_or_w, lot_h=None, margin=SLOT_SNAP_MARGIN):
    x_min, y_min, x_max, y_max, _, _ = parse_lot_extents(lot_or_w, lot_h)
    road = road_or_inner if road_or_inner.get("centerline") else road_from_inner(road_or_inner or {}, DEFAULT_ROAD_WIDTH)
    strips = build_road_guide_segments(road, lot_or_w, lot_h, margin)
    if not strips:
        return [_clamp(x, x_min, x_max), _clamp(y, y_min, y_max), 0.0]
    best_x = x
    best_y = y
    best_theta = 0.0
    best_d = 1e30
    for s in strips:
        qx, qy = closest_point_on_segment(x, y, s["x1"], s["y1"], s["x2"], s["y2"])
        d = (x - qx) ** 2 + (y - qy) ** 2
        if d < best_d:
            best_d = d
            best_x = qx
            best_y = qy
            best_theta = s["theta"]
    return [
        _clamp(best_x, x_min, x_max),
        _clamp(best_y, y_min, y_max),
        normalize_angle(best_theta),
    ]
