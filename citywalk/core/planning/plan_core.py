# -*- coding: utf-8 -*-
"""可单测的规划纯函数（链式估时、路线进度几何）。"""
from typing import Dict, List, Optional, Tuple

from citywalk.core.geo.geo_utils import haversine

CHAIN_WALK_M_PER_MIN = 75
SEGMENT_MIN_BUCKETS = 5


def route_progress_meters(lng: float, lat: float,
                          route_points: List[Tuple[float, float]]) -> float:
    """计算点沿路线折线从起点累计的前进距离（米），用于 start→end 顺序排列。"""
    if not route_points or len(route_points) < 2:
        return 0.0

    min_dist = float("inf")
    best_progress = 0.0
    cumulative = 0.0

    for i in range(len(route_points) - 1):
        ax, ay = route_points[i]
        bx, by = route_points[i + 1]
        seg_len = haversine(ax, ay, bx, by)
        if seg_len < 1e-3:
            cumulative += seg_len
            continue

        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy
        if denom < 1e-12:
            t = 0.0
        else:
            t = ((lng - ax) * dx + (lat - ay) * dy) / denom
            t = max(0.0, min(1.0, t))

        proj_lng = ax + t * dx
        proj_lat = ay + t * dy
        d = haversine(lng, lat, proj_lng, proj_lat)
        progress = cumulative + seg_len * t
        if d < min_dist:
            min_dist = d
            best_progress = progress
        cumulative += seg_len

    return best_progress


def route_total_length_m(route_points: List[Tuple[float, float]]) -> float:
    if not route_points or len(route_points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(route_points) - 1):
        a, b = route_points[i], route_points[i + 1]
        total += haversine(a[0], a[1], b[0], b[1])
    return total


def _attach_route_progress(pois: List[Dict], route_points: List[Tuple[float, float]]) -> None:
    for poi in pois:
        lng, lat = poi["location"]
        poi["_route_progress_m"] = route_progress_meters(lng, lat, route_points)


def _order_pois_along_route(pois: List[Dict]) -> List[Dict]:
    """按沿主路线前进距离排序，同位置优先高分。"""
    return sorted(
        pois,
        key=lambda p: (
            p.get("_route_progress_m", 0.0),
            -p.get("final_score", 0.0),
            p.get("dist_to_route", float("inf")),
        ),
    )


def _poi_dist_to_end_m(poi: Dict, end: Tuple[float, float]) -> float:
    lng, lat = poi["location"]
    return haversine(lng, lat, end[0], end[1])


def _attach_dist_to_end(pois: List[Dict], end: Tuple[float, float]) -> None:
    for poi in pois:
        poi["_dist_to_end_m"] = _poi_dist_to_end_m(poi, end)


def _attach_route_progress_and_end(
        pois: List[Dict],
        route_points: Optional[List[Tuple[float, float]]],
        end: Optional[Tuple[float, float]] = None) -> None:
    if route_points and len(route_points) >= 2:
        _attach_route_progress(pois, route_points)
    if end:
        _attach_dist_to_end(pois, end)


def estimate_chained_walk_minutes(
        start: Tuple[float, float],
        end: Tuple[float, float],
        pois: List[Dict],
        shortest_walk_min: int,
        route_points: Optional[List[Tuple[float, float]]] = None,
        order_key: str = "_route_progress_m",
        m_per_min: float = CHAIN_WALK_M_PER_MIN) -> int:
    """起点→POI→终点链式 haversine 粗估步行，用于 fill 与 stay 预算，不调高德。"""
    if not pois:
        return int(shortest_walk_min)
    if route_points and len(route_points) >= 2:
        working = list(pois)
        _attach_route_progress(working, route_points)
        ordered = _order_pois_along_route(working)
    else:
        ordered = sorted(pois, key=lambda p: p.get(order_key, 0.0))
    chain = [start] + [(p["location"][0], p["location"][1]) for p in ordered] + [end]
    total_m = 0.0
    for i in range(len(chain) - 1):
        a, b = chain[i], chain[i + 1]
        total_m += haversine(a[0], a[1], b[0], b[1])
    est = int(total_m / m_per_min) if m_per_min > 0 else int(shortest_walk_min)
    return max(int(shortest_walk_min), est)


def validate_span_only(
        start: Tuple[float, float],
        end: Tuple[float, float],
        max_span_m: float = 25000) -> Tuple[bool, str]:
    span_m = haversine(start[0], start[1], end[0], end[1])
    if span_m > max_span_m:
        return False, f"距离 {int(span_m / 1000)}km 超限"
    return True, ""
