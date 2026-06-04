# -*- coding: utf-8 -*-
"""探索模式（环形漫步）：中心点 + 扇区采样 POI + 环行串点。"""
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from lib.amap_client import AmapQuotaError, api_request_with_retry
from lib.geo_utils import haversine
from planning.plan_budget import AMAP_POOL_WORKERS

logger = logging.getLogger(__name__)

WALKING_URL = "https://restapi.amap.com/v3/direction/walking"
AROUND_URL = "https://restapi.amap.com/v3/place/around"
LOOP_NUM_SECTORS = 8
LOOP_POIS_PER_SECTOR = 2


def _parse_polyline_point(point_str: str) -> Optional[Tuple[float, float]]:
    try:
        lng, lat = map(float, point_str.split(","))
        return lng, lat
    except (ValueError, AttributeError):
        return None


def _fetch_walking_segment(
        seg_start: Tuple[float, float],
        seg_end: Tuple[float, float]) -> Optional[dict]:
    params = {
        "origin": f"{seg_start[0]},{seg_start[1]}",
        "destination": f"{seg_end[0]},{seg_end[1]}",
        "output": "json",
    }
    try:
        return api_request_with_retry(WALKING_URL, params)
    except AmapQuotaError:
        raise
    except Exception as exc:
        logger.warning("步行分段请求失败：%s", exc)
        return None


def sample_poi_in_circle(
        center: Tuple[float, float],
        plan_time: int,
        poi_type: str,
        target_city: Optional[str],
        poi_profile_weights: Dict[str, Dict[str, int]],
        poi_type_icons: Dict[str, str],
        normalize_poi_type_fn: Callable[[str], str],
        filter_low_value_poi_fn: Callable[[Dict, str], bool],
        is_poi_in_target_city_fn: Callable[[Dict, Optional[str]], bool],
) -> List[Dict]:
    """中心点周围按扇区并发采样 POI。"""
    poi_type = normalize_poi_type_fn(poi_type or "无偏好")
    walk_distance = plan_time * 0.6 * 83
    radius_m = max(300, min(walk_distance / (2 * math.pi), 2000))

    lat_rad = math.radians(center[1])
    meters_per_lat = 111320.0
    meters_per_lng = 111320.0 * math.cos(lat_rad) or 1e-6

    keywords_map = poi_profile_weights.get(poi_type) or poi_profile_weights.get("无偏好", {})
    target_keywords = list(keywords_map.keys()) or ["咖啡馆", "甜品店", "公园"]
    search_radius = min(int(radius_m * 0.6), 1000)

    logger.info(
        "探索模式采样：中心=%s 半径=%.0fm 搜索半径=%dm",
        center, radius_m, search_radius,
    )

    def fetch_sector(sector: int) -> Tuple[int, List]:
        angle = (2 * math.pi * sector) / LOOP_NUM_SECTORS
        s_lng = center[0] + (radius_m * 0.85 / meters_per_lng) * math.cos(angle)
        s_lat = center[1] + (radius_m * 0.85 / meters_per_lat) * math.sin(angle)
        params = {
            "location": f"{s_lng:.6f},{s_lat:.6f}",
            "radius": search_radius,
            "keywords": "|".join(target_keywords),
            "offset": 10,
            "page": 1,
            "output": "json",
            "sortrule": "distance",
        }
        if target_city:
            params["city"] = target_city.replace("市", "")
        try:
            data = api_request_with_retry(AROUND_URL, params)
            if data and data.get("status") == "1":
                return sector, data.get("pois", [])
        except AmapQuotaError:
            raise
        except Exception as exc:
            logger.warning("扇区%d搜索失败：%s", sector, exc)
        return sector, []

    sector_results: Dict[int, List] = {}
    with ThreadPoolExecutor(max_workers=min(LOOP_NUM_SECTORS, AMAP_POOL_WORKERS)) as pool:
        futures = {pool.submit(fetch_sector, s): s for s in range(LOOP_NUM_SECTORS)}
        for fut in as_completed(futures):
            s_idx, pois = fut.result()
            sector_results[s_idx] = pois

    all_pois: List[Dict] = []
    used_names: set = set()
    used_locs: List[Tuple[float, float]] = []

    for sector in range(LOOP_NUM_SECTORS):
        sector_count = 0
        for poi in sector_results.get(sector, []):
            if sector_count >= LOOP_POIS_PER_SECTOR:
                break
            poi_name = (poi.get("name") or "").strip()
            if not poi_name or poi_name in used_names:
                continue
            loc_raw = poi.get("location", "0,0")
            try:
                poi_lng, poi_lat = map(float, str(loc_raw).split(","))
            except ValueError:
                continue
            if any(haversine(poi_lng, poi_lat, u, v) < 50 for u, v in used_locs):
                continue
            if not filter_low_value_poi_fn(poi, poi_type):
                continue
            if target_city and not is_poi_in_target_city_fn(poi, target_city):
                continue

            poi_angle = math.atan2(poi_lat - center[1], poi_lng - center[0])
            dist_to_center = haversine(center[0], center[1], poi_lng, poi_lat)
            poi_type_str = (poi.get("type") or "").split(";")[0]
            poi_icon = "📍"
            for key, icon in poi_type_icons.items():
                if key in poi_name or key in poi_type_str:
                    poi_icon = icon
                    break

            all_pois.append({
                "name": poi_name,
                "address": poi.get("address", "暂无地址"),
                "location": [poi_lng, poi_lat],
                "type": poi_type_str,
                "icon": poi_icon,
                "dist_to_route": dist_to_center,
                "angle": poi_angle,
                "sector": sector,
                "sample_idx": sector,
            })
            used_names.add(poi_name)
            used_locs.append((poi_lng, poi_lat))
            sector_count += 1

    logger.info("探索模式采样 POI：%d 个（%d 扇区）", len(all_pois), LOOP_NUM_SECTORS)
    return all_pois


def generate_loop_route(
        center: Tuple[float, float],
        pois: List[Dict],
) -> Dict[str, Any]:
    """按角度排序环行：中心 → POI 环 → 回中心。"""
    if not pois:
        return {
            "new_route_points": [list(center), list(center)],
            "new_total_distance": 0,
            "new_walk_duration": 0,
            "new_total_duration": 0,
            "waypoints": [],
        }

    pois_sorted = sorted(pois, key=lambda p: p.get("angle", 0))
    waypoints = [(p["location"][0], p["location"][1]) for p in pois_sorted]
    route_sequence = [center] + waypoints + [center]
    segments = [
        (i, route_sequence[i], route_sequence[i + 1])
        for i in range(len(route_sequence) - 1)
    ]

    results: Dict[int, Optional[Tuple]] = {}
    with ThreadPoolExecutor(
            max_workers=min(AMAP_POOL_WORKERS, len(segments))
    ) as pool:
        def _run(seg):
            idx, seg_start, seg_end = seg
            data = _fetch_walking_segment(seg_start, seg_end)
            if not data or data.get("status") != "1":
                return idx, [], 0, 0
            paths = data.get("route", {}).get("paths", [])
            if not paths:
                return idx, [], 0, 0
            seg_path = paths[0]
            seg_points = []
            for step in seg_path.get("steps", []):
                polyline = step.get("polyline", "")
                if not polyline:
                    continue
                for point_str in polyline.split(";"):
                    loc = _parse_polyline_point(point_str)
                    if loc:
                        seg_points.append(loc)
            return (
                idx,
                seg_points,
                int(seg_path.get("distance", 0)),
                int(seg_path.get("duration", 0)) // 60,
            )

        for idx, pts, dist, dur in pool.map(_run, segments):
            results[idx] = (pts, dist, dur)

    all_route_points: List[Tuple[float, float]] = []
    total_distance = 0
    total_walk_duration = 0
    for i in range(len(segments)):
        entry = results.get(i)
        if not entry:
            continue
        seg_points, seg_dist, seg_dur = entry
        all_route_points.extend(seg_points)
        total_distance += seg_dist
        total_walk_duration += seg_dur

    if not all_route_points:
        all_route_points = list(route_sequence)

    return {
        "new_route_points": all_route_points,
        "new_total_distance": total_distance,
        "new_walk_duration": total_walk_duration,
        "new_total_duration": total_walk_duration,
        "waypoints": waypoints,
    }
