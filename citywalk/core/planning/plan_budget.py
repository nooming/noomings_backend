# -*- coding: utf-8 -*-
"""规划 API 用量预算（采样点、步行分段上限）。"""
import os

DEFAULT_MAX_SAMPLE_POINTS = 12
MIN_PLAN_TIME_MIN = 30
MAX_PLAN_TIME_MIN = 240
MAX_ROUTE_WAYPOINTS = int(os.environ.get("MAX_ROUTE_WAYPOINTS", "5"))
MAX_ROUTE_WAYPOINTS_CHECKIN_LONG = 12
AMAP_POOL_WORKERS = int(os.environ.get("AMAP_MAX_CONCURRENT", "4"))


def compute_max_sample_points(plan_time: int, detour_mode: bool) -> int:
    """按计划时长动态限制沿路采样点数，降低 QPS。"""
    if plan_time <= 60:
        base = 6
    elif plan_time <= 120:
        base = 9
    else:
        base = 12
    if detour_mode:
        base = min(base + 2, DEFAULT_MAX_SAMPLE_POINTS)
    return min(base, DEFAULT_MAX_SAMPLE_POINTS)


def max_route_waypoints(plan_time: int = 60, visit_pace: str = "checkin") -> int:
    """按计划时长与停留节奏动态限制高德步行串点途经点数。"""
    from citywalk.core.planning.constants import normalize_visit_pace

    cap = MAX_ROUTE_WAYPOINTS
    if normalize_visit_pace(visit_pace) == "checkin":
        if plan_time >= 180:
            cap = max(cap, MAX_ROUTE_WAYPOINTS_CHECKIN_LONG)
        elif plan_time >= 120:
            cap = max(cap, 10)
    return cap


def cap_waypoints_for_walking(
        waypoints: list,
        plan_time: int = 60,
        visit_pace: str = "checkin",
) -> tuple:
    """限制串点步行分段数，返回 (waypoints, truncated)。"""
    limit = max_route_waypoints(plan_time, visit_pace)
    if len(waypoints) <= limit:
        return waypoints, False
    return waypoints[:limit], True
