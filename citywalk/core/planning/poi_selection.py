# -*- coding: utf-8 -*-
"""POI 筛选、评分、停留时长与折返修剪。"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from citywalk.core.geo.geo_utils import haversine, normalize_city_name
from citywalk.core.planning.constants import *
from citywalk.core.planning.plan_core import (
    _attach_route_progress,
    _attach_route_progress_and_end,
    _order_pois_along_route,
    estimate_chained_walk_minutes,
    route_total_length_m,
)
def parse_location(location_str: str) -> Optional[Tuple[float, float]]:
    """解析 'lng,lat' 字符串，失败返回 None（替代裸 split 防止 ValueError）。"""
    try:
        parts = str(location_str).split(",")
        if len(parts) != 2:
            return None
        return float(parts[0]), float(parts[1])
    except (ValueError, AttributeError):
        return None


def _location_grid_key(lng: float, lat: float) -> Tuple[int, int]:
    """坐标转网格 key（每格约 55m），用于 O(1) 近邻去重。"""
    return (round(lat * 2000), round(lng * 2000))


# 计划时长对齐：氛围节点串点绕远 vs 防大幅回头
DETOUR_TIME_THRESHOLD_MIN = 30
PLAN_TIME_FILL_RATIO = 0.95
PLAN_TIME_SHORTFALL_RATIO = 0.9
MIN_POI_DETOUR = 5
MIN_POI_DETOUR_MAX = 8
MIN_PLAN_TIME_FOR_MIN_POI = 90
DETOUR_ATMOSPHERE_TOWARD_MULT = 2.5
FILL_POI_TOWARD_END_MULTIPLIER = 1.5
TRIM_BACKTRACK_RELAX_MULT = 2.0
TRIM_BACKTRACK_MIN_GAP_M = 150
END_TAIL_MAX_DIST_M = 450


def _end_tail_max_dist_m(
        route_points: Optional[List[Tuple[float, float]]],
        visit_pace: str = "checkin",
) -> float:
    """末站距地理终点的距离上限；checkin 沿走廊多点时放宽，避免成批删站。"""
    if normalize_visit_pace(visit_pace) != "checkin":
        return float(END_TAIL_MAX_DIST_M)
    if route_points and len(route_points) >= 2:
        route_len = route_total_length_m(route_points)
        return float(max(800, min(END_TAIL_MAX_DIST_M_CHECKIN, int(route_len * 0.25))))
    return float(END_TAIL_MAX_DIST_M_CHECKIN)
POI_STAY_MIN_M = 5
POI_STAY_MAX_M = 25
POI_STAY_MAX_M_HISTORY = 30
POI_STAY_ABS_MAX_M = 45
DEFAULT_POI_STAY_ESTIMATE_M = 5
CHAIN_WALK_M_PER_MIN = 75
SEGMENT_MIN_BUCKETS = 5
SEGMENT_MAX_PER_BUCKET = 2
DETOUR_LATERAL_SAMPLE_M = 150
DETOUR_EXTRA_SAMPLE = True
ROUTE_SAMPLE_INTERVAL_DETOUR = 350


def is_detour_mode(plan_time: int, shortest_walk_min: int) -> bool:
    return (plan_time - shortest_walk_min) >= DETOUR_TIME_THRESHOLD_MIN


def _pace_cfg(visit_pace: str = "checkin") -> Dict[str, Any]:
    return VISIT_PACE_CONFIG[normalize_visit_pace(visit_pace)]


def target_poi_count_by_distance(distance_m: float, visit_pace: str = "checkin") -> int:
    cfg = _pace_cfg(visit_pace)
    per_km = float(cfg.get("pois_per_km") or 0)
    if per_km <= 0 or distance_m <= 0:
        return 0
    return max(MIN_REQUIRED_NON_OPTIONAL_POIS, int(round((distance_m / 1000.0) * per_km)))


def compute_max_poi_count(
        plan_time: int,
        original_route_duration: int,
        visit_pace: str = "checkin",
) -> int:
    cfg = _pace_cfg(visit_pace)
    estimate_m = int(cfg.get("stay_estimate_m") or DEFAULT_POI_STAY_ESTIMATE_M)
    cap = int(cfg.get("max_poi_cap") or 12)
    available_stay_time = max(0, plan_time - original_route_duration)
    max_poi_count = int(available_stay_time / max(estimate_m, 1))
    return min(max(max_poi_count, 1), cap)


def compute_min_poi_count(
        plan_time: int,
        detour_mode: bool,
        max_poi_count: int,
        visit_pace: str = "checkin",
        distance_m: Optional[float] = None,
) -> int:
    if not detour_mode or plan_time < MIN_PLAN_TIME_FOR_MIN_POI:
        base = 1
    else:
        base = min(MIN_POI_DETOUR_MAX, max_poi_count, MIN_POI_DETOUR)
    if normalize_visit_pace(visit_pace) == "checkin" and distance_m and distance_m > 0:
        by_km = target_poi_count_by_distance(distance_m, visit_pace)
        base = max(base, min(by_km, max_poi_count))
    return base


def _poi_atmosphere_sort_key(poi: Dict) -> Tuple:
    """氛围优先：有标签/语义分高的 POI 优先，用于 detour 串点而非纯距离绕远。"""
    tags = poi.get("ambience_tags") or []
    sem = float(poi.get("semantic_score", 0) or 0)
    has_atmo = 1 if (sem > 0 or len(tags) > 0) else 0
    return (
        -has_atmo,
        -float(poi.get("final_score", 0) or 0),
        -sem,
        float(poi.get("dist_to_route", float("inf")) or float("inf")),
    )


def _sort_poi_candidates(candidates: List[Dict], detour_mode: bool) -> List[Dict]:
    if detour_mode:
        return sorted(candidates, key=_poi_atmosphere_sort_key)
    return sorted(
        candidates,
        key=lambda x: (-x.get("final_score", 0.0), x.get("dist_to_route", float("inf"))),
    )


def _selection_spacing_and_slack(
        route_style: str,
        detour_mode: bool,
        visit_pace: str = "checkin",
) -> Tuple[float, float, float]:
    style_cfg = ROUTE_STYLE_CONFIG.get(route_style, ROUTE_STYLE_CONFIG["balanced"])
    min_spacing_m = float(style_cfg["min_spacing_m"])
    backtrack_slack_m = float(style_cfg.get("backtrack_slack_m", 200))
    toward_end_slack_m = float(style_cfg.get("toward_end_slack_m", 80))
    if detour_mode and route_style == "atmosphere_first":
        min_spacing_m = float(style_cfg.get("min_spacing_detour_m", 110))
        backtrack_slack_m = float(style_cfg.get("backtrack_slack_detour_m", 320))
    pace_spacing = _pace_cfg(visit_pace).get("min_spacing_m")
    if pace_spacing is not None:
        min_spacing_m = float(pace_spacing)
    return min_spacing_m, backtrack_slack_m, toward_end_slack_m


def estimate_plan_total_min(
        walk_duration_min: int,
        pois: List[Dict],
        visit_pace: str = "checkin",
) -> int:
    activity, _free = compute_activity_and_free_min(
        walk_duration_min, pois, plan_time=0,
    )
    return activity


def compute_activity_and_free_min(
        walk_duration_min: int,
        pois: List[Dict],
        plan_time: int = 0,
) -> Tuple[int, int]:
    """活动耗时（步行+停留）与相对计划时长的自由安排分钟数。"""
    walk = int(walk_duration_min)
    stay = sum(int(p.get("stay_time", 0) or 0) for p in pois)
    activity = walk + stay
    free_m = max(0, int(plan_time) - activity) if plan_time > 0 else 0
    return activity, free_m


def _filter_poi_greedy(
        candidates: List[Dict],
        max_poi_count: int,
        route_points: Optional[List[Tuple[float, float]]],
        end: Optional[Tuple[float, float]],
        route_style: str,
        detour_mode: bool,
        visit_pace: str = "checkin",
) -> List[Dict]:
    min_spacing_m, backtrack_slack_m, toward_end_slack_m = _selection_spacing_and_slack(
        route_style, detour_mode, visit_pace
    )
    sorted_pois = _sort_poi_candidates(candidates, detour_mode)
    filtered_pois: List[Dict] = []
    max_progress_selected = -1.0
    min_dist_to_end_selected = float("inf")
    for poi in sorted_pois:
        is_last_slot = len(filtered_pois) >= max_poi_count - 1
        if not _poi_passes_selection_rules(
                poi, filtered_pois, end, route_points, min_spacing_m,
                backtrack_slack_m, toward_end_slack_m,
                max_progress_selected, min_dist_to_end_selected,
                is_last_slot, apply_toward_end=False, visit_pace=visit_pace):
            continue
        filtered_pois.append(poi)
        if route_points and len(route_points) >= 2:
            max_progress_selected = max(
                max_progress_selected,
                poi.get("_route_progress_m", 0.0),
            )
        if end:
            dist_end = poi.get("_dist_to_end_m", _poi_dist_to_end_m(poi, end))
            min_dist_to_end_selected = min(min_dist_to_end_selected, dist_end)
        if len(filtered_pois) >= max_poi_count:
            break
    return filtered_pois


def select_pois_by_route_segments(
        candidates: List[Dict],
        route_points: List[Tuple[float, float]],
        end: Optional[Tuple[float, float]],
        max_poi_count: int,
        min_poi_count: int,
        route_style: str,
        detour_mode: bool,
        visit_pace: str = "checkin",
) -> List[Dict]:
    """沿走廊 progress 分桶，每桶氛围优选 1 个（detour 且候选足时可 2 个）。"""
    if not candidates or not route_points or len(route_points) < 2:
        return _filter_poi_greedy(
            candidates, max_poi_count, route_points, end, route_style, detour_mode,
            visit_pace,
        )

    pool = list(candidates)
    _attach_route_progress_and_end(pool, route_points, end)
    total_len = route_total_length_m(route_points)
    pace_cfg = _pace_cfg(visit_pace)
    if pace_cfg.get("use_max_buckets"):
        n_buckets = max(1, max_poi_count)
    else:
        n_buckets = min(
            max_poi_count,
            max(min_poi_count, min(8, max_poi_count), SEGMENT_MIN_BUCKETS),
        )
        n_buckets = max(1, n_buckets)
    min_spacing_m, backtrack_slack_m, toward_end_slack_m = _selection_spacing_and_slack(
        route_style, detour_mode, visit_pace
    )
    min_for_two = int(pace_cfg.get("segment_min_candidates_for_two") or 3)

    if total_len < 1.0:
        bucket_width = 1.0
    else:
        bucket_width = total_len / n_buckets

    buckets: Dict[int, List[Dict]] = {}
    for poi in pool:
        prog = poi.get("_route_progress_m", 0.0)
        if bucket_width > 0:
            bid = int(prog / bucket_width)
        else:
            bid = 0
        bid = max(0, min(n_buckets - 1, bid))
        poi["_segment_bucket"] = bid
        buckets.setdefault(bid, []).append(poi)

    filtered_pois: List[Dict] = []
    max_progress_selected = -1.0
    min_dist_to_end_selected = float("inf")

    for bid in range(n_buckets):
        if len(filtered_pois) >= max_poi_count:
            break
        bucket_list = buckets.get(bid, [])
        if not bucket_list:
            continue
        sorted_bucket = _sort_poi_candidates(bucket_list, detour_mode)
        max_per_bucket = 1
        if detour_mode and len(sorted_bucket) >= min_for_two:
            max_per_bucket = SEGMENT_MAX_PER_BUCKET
        picked_in_bucket = 0
        for poi in sorted_bucket:
            if len(filtered_pois) >= max_poi_count:
                break
            if picked_in_bucket >= max_per_bucket:
                break
            is_last_slot = len(filtered_pois) >= max_poi_count - 1
            if not _poi_passes_selection_rules(
                    poi, filtered_pois, end, route_points, min_spacing_m,
                    backtrack_slack_m, toward_end_slack_m,
                    max_progress_selected, min_dist_to_end_selected,
                    is_last_slot, apply_toward_end=False, visit_pace=visit_pace):
                continue
            filtered_pois.append(poi)
            picked_in_bucket += 1
            max_progress_selected = max(
                max_progress_selected, poi.get("_route_progress_m", 0.0)
            )
            if end:
                dist_end = poi.get("_dist_to_end_m", _poi_dist_to_end_m(poi, end))
                min_dist_to_end_selected = min(min_dist_to_end_selected, dist_end)

    if not filtered_pois:
        sorted_all = _sort_poi_candidates(pool, detour_mode)
        if sorted_all:
            filtered_pois = [sorted_all[0]]
    return filtered_pois


_COORD_ADDRESS_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$")


def _poi_max_stay_min(poi_type: str, ambience_profile: str) -> int:
    profile = (ambience_profile or "").strip()
    if "历史" in profile or (poi_type or "").strip() == "历史":
        return POI_STAY_MAX_M_HISTORY
    return POI_STAY_MAX_M


def _checkin_stay_cap(poi_type: str, ambience_profile: str, visit_pace: str) -> int:
    cfg = _pace_cfg(visit_pace)
    profile = (ambience_profile or "").strip()
    if "历史" in profile or (poi_type or "").strip() == "历史":
        return int(cfg.get("stay_cap_history_m") or 12)
    return int(cfg.get("stay_cap_m") or 10)


def allocate_poi_stay_times(
        pois: List[Dict],
        plan_time: int,
        walk_duration_min: int,
        poi_type: str = "",
        ambience_profile: str = "",
        visit_pace: str = "checkin",
) -> Tuple[List[Dict], str, int]:
    """按 plan_time 与步行耗时分配每点停留，返回 (pois, 提示片段, free_time_min)。"""
    if not pois:
        return pois, "", 0

    stay_budget = max(0, plan_time - int(walk_duration_min))
    n = len(pois)
    hint = ""
    free_m = 0

    if stay_budget <= 0:
        for p in pois:
            p["stay_time"] = POI_STAY_MIN_M
        _, free_m = compute_activity_and_free_min(
            walk_duration_min, pois, plan_time,
        )
        return pois, hint, free_m

    if normalize_visit_pace(visit_pace) == "checkin":
        cap = _checkin_stay_cap(poi_type, ambience_profile, visit_pace)
        for p in pois:
            p["stay_time"] = max(POI_STAY_MIN_M, cap)
        used = sum(p["stay_time"] for p in pois)
        free_m = max(0, stay_budget - used)
        if free_m > 10:
            hint = (
                f"约 {int(free_m)} 分钟为途中自由安排（咖啡/休息可自选）；"
                "标「可选」的打卡点可按体力跳过。"
            )
        return pois, hint, free_m

    max_stay = _poi_max_stay_min(poi_type, ambience_profile)
    profile_max = max_stay
    per_poi_cap = min(POI_STAY_ABS_MAX_M, max(profile_max, stay_budget // max(n, 1)))
    if n <= 4 and stay_budget > n * profile_max:
        per_poi_cap = min(POI_STAY_ABS_MAX_M, stay_budget // n)

    if stay_budget >= n * per_poi_cap:
        for p in pois:
            p["stay_time"] = per_poi_cap
        shortfall = stay_budget - n * per_poi_cap
        if shortfall > 10:
            hint = "各站停留已按行程估算；若仍觉得偏短，可在店内多留一会儿。"
        _, free_m = compute_activity_and_free_min(
            walk_duration_min, pois, plan_time,
        )
        return pois, hint, free_m

    base = stay_budget // n
    remainder = stay_budget % n
    for i, p in enumerate(pois):
        stay = base + (1 if i < remainder else 0)
        p["stay_time"] = max(POI_STAY_MIN_M, min(per_poi_cap, stay))
    _, free_m = compute_activity_and_free_min(
        walk_duration_min, pois, plan_time,
    )
    return pois, hint, free_m


def mark_optional_pois(
        pois: List[Dict],
        visit_pace: str = "checkin",
        min_required: int = MIN_REQUIRED_NON_OPTIONAL_POIS,
) -> List[Dict]:
    """为次要打卡点标注 optional（种子与高分核心站不标）。"""
    if not pois:
        return pois
    if normalize_visit_pace(visit_pace) != "checkin":
        for p in pois:
            p.pop("optional", None)
            p.pop("optional_reason", None)
        return pois

    scores = [float(p.get("final_score", 0) or 0) for p in pois]
    scores_sorted = sorted(scores)
    median = scores_sorted[len(scores_sorted) // 2] if scores_sorted else 0.0
    ranked = sorted(pois, key=lambda p: -float(p.get("final_score", 0) or 0))
    required_names = {
        p.get("name") for p in ranked[:max(1, min(min_required, len(ranked)))]
    }

    for p in pois:
        if p.get("is_seed") or p.get("name") in required_names:
            p["optional"] = False
            p.pop("optional_reason", None)
            continue
        low_score = float(p.get("final_score", 0) or 0) < median
        if p.get("_fill_added") or low_score:
            p["optional"] = True
            p["optional_reason"] = "可跳过"
        else:
            p["optional"] = False
            p.pop("optional_reason", None)
    return pois


def ensure_last_poi_near_end(
        pois: List[Dict],
        end: Tuple[float, float],
        route_points: Optional[List[Tuple[float, float]]] = None,
        visit_pace: str = "checkin",
        min_keep: int = 1,
) -> List[Dict]:
    """约束顺序末站尽量靠近终点；中间站点不因距终点远而批量删除。"""
    if not pois or not end or len(pois) <= 1:
        return pois

    tail_max = _end_tail_max_dist_m(route_points, visit_pace)
    working = list(pois)
    _attach_route_progress_and_end(working, route_points, end)
    ordered = (
        _order_pois_along_route(working)
        if route_points and len(route_points) >= 2
        else sorted(working, key=lambda p: p.get("_dist_to_end_m", float("inf")))
    )

    def _dist_end(p: Dict) -> float:
        return float(p.get("_dist_to_end_m", _poi_dist_to_end_m(p, end)))

    last_dist = _dist_end(ordered[-1])
    if last_dist <= tail_max:
        return ordered

    near_end = [p for p in ordered[:-1] if _dist_end(p) <= tail_max]
    if near_end:
        best = max(near_end, key=lambda p: p.get("_route_progress_m", 0.0))
        rest = [p for p in ordered if p.get("name") != best.get("name")]
        logging.info(
            "末站距终点 %dm，将「%s」调整为顺序最后一站",
            int(last_dist), best.get("name", ""),
        )
        return rest + [best]

    min_keep = max(1, min(min_keep, len(ordered)))
    if normalize_visit_pace(visit_pace) == "checkin" and len(ordered) >= min_keep:
        logging.info(
            "末站距终点 %dm，checkin 保留全部 %d 站（步行仍至地图终点）",
            int(last_dist), len(ordered),
        )
        return ordered

    if len(ordered) > min_keep:
        removed = ordered.pop()
        logging.info(
            "尾站距终点 %dm，移除末站「%s」",
            int(_dist_end(removed)), removed.get("name", ""),
        )
    return ordered


def _poi_passes_selection_rules(
        poi: Dict,
        filtered_pois: List[Dict],
        end: Optional[Tuple[float, float]],
        route_points: Optional[List[Tuple[float, float]]],
        min_spacing_m: float,
        backtrack_slack_m: float,
        toward_end_slack_m: float,
        max_progress_selected: float,
        min_dist_to_end_selected: float,
        is_last_slot: bool,
        apply_toward_end: bool = False,
        visit_pace: str = "checkin",
) -> bool:
    if route_points and len(route_points) >= 2:
        prog = poi.get("_route_progress_m", 0.0)
        if filtered_pois and prog < max_progress_selected - backtrack_slack_m:
            return False

    if end:
        dist_end = poi.get("_dist_to_end_m")
        if dist_end is None:
            dist_end = _poi_dist_to_end_m(poi, end)
            poi["_dist_to_end_m"] = dist_end
        if apply_toward_end and filtered_pois:
            if dist_end > min_dist_to_end_selected + toward_end_slack_m:
                return False
        tail_max = _end_tail_max_dist_m(route_points, visit_pace)
        if is_last_slot and dist_end > tail_max:
            return False

    poi_lng, poi_lat = poi["location"]
    for chosen in filtered_pois:
        clng, clat = chosen["location"]
        if haversine(poi_lng, poi_lat, clng, clat) < min_spacing_m:
            return False
    return True


def try_fill_pois_for_plan_time(
        filtered_pois: List[Dict],
        all_candidates: List[Dict],
        plan_time: int,
        walk_duration_est: int,
        max_poi_count: int,
        route_style: str,
        route_points: Optional[List[Tuple[float, float]]],
        end: Optional[Tuple[float, float]],
        detour_mode: bool,
        start: Optional[Tuple[float, float]] = None,
        shortest_walk_min: int = 0,
        visit_pace: str = "checkin",
        distance_m: Optional[float] = None,
) -> List[Dict]:
    """时长不足时按氛围候选补点；未达最少节点前不因估时达标停止。"""
    if not all_candidates or max_poi_count <= 0:
        return filtered_pois

    pace = normalize_visit_pace(visit_pace)
    pace_cfg = _pace_cfg(pace)
    min_spacing_m, backtrack_slack_m, toward_end_slack_m = _selection_spacing_and_slack(
        route_style, detour_mode, pace
    )
    if not detour_mode:
        toward_end_slack_m *= FILL_POI_TOWARD_END_MULTIPLIER

    selected_names = {p.get("name") for p in filtered_pois}
    pool = [p for p in all_candidates if p.get("name") not in selected_names]
    if not pool:
        return filtered_pois

    result = list(filtered_pois)
    _attach_route_progress_and_end(pool, route_points, end)
    _attach_route_progress_and_end(result, route_points, end)
    sorted_pool = _sort_poi_candidates(pool, detour_mode)

    min_poi_count = compute_min_poi_count(
        plan_time, detour_mode, max_poi_count, pace, distance_m=distance_m,
    )
    target_total = int(plan_time * PLAN_TIME_FILL_RATIO)
    walk_est = int(walk_duration_est)
    use_chain = start is not None and end is not None
    fill_until_max = bool(pace_cfg.get("fill_until_max"))

    while len(result) < max_poi_count:
        if use_chain:
            walk_est = estimate_chained_walk_minutes(
                start, end, result, shortest_walk_min, route_points
            )
        if not fill_until_max:
            estimated = estimate_plan_total_min(walk_est, result, pace)
            if estimated >= target_total and len(result) >= min_poi_count:
                break
        elif len(result) >= min_poi_count and distance_m and distance_m > 0:
            if len(result) >= target_poi_count_by_distance(distance_m, pace):
                estimated = estimate_plan_total_min(walk_est, result, pace)
                if estimated >= int(plan_time * PLAN_TIME_SHORTFALL_RATIO):
                    break

        max_progress_selected = max(
            (p.get("_route_progress_m", 0.0) for p in result), default=-1.0
        )
        min_dist_to_end_selected = min(
            (p.get("_dist_to_end_m", float("inf")) for p in result),
            default=float("inf"),
        )
        added = False
        for poi in sorted_pool:
            if poi.get("name") in {p.get("name") for p in result}:
                continue
            is_last_slot = len(result) >= max_poi_count - 1
            if not _poi_passes_selection_rules(
                    poi, result, end, route_points, min_spacing_m,
                    backtrack_slack_m, toward_end_slack_m,
                    max_progress_selected, min_dist_to_end_selected,
                    is_last_slot, apply_toward_end=False, visit_pace=pace):
                continue
            poi["_fill_added"] = True
            result.append(poi)
            added = True
            break
        if not added:
            break

    if len(result) > len(filtered_pois):
        logging.info(
            f"氛围补点：{len(filtered_pois)} -> {len(result)} "
            f"(detour={detour_mode}, min_poi={min_poi_count}, walk_est={walk_est})"
        )
    return result


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


def trim_backtrack_pois_toward_end(
        pois: List[Dict],
        end: Tuple[float, float],
        route_style: str = "balanced",
        route_points: Optional[List[Tuple[float, float]]] = None,
        relaxed: bool = False) -> List[Dict]:
    """修剪访问顺序上「大幅离终点变远」的点；relaxed 保留小幅折返。"""
    if not pois or not end:
        return pois

    style_cfg = ROUTE_STYLE_CONFIG.get(route_style, ROUTE_STYLE_CONFIG["balanced"])
    toward_slack = float(style_cfg.get("toward_end_slack_m", 80))
    if relaxed:
        toward_slack *= TRIM_BACKTRACK_RELAX_MULT

    working = list(pois)
    _attach_route_progress_and_end(working, route_points, end)

    if route_points and len(route_points) >= 2:
        ordered = _order_pois_along_route(working)
    else:
        ordered = sorted(working, key=lambda p: p.get("_dist_to_end_m", float("inf")))

    if not ordered:
        return pois

    kept = [ordered[0]]
    for poi in ordered[1:]:
        if poi.get("is_seed"):
            kept.append(poi)
            continue
        prev_dist = kept[-1].get("_dist_to_end_m", float("inf"))
        cur_dist = poi.get("_dist_to_end_m", float("inf"))
        gap = cur_dist - prev_dist
        if cur_dist <= prev_dist + toward_slack:
            kept.append(poi)
        elif relaxed and gap <= TRIM_BACKTRACK_MIN_GAP_M:
            kept.append(poi)

    before = len(pois)
    after = len(kept)
    if after < before:
        logging.info(
            f"朝终点修剪打卡点：{before} -> {after}（slack={int(toward_slack)}m relaxed={relaxed}）"
        )
    return kept if kept else [ordered[0]]


def is_poi_in_target_city(poi: Dict, target_city: str = None) -> bool:
    """校验POI是否在目标城市（宽容匹配，避免误删同城POI）。"""
    if not target_city:
        return True  # 未指定城市时，接受所有POI

    target_norm = normalize_city_name(target_city)
    cityname_norm = normalize_city_name(poi.get("cityname", ""))

    # 仅当有 cityname 时做匹配判断；cityname 缺失（如只有省名）时保守放行，避免误删同城 POI。
    if cityname_norm:
        return target_norm in cityname_norm or cityname_norm in target_norm
    return True


def filter_low_value_poi(poi: Dict, poi_type: str) -> bool:
    """
    过滤无效/低价值POI：返回True表示有效，False表示无效
    校验规则：
    1. 排除命中EXCLUDE_POI_TYPES的POI
    2. 排除命中LOW_VALUE_KEYWORDS的POI
    3. 仅保留高匹配度的有效POI
    """
    poi_name = poi.get("name", "").strip().lower()
    poi_type_str = poi.get("type", "").strip().lower()

    # 规则1：排除完全无效的类型
    for exclude_type in EXCLUDE_POI_TYPES:
        if exclude_type.lower() in poi_type_str or exclude_type.lower() in poi_name:
            logging.debug(f"排除低价值POI（无效类型）：{poi_name}")
            return False

    # 规则2：排除低价值关键词
    for low_key in LOW_VALUE_KEYWORDS:
        if low_key.lower() in poi_name or low_key.lower() in poi_type_str:
            logging.debug(f"排除低价值POI（低价值关键词）：{poi_name}")
            return False

    # 规则3：校验是否命中目标高价值类型
    # 无偏好/无权重配置时，只要通过前两条规则即有效
    poi_type = normalize_poi_type(poi_type)
    if poi_type == "无偏好" or poi_type not in POI_PROFILE_WEIGHTS:
        return True

    target_weights = POI_PROFILE_WEIGHTS.get(poi_type, {})
    if not target_weights:
        return True

    # 匹配高价值关键词（名称/类型任一命中）
    for valid_key in target_weights.keys():
        if valid_key.lower() in poi_name or valid_key.lower() in poi_type_str:
            return True

    logging.debug(f"排除低价值POI（未命中目标类型）：{poi_name}")
    return False


def resolve_ambience_profile(poi_type: str, ambience_profile: str = None) -> str:
    """解析氛围画像：优先显式 ambience，否则 poi_type；均做枚举归一。"""
    candidate = normalize_poi_type((ambience_profile or poi_type or "无偏好").strip())
    if candidate in POI_PROFILE_WEIGHTS:
        return candidate
    return "无偏好"


def score_poi_ambience(poi: Dict, poi_type: str, ambience_profile: str, route_style: str,
                       dist_to_route: float) -> Dict:
    """计算POI氛围分、绕路惩罚与综合分。"""
    profile = resolve_ambience_profile(poi_type, ambience_profile)
    profile_weights = POI_PROFILE_WEIGHTS.get(profile, {})
    style_cfg = ROUTE_STYLE_CONFIG.get(route_style, ROUTE_STYLE_CONFIG["balanced"])

    poi_name = (poi.get("name", "") or "").strip().lower()
    poi_type_str = (poi.get("type", "") or "").strip().lower()
    matched_tags = []
    semantic_score = 0.0
    for key, weight in profile_weights.items():
        key_norm = key.lower()
        if key_norm in poi_name or key_norm in poi_type_str:
            matched_tags.append(key)
            semantic_score += float(weight)

    # 将距离转换为温和惩罚（每100米记1分），并限制上限
    detour_cost = min(dist_to_route / 100.0, style_cfg["max_detour_cost"])
    final_score = style_cfg["semantic_weight"] * semantic_score - style_cfg["detour_weight"] * detour_cost
    reason = (
        f"命中偏好标签{len(matched_tags)}个，离路线约{int(dist_to_route)}米"
        if matched_tags else
        f"位置贴近路线（约{int(dist_to_route)}米）"
    )
    return {
        "ambience_profile": profile,
        "ambience_tags": matched_tags,
        "semantic_score": round(semantic_score, 3),
        "detour_cost": round(detour_cost, 3),
        "final_score": round(final_score, 3),
        "recommendation_reason": reason
    }

