# -*- coding: utf-8 -*-
"""最短路采样、POI 沿途搜索与路线生成。"""
import logging
import os
from math import cos, radians, sqrt
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from lib.amap_client import AmapQuotaError, api_request_with_retry, consume_last_amap_info
from lib.geo_utils import haversine, normalize_city_name
from planning.constants import *
from planning.plan_budget import AMAP_POOL_WORKERS, cap_waypoints_for_walking, compute_max_sample_points
from planning.poi_selection import (
    DETOUR_EXTRA_SAMPLE,
    DETOUR_LATERAL_SAMPLE_M,
    ROUTE_SAMPLE_INTERVAL_DETOUR,
    SEGMENT_MIN_BUCKETS,
    _attach_route_progress_and_end,
    _filter_poi_greedy,
    _location_grid_key,
    _sort_poi_candidates,
    compute_max_poi_count,
    compute_min_poi_count,
    filter_low_value_poi,
    is_poi_in_target_city,
    parse_location,
    resolve_ambience_profile,
    score_poi_ambience,
    select_pois_by_route_segments,
)
from planning.plan_core import (
    _attach_route_progress,
    _order_pois_along_route,
    route_progress_meters,
    route_total_length_m,
)
from planning.runtime import AMAP_KEY

# 默认串行拉取采样点周边 POI，降低高德 CUQPS；设 AMAP_SAMPLE_SERIAL=0 可恢复并发
AMAP_SAMPLE_SERIAL = os.environ.get("AMAP_SAMPLE_SERIAL", "1").lower() in (
    "1", "true", "yes",
)


def get_shortest_route(start: Tuple[float, float], end: Tuple[float, float]) -> Dict:
    """第一步：获取起点→终点的最短步行路线（高德步行规划，起终点为全国有效坐标即可）"""
    url = "https://restapi.amap.com/v3/direction/walking"
    params = {
        "key": AMAP_KEY,
        "origin": f"{start[0]},{start[1]}",
        "destination": f"{end[0]},{end[1]}",
        "output": "json"
    }

    amap_info = ""
    try:
        data = api_request_with_retry(url, params)
        if not data:
            amap_info = consume_last_amap_info() or "无有效返回"
            return {
                "route_points": [start, end],
                "total_distance": 0,
                "total_duration": 0,
                "original_path": {},
                "amap_info": amap_info,
            }

        paths = data["route"]["paths"]
        if not paths:
            amap_info = consume_last_amap_info() or "空路径列表"
            return {
                "route_points": [start, end],
                "total_distance": 0,
                "total_duration": 0,
                "original_path": {},
                "amap_info": amap_info,
            }
        path = paths[0]
        route_points = []
        total_distance = int(path["distance"])
        total_duration = int(path["duration"]) // 60

        for step in path["steps"]:
            for point_str in step["polyline"].split(";"):
                loc = parse_location(point_str)
                if loc:
                    route_points.append(loc)

        return {
            "route_points": route_points,
            "total_distance": total_distance,
            "total_duration": total_duration,
            "original_path": path,
            "amap_info": "",
        }
    except AmapQuotaError:
        raise
    except Exception as e:
        logging.error("获取最短路线异常：%s", e)
        if not amap_info:
            amap_info = consume_last_amap_info() or str(e)
        return {
            "route_points": [start, end],
            "total_distance": 0,
            "total_duration": 0,
            "original_path": {},
            "amap_info": amap_info,
        }


def _route_point_at_progress_m(
        route_points: List[Tuple[float, float]], target_m: float
) -> Tuple[float, float, float, float]:
    """返回 (lng, lat, 段内切向 dx, dy) 于 target_m 处。"""
    if not route_points or len(route_points) < 2:
        p = route_points[0] if route_points else (0.0, 0.0)
        return p[0], p[1], 1.0, 0.0
    cumulative = 0.0
    for i in range(len(route_points) - 1):
        ax, ay = route_points[i]
        bx, by = route_points[i + 1]
        seg_len = haversine(ax, ay, bx, by)
        if cumulative + seg_len >= target_m or i == len(route_points) - 2:
            remain = max(0.0, target_m - cumulative)
            t = remain / seg_len if seg_len > 1e-3 else 0.0
            t = max(0.0, min(1.0, t))
            return ax + t * (bx - ax), ay + t * (by - ay), bx - ax, by - ay
        cumulative += seg_len
    last = route_points[-1]
    prev = route_points[-2]
    return last[0], last[1], last[0] - prev[0], last[1] - prev[1]


def _lateral_offset_points(
        lng: float, lat: float, tangent_dx: float, tangent_dy: float,
        offset_m: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """沿法线方向 ±offset_m 生成两个采样点（经纬度近似米制）。"""
    mag = sqrt(tangent_dx * tangent_dx + tangent_dy * tangent_dy)
    if mag < 1e-9:
        nx, ny = 0.0, 1.0
    else:
        nx, ny = -tangent_dy / mag, tangent_dx / mag
    lat_scale = 111320.0
    lng_scale = max(111320.0 * cos(radians(lat)), 1e-3)
    dlat = (offset_m / lat_scale) * ny
    dlng = (offset_m / lng_scale) * nx
    plus = (lng + dlng, lat + dlat)
    minus = (lng - dlng, lat - dlat)
    return plus, minus


def _detour_extra_sample_points(
        route_points: List[Tuple[float, float]],
        fractions: Tuple[float, ...] = (0.25, 0.5, 0.75),
        offset_m: float = DETOUR_LATERAL_SAMPLE_M,
) -> List[Tuple[float, float]]:
    """在走廊 progress 分位处侧向偏移，增强 off-corridor POI 召回。"""
    total = route_total_length_m(route_points)
    if total < 1.0:
        return []
    extras: List[Tuple[float, float]] = []
    for frac in fractions:
        target_m = total * frac
        lng, lat, tdx, tdy = _route_point_at_progress_m(route_points, target_m)
        p1, p2 = _lateral_offset_points(lng, lat, tdx, tdy, offset_m)
        extras.extend([p1, p2])
    return extras


def sample_poi_along_shortest_route(route_points: List[Tuple[float, float]],
                                    poi_type: str, target_city: str = None,
                                    route_style: str = "balanced",
                                    ambience_profile: str = None,
                                    detour_mode: bool = False,
                                    plan_time: int = 60) -> List[Dict]:
    """第二步：沿最短路线采样POI（语义氛围+距离平衡评分）"""
    max_samples = compute_max_sample_points(plan_time, detour_mode)
    interval = ROUTE_SAMPLE_INTERVAL
    if detour_mode and route_style == "atmosphere_first":
        interval = ROUTE_SAMPLE_INTERVAL_DETOUR

    # 1. 沿最短路线均匀取采样点
    sample_points = []
    current_distance = 0
    prev_point = route_points[0]

    sample_points.append(route_points[0])

    for point in route_points[1:]:
        dist = haversine(prev_point[0], prev_point[1], point[0], point[1])
        current_distance += dist

        if current_distance >= interval and len(sample_points) < max_samples:
            sample_points.append(point)
            current_distance = 0

        prev_point = point

    if sample_points[-1] != route_points[-1] and len(sample_points) < max_samples:
        sample_points.append(route_points[-1])

    if DETOUR_EXTRA_SAMPLE and detour_mode and len(sample_points) < max_samples:
        for extra in _detour_extra_sample_points(route_points):
            if len(sample_points) >= max_samples:
                break
            if extra not in sample_points:
                sample_points.append(extra)

    sample_points = sample_points[:max_samples]
    logging.info(f"沿最短路线生成采样点：{len(sample_points)}个（严格贴合路线）")

    # 2. 每个采样点搜索周边POI（支持全国任意城市+过滤低价值）
    profile = resolve_ambience_profile(poi_type, ambience_profile)
    target_keywords = list(POI_PROFILE_WEIGHTS.get(profile, {}).keys()) or ["咖啡馆", "甜品店", "公园"]
    normalized_target_city = normalize_city_name(target_city) if target_city else ""

    all_pois = []
    used_poi_names = set()
    used_grid_cells: set = set()  # 网格去重（O(1)替代O(n²)haversine遍历，每格≈55m）
    debug_stats = {
        "total_raw_pois": 0,
        "filtered_by_city": 0,
        "filtered_by_name_or_location": 0,
        "filtered_by_low_value": 0,
        "kept_pois": 0,
        "sample_points": len(sample_points),
        "per_sample": []
    }

    around_url = "https://restapi.amap.com/v3/place/around"
    around_offset = 20

    def _build_around_params(lng: float, lat: float) -> dict:
        p = {
            "key": AMAP_KEY,
            "location": f"{lng:.6f},{lat:.6f}",
            "radius": POI_SEARCH_RADIUS,
            "keywords": "|".join(target_keywords),
            "offset": around_offset,
            "output": "json",
            "sortrule": "distance"  # 按离采样点的距离排序（最贴合路线）
        }
        # 如果指定了目标城市，添加城市参数
        if target_city:
            p["city"] = target_city
        return p

    def _fetch_sample_pois(item):
        """单个采样点拉取（页1 + 条件页2），纯网络无共享状态，可并发。"""
        s_idx, (s_lng, s_lat) = item
        base = _build_around_params(s_lng, s_lat)
        p1 = dict(base, page=1)
        d1 = api_request_with_retry(around_url, p1)
        page1 = (d1.get("pois", []) if d1 else []) or []
        page2 = []
        # 第二页仅做兜底：第一页命中满页时才继续
        if len(page1) >= around_offset:
            p2 = dict(base, page=2)
            d2 = api_request_with_retry(around_url, p2)
            page2 = (d2.get("pois", []) if d2 else []) or []
        return s_idx, page1, page2

    # 阶段A：拉取各采样点周边 POI（默认串行降压；去重/评分在阶段 B）
    fetched: Dict[int, Tuple[list, list]] = {}
    if sample_points:
        items = list(enumerate(sample_points))
        if AMAP_SAMPLE_SERIAL:
            for item in items:
                s_idx, page1, page2 = _fetch_sample_pois(item)
                fetched[s_idx] = (page1, page2)
        else:
            with ThreadPoolExecutor(
                    max_workers=min(AMAP_POOL_WORKERS, len(sample_points))
            ) as executor:
                for s_idx, page1, page2 in executor.map(_fetch_sample_pois, items):
                    fetched[s_idx] = (page1, page2)

    # 阶段B：按采样点顺序做去重/过滤/评分（顺序敏感，串行执行）
    for idx, (lng, lat) in enumerate(sample_points):
        sample_candidates = []
        sample_seen_names = set()
        sample_grid_cells: set = set()
        sample_debug = {"sample_idx": idx, "raw_page1": 0, "raw_page2": 0, "kept": 0}

        pages = {1: fetched.get(idx, ([], []))[0], 2: fetched.get(idx, ([], []))[1]}

        try:
            for page in (1, 2):
                pois = pages[page] or []
                debug_stats["total_raw_pois"] += len(pois)
                if page == 1:
                    sample_debug["raw_page1"] = len(pois)
                else:
                    sample_debug["raw_page2"] = len(pois)

                # 筛选：目标城市 + 未重复 + 过滤低价值 + 匹配类型
                for poi in pois:
                    if normalized_target_city and not is_poi_in_target_city(poi, normalized_target_city):
                        debug_stats["filtered_by_city"] += 1
                        continue
                    poi_name = poi.get("name", "").strip()
                    if not poi_name:
                        debug_stats["filtered_by_name_or_location"] += 1
                        continue

                    # 格式化POI（保留离路线的距离，用于排序）
                    loc = parse_location(poi.get("location", ""))
                    if loc is None:
                        debug_stats["filtered_by_name_or_location"] += 1
                        continue
                    poi_lng, poi_lat = loc

                    # 去重检查1：按名称去重
                    if poi_name in used_poi_names or poi_name in sample_seen_names:
                        debug_stats["filtered_by_name_or_location"] += 1
                        continue

                    # 去重检查2：网格去重，O(1) 检查 3×3 邻格（覆盖约 55m 范围）
                    poi_gk = _location_grid_key(poi_lng, poi_lat)
                    neighbors = [
                        (poi_gk[0] + dr, poi_gk[1] + dc)
                        for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                    ]
                    if any(k in used_grid_cells or k in sample_grid_cells for k in neighbors):
                        logging.debug(f"坐标去重：{poi_name} 与已有POI位置重复（≈55m内）")
                        debug_stats["filtered_by_name_or_location"] += 1
                        continue

                    # 核心：过滤无效/低价值POI
                    if not filter_low_value_poi(poi, poi_type):
                        debug_stats["filtered_by_low_value"] += 1
                        continue

                    # 计算POI到当前采样点的距离（用于排序，优先选近的）
                    dist_to_route = haversine(lng, lat, poi_lng, poi_lat)

                    # 获取POI类型图标
                    poi_type_str = poi.get("type", "").split(";")[0]
                    poi_icon = "📍"  # 默认图标
                    for key, icon in POI_TYPE_ICONS.items():
                        if key in poi_name or key in poi_type_str:
                            poi_icon = icon
                            break

                    scoring = score_poi_ambience(
                        poi=poi,
                        poi_type=poi_type,
                        ambience_profile=profile,
                        route_style=route_style,
                        dist_to_route=dist_to_route
                    )
                    sample_candidates.append({
                        "name": poi_name,
                        "address": poi.get("address", "暂无地址"),
                        "location": [poi_lng, poi_lat],
                        "type": poi_type_str,
                        "icon": poi_icon,  # POI类型图标
                        "dist_to_route": dist_to_route,  # 离采样点的距离（米）
                        "ambience_profile": scoring["ambience_profile"],
                        "ambience_tags": scoring["ambience_tags"],
                        "semantic_score": scoring["semantic_score"],
                        "detour_cost": scoring["detour_cost"],
                        "final_score": scoring["final_score"],
                        "recommendation_reason": scoring["recommendation_reason"],
                        "sample_idx": idx  # 记录属于哪个采样点
                    })
                    sample_seen_names.add(poi_name)
                    sample_grid_cells.add(_location_grid_key(poi_lng, poi_lat))
            # 每个采样点优先保留综合分更高的 POI，避免全由最近点占满
            sample_candidates.sort(key=lambda x: (-x["final_score"], x["dist_to_route"]))
            selected_candidates = sample_candidates[:POI_PER_SAMPLE]
            all_pois.extend(selected_candidates)
            for picked in selected_candidates:
                used_poi_names.add(picked["name"])
                used_grid_cells.add(_location_grid_key(picked["location"][0], picked["location"][1]))
            sample_debug["kept"] = len(selected_candidates)
            debug_stats["kept_pois"] += len(selected_candidates)
        except Exception as e:
            logging.warning(f"采样点{idx + 1}搜索POI失败：{str(e)}")
            continue
        finally:
            debug_stats["per_sample"].append(sample_debug)

    # 排序：综合分优先，距离次之
    all_pois.sort(key=lambda x: (-x.get("final_score", 0.0), x["dist_to_route"]))
    if DEBUG_PLAN_LOG:
        logging.info(
            f"[plan_debug] poi_recall city={target_city or 'auto'} samples={debug_stats['sample_points']} "
            f"raw={debug_stats['total_raw_pois']} kept={debug_stats['kept_pois']} "
            f"filtered_city={debug_stats['filtered_by_city']} "
            f"filtered_dup_or_invalid={debug_stats['filtered_by_name_or_location']} "
            f"filtered_low_value={debug_stats['filtered_by_low_value']} "
            f"sample_detail={debug_stats['per_sample']}"
        )
    return all_pois


def filter_poi_for_route(pois: List[Dict], plan_time: int,
                         original_route_duration: int,
                         route_style: str = "balanced",
                         route_points: Optional[List[Tuple[float, float]]] = None,
                         end: Optional[Tuple[float, float]] = None,
                         detour_mode: bool = False,
                         visit_pace: str = "checkin",
                         distance_m: Optional[float] = None) -> List[Dict]:
    """第三步：筛选POI（匹配计划时间；防回头；detour 模式允许侧向绕远）"""
    max_poi_count = compute_max_poi_count(
        plan_time, original_route_duration, visit_pace,
    )
    min_poi_count = compute_min_poi_count(
        plan_time, detour_mode, max_poi_count, visit_pace, distance_m=distance_m,
    )
    if not pois:
        filtered_pois = []
    elif (detour_mode or max_poi_count >= SEGMENT_MIN_BUCKETS) and route_points and len(route_points) >= 2:
        filtered_pois = select_pois_by_route_segments(
            pois,
            route_points,
            end,
            max_poi_count,
            min_poi_count,
            route_style,
            detour_mode,
            visit_pace,
        )
        if not filtered_pois:
            candidates = list(pois)
            _attach_route_progress_and_end(candidates, route_points, end)
            sorted_pois = _sort_poi_candidates(candidates, detour_mode)
            if sorted_pois:
                filtered_pois = _order_pois_along_route(sorted_pois)[:1]
    else:
        candidates = list(pois)
        _attach_route_progress_and_end(candidates, route_points, end)
        filtered_pois = _filter_poi_greedy(
            candidates, max_poi_count, route_points, end, route_style, detour_mode,
            visit_pace,
        )
        if not filtered_pois:
            sorted_pois = _sort_poi_candidates(candidates, detour_mode)
            if sorted_pois:
                if route_points and len(route_points) >= 2:
                    filtered_pois = _order_pois_along_route(sorted_pois)[:1]
                else:
                    filtered_pois = sorted_pois[:1]

    logging.info(
        f"筛选后高价值POI数量：{len(filtered_pois)}，plan_time={plan_time}，"
        f"detour_mode={detour_mode} segment={detour_mode or max_poi_count >= SEGMENT_MIN_BUCKETS}"
    )
    return filtered_pois


def _ensure_seed_pois_retained(
        filtered_pois: List[Dict],
        route_pois: List[Dict],
        max_poi_count: int,
        route_points: Optional[List[Tuple[float, float]]] = None,
) -> List[Dict]:
    """用户勾选的种草点（is_seed）尽量保留在最终打卡列表中。"""
    if max_poi_count <= 0 or not route_pois:
        return filtered_pois
    seeds = [p for p in route_pois if p.get("is_seed")]
    if not seeds:
        return filtered_pois
    result = list(filtered_pois)
    names = {p.get("name") for p in result}
    for seed in seeds:
        name = seed.get("name")
        if not name or name in names:
            continue
        if len(result) < max_poi_count:
            result.append(seed)
            names.add(name)
            continue
        replace_idx = None
        lowest = float("inf")
        for i, p in enumerate(result):
            if p.get("is_seed"):
                continue
            sc = float(p.get("final_score", 0) or 0)
            if sc < lowest:
                lowest = sc
                replace_idx = i
        if replace_idx is not None:
            result[replace_idx] = seed
            names.add(name)
    if route_points and len(route_points) >= 2:
        _attach_route_progress(result, route_points)
        result = _order_pois_along_route(result)
    return result[:max_poi_count]


def generate_new_route(start: Tuple[float, float], end: Tuple[float, float],
                       filtered_pois: List[Dict],
                       route_points: Optional[List[Tuple[float, float]]] = None,
                       plan_time: int = 60,
                       visit_pace: str = "checkin") -> Dict:
    """第四步：基于筛选后的高价值POI生成新路线（分段规划后合并）"""
    waypoints = []
    ordered_pois = []
    route_waypoints_truncated = False

    if filtered_pois:
        if route_points and len(route_points) >= 2:
            _attach_route_progress(filtered_pois, route_points)
            ordered_pois = _order_pois_along_route(filtered_pois)
        else:
            # 无参考主线时退回贪心最近邻
            remaining_pois = filtered_pois.copy()
            current_pos = start
            while remaining_pois:
                min_dist = float("inf")
                nearest_poi = None
                nearest_idx = -1
                for i, poi in enumerate(remaining_pois):
                    poi_lng, poi_lat = poi["location"]
                    dist = haversine(current_pos[0], current_pos[1], poi_lng, poi_lat)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_poi = poi
                        nearest_idx = i
                if nearest_poi:
                    ordered_pois.append(nearest_poi)
                    current_pos = (nearest_poi["location"][0], nearest_poi["location"][1])
                    remaining_pois.pop(nearest_idx)
                else:
                    break

        waypoints = [
            (p["location"][0], p["location"][1]) for p in ordered_pois
        ]
        waypoints, route_waypoints_truncated = cap_waypoints_for_walking(
            waypoints, plan_time=plan_time, visit_pace=visit_pace,
        )
        if route_waypoints_truncated:
            ordered_pois = ordered_pois[:len(waypoints)]
        filtered_pois.clear()
        filtered_pois.extend(ordered_pois)

    # 高德步行路线API不支持waypoints，需要分段规划后合并
    # 构建路线点序列：起点 → POI1 → POI2 → ... → 终点
    route_sequence = [start] + waypoints + [end]

    walking_url = "https://restapi.amap.com/v3/direction/walking"

    def _fetch_segment(seg):
        """规划单段步行路线，返回 (seg_index, points, distance_m, duration_min)。纯网络，可并发。"""
        seg_index, seg_start, seg_end = seg
        params = {
            "origin": f"{seg_start[0]},{seg_start[1]}",
            "destination": f"{seg_end[0]},{seg_end[1]}",
            "output": "json",
        }
        try:
            data = api_request_with_retry(walking_url, params)
        except AmapQuotaError:
            raise
        if not data:
            logging.warning(f"分段路线{seg_index + 1}规划失败")
            return seg_index, [], 0, 0
        paths = data.get("route", {}).get("paths", [])
        if not paths:
            logging.warning(f"分段路线{seg_index + 1}返回空路径，跳过")
            return seg_index, [], 0, 0
        seg_path = paths[0]
        seg_points = []
        for step in seg_path.get("steps", []):
            polyline = step.get("polyline", "")
            if not polyline:
                continue
            for point_str in polyline.split(";"):
                loc = parse_location(point_str)
                if loc:
                    seg_points.append(loc)
        return (seg_index, seg_points,
                int(seg_path.get("distance", 0)),
                int(seg_path.get("duration", 0)) // 60)

    segments = [
        (i, route_sequence[i], route_sequence[i + 1])
        for i in range(len(route_sequence) - 1)
    ]

    all_route_points = []
    total_distance = 0
    total_walk_duration = 0

    if segments:
        # 并发规划各分段，再按 index 顺序拼接（保证路线点顺序正确）
        results: List[Optional[Tuple]] = [None] * len(segments)
        with ThreadPoolExecutor(
                max_workers=min(2, len(segments))
        ) as executor:
            for seg_index, seg_points, seg_dist, seg_dur in executor.map(_fetch_segment, segments):
                results[seg_index] = (seg_points, seg_dist, seg_dur)
        for entry in results:
            if not entry:
                continue
            seg_points, seg_dist, seg_dur = entry
            all_route_points.extend(seg_points)
            total_distance += seg_dist
            total_walk_duration += seg_dur

    # 如果分段规划失败，直接返回直线连接
    if not all_route_points:
        logging.error("所有分段路线规划失败，使用直线连接")
        all_route_points = route_sequence

    return {
        "new_route_points": all_route_points,
        "new_total_distance": total_distance,
        "new_walk_duration": total_walk_duration,
        "new_total_duration": total_walk_duration,
        "waypoints": waypoints,
        "route_waypoints_truncated": route_waypoints_truncated,
    }
