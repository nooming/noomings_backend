# -*- coding: utf-8 -*-
import copy
import math

from .geometry import build_road_segments

DEFAULT_ROAD_WIDTH = 6.0


def clone_json(v):
    return copy.deepcopy(v)


def road_from_inner(inner, fallback_width=DEFAULT_ROAD_WIDTH):
    ix0 = float(inner.get("x_min", float("nan")))
    ix1 = float(inner.get("x_max", float("nan")))
    iy0 = float(inner.get("y_min", float("nan")))
    iy1 = float(inner.get("y_max", float("nan")))
    if not all(math.isfinite(v) for v in [ix0, ix1, iy0, iy1]):
        return None
    return {
        "centerline": [
            [ix0, iy0],
            [ix1, iy0],
            [ix1, iy1],
            [ix0, iy1],
            [ix0, iy0],
        ],
        "width": float(fallback_width) if math.isfinite(float(fallback_width)) else DEFAULT_ROAD_WIDTH,
        "closed": True,
    }


def inner_from_road(road):
    pts = road.get("centerline") if isinstance(road.get("centerline"), list) else []
    xmin = float("inf")
    xmax = float("-inf")
    ymin = float("inf")
    ymax = float("-inf")
    for p in pts:
        x = float(p[0]) if p and len(p) > 0 else float("nan")
        y = float(p[1]) if p and len(p) > 1 else float("nan")
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        xmin = min(xmin, x)
        xmax = max(xmax, x)
        ymin = min(ymin, y)
        ymax = max(ymax, y)
    if not all(math.isfinite(v) for v in [xmin, xmax, ymin, ymax]):
        return None
    return {"x_min": xmin, "x_max": xmax, "y_min": ymin, "y_max": ymax}


def normalize_road(road_raw, inner_raw, fallback_road_factory=None):
    fallback_road = fallback_road_factory() if callable(fallback_road_factory) else None
    road = clone_json(road_raw) if road_raw and isinstance(road_raw, dict) else None
    if not road or not isinstance(road.get("centerline"), list) or len(road["centerline"]) < 2:
        road = road_from_inner(inner_raw or {}, road.get("width") if road else None)
    if not road:
        return clone_json(fallback_road or road_from_inner({}, DEFAULT_ROAD_WIDTH))
    centerline = road.get("centerline") if isinstance(road.get("centerline"), list) else []
    norm = []
    for p in centerline:
        x = float(p[0]) if p and len(p) > 0 else float("nan")
        y = float(p[1]) if p and len(p) > 1 else float("nan")
        if math.isfinite(x) and math.isfinite(y):
            norm.append([x, y])
    clean = []
    for pt in norm:
        if not clean or math.hypot(clean[-1][0] - pt[0], clean[-1][1] - pt[1]) > 1e-6:
            clean.append(pt)
    if len(clean) < 2:
        return clone_json(fallback_road or road_from_inner({}, DEFAULT_ROAD_WIDTH))
    road["centerline"] = clean
    road["width"] = max(2.4, float(road.get("width", DEFAULT_ROAD_WIDTH) or DEFAULT_ROAD_WIDTH))
    road["closed"] = road.get("closed") is not False
    return road


def build_road_segments_from_road(road_or_inner):
    road = road_or_inner if road_or_inner.get("centerline") else road_from_inner(road_or_inner or {}, DEFAULT_ROAD_WIDTH)
    return build_road_segments({"road": road})
