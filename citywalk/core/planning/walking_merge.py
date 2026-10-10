# -*- coding: utf-8 -*-
"""分段步行结果拼接：失败段直线兜底并生成用户向说明。"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

from citywalk.core.geo.geo_utils import haversine

Coord = Tuple[float, float]

# 直线兜底估算步行速度（米/分钟），约 4.8 km/h
_STRAIGHT_WALK_M_PER_MIN = 80.0


def build_walk_leg_labels(
        ordered_poi_names: Sequence[str],
        *,
        start_label: str = "起点",
        end_label: str = "终点",
) -> List[str]:
    return [start_label] + [n or "途经点" for n in ordered_poi_names] + [end_label]


def _short_label(name: str, max_len: int = 12) -> str:
    s = (name or "").strip()
    if len(s) <= max_len:
        return s or "途经点"
    return s[: max_len - 1] + "…"


def format_walking_segment_failure_tip(failures: List[Dict[str, Any]]) -> str:
    if not failures:
        return ""
    if any(f.get("all_failed") for f in failures):
        return (
            "步行路线未能完整拉取，地图为起终点直线示意；"
            "请减少站点或稍后重试。"
        )
    legs = []
    for f in failures:
        idx = f.get("index")
        fr = _short_label(str(f.get("from") or "?"))
        to = _short_label(str(f.get("to") or "?"))
        legs.append(f"第 {idx} 段（{fr} → {to}）")
    if len(legs) == 1:
        return f"{legs[0]} 未能获取步行路线，地图上该段为直线连接。"
    joined = "；".join(legs)
    return f"共 {len(legs)} 段未能获取步行路线（{joined}），地图上对应段落为直线连接。"


def stitch_walk_segment_results(
        segment_specs: Sequence[Tuple[int, Coord, Coord]],
        seg_results: Sequence[Optional[Tuple[List, int, int]]],
        leg_labels: Sequence[str],
) -> Dict[str, Any]:
    """
    按顺序拼接各段 path。seg_results[i] = (points, distance_m, duration_min) 或 None。
    空段用起终点直线连接并记入 walking_segment_failures。
    """
    failures: List[Dict[str, Any]] = []
    all_route_points: List[List[float]] = []
    total_distance = 0
    total_walk_duration = 0

    for i, spec in enumerate(segment_specs):
        _idx, seg_start, seg_end = spec
        entry = seg_results[i] if i < len(seg_results) else None
        seg_points: List = []
        seg_dist = 0
        seg_dur = 0
        if entry:
            seg_points, seg_dist, seg_dur = entry

        if not seg_points:
            fr = leg_labels[i] if i < len(leg_labels) else "?"
            to = leg_labels[i + 1] if i + 1 < len(leg_labels) else "?"
            failures.append({"index": i + 1, "from": fr, "to": to})
            seg_points = [list(seg_start), list(seg_end)]
            seg_dist = int(haversine(seg_start[0], seg_start[1], seg_end[0], seg_end[1]))
            seg_dur = max(1, int(seg_dist / _STRAIGHT_WALK_M_PER_MIN))

        if all_route_points and seg_points:
            if (
                len(seg_points) >= 2
                and all_route_points[-1][0] == seg_points[0][0]
                and all_route_points[-1][1] == seg_points[0][1]
            ):
                seg_points = seg_points[1:]

        all_route_points.extend(seg_points)
        total_distance += seg_dist
        total_walk_duration += seg_dur

    if not all_route_points and segment_specs:
        failures = [{"index": 0, "from": "全程", "to": "", "all_failed": True}]
        _, first_start, _ = segment_specs[0]
        _, _, last_end = segment_specs[-1]
        all_route_points = [list(first_start), list(last_end)]

    return {
        "new_route_points": all_route_points,
        "new_total_distance": total_distance,
        "new_walk_duration": total_walk_duration,
        "new_total_duration": total_walk_duration,
        "walking_segment_failures": failures,
    }
