# -*- coding: utf-8 -*-
"""execute_plan_request：/plan 与 Agent 共用的规划编排。"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from citywalk.core.geo.amap_client import AmapQuotaError, api_request_with_retry
from citywalk.core.geo.geo_utils import haversine, normalize_city_name
from citywalk.core.geo.geocoding import (
    geocode_address,
    resolve_location,
    resolve_location_detail,
    resolve_seed_location,
    validate_citywalk_endpoints,
)
from citywalk.core.planning.constants import *  # noqa: F403
from citywalk.core.planning.constants import normalize_visit_pace
from citywalk.core.planning.plan_budget import MAX_PLAN_TIME_MIN, MIN_PLAN_TIME_MIN
from citywalk.core.planning.plan_loop import generate_loop_route, sample_poi_in_circle
from citywalk.core.planning.poi_selection import (
    allocate_poi_stay_times,
    compute_activity_and_free_min,
    compute_max_poi_count,
    compute_min_poi_count,
    ensure_last_poi_near_end,
    estimate_chained_walk_minutes,
    filter_low_value_poi,
    is_detour_mode,
    is_poi_in_target_city,
    mark_optional_pois,
    resolve_ambience_profile,
    trim_backtrack_pois_toward_end,
    try_fill_pois_for_plan_time,
)
from citywalk.core.planning.route_engine import (
    _ensure_seed_pois_retained,
    filter_poi_for_route,
    generate_new_route,
    get_shortest_route,
    sample_poi_along_shortest_route,
)
from citywalk.core.planning.route_tip import build_user_route_tip
from citywalk.core.planning.runtime import AMAP_KEY

def _min_dist_to_route_m(lng: float, lat: float,
                         route_points: List[Tuple[float, float]]) -> float:
    """点到路线（采样若干折点）的最小直线距离，仅用于排序参考。"""
    if not route_points:
        return 0.0
    step = max(1, len(route_points) // 60)  # 控制计算量
    best = float("inf")
    for i in range(0, len(route_points), step):
        rp = route_points[i]
        d = haversine(lng, lat, rp[0], rp[1])
        if d < best:
            best = d
    return 0.0 if best == float("inf") else best


def _plan_time_response_fields(
        plan_time: int,
        walk_duration_min: int,
        pois: List[Dict],
) -> Dict[str, Any]:
    """活动耗时、自由时间与 breakdown，供前端对齐「计划 vs 预计」。"""
    activity, free_m = compute_activity_and_free_min(
        walk_duration_min, pois, plan_time,
    )
    stay = sum(int(p.get("stay_time", 0) or 0) for p in pois)
    return {
        "activity_total_min": activity,
        "free_time_min": free_m,
        "estimated_total_min": activity,
        "time_breakdown": {
            "walk_min": int(walk_duration_min),
            "stay_min": stay,
            "free_min": free_m,
        },
    }


def _walking_route_fail_message(amap_info: str) -> str:
    """步行最短路失败时返回用户可读文案，透传高德 info。"""
    info = (amap_info or "").strip()
    base = "高德步行规划未成功，请确认起终点在同一城市且距离适中"
    if info:
        return f"{base}（{info}），或约 30 秒后再试。"
    return (
        "步行路线规划失败，请检查起终点是否在同一城市，"
        "或稍后再试（若刚出现限流提示请等待约 30 秒）。"
    )


def build_seed_pois(seed_specs: List[Any],
                    route_points: List[Tuple[float, float]],
                    ambience_profile: str = "无偏好",
                    route_style: str = "balanced",
                    city: Optional[str] = None) -> List[Dict]:
    """把灵感/种草点（名称或 {name,lng,lat}）构造成与采样 POI 同构的高分候选。

    - 已带坐标则直接用；只有名称则地理编码；失败的丢弃。
    - final_score 置高，使其在筛选中被优先串联（仍受路线/绕路约束裁剪）。
    """
    seeds: List[Dict] = []
    seen = set()
    for spec in (seed_specs or [])[:8]:
        if isinstance(spec, str):
            name, reason, category, area = spec.strip(), "", "", ""
            lng = lat = None
        elif isinstance(spec, dict):
            name = (spec.get("name") or "").strip()
            reason = (spec.get("reason") or "").strip()
            category = (spec.get("category") or "").strip()
            area = (spec.get("area") or "").strip()
            lng = spec.get("lng")
            lat = spec.get("lat")
        else:
            continue
        if not name or name in seen:
            continue

        coords = resolve_seed_location(
            name, city, route_points, area=area, lng=lng, lat=lat,
        )
        if not coords:
            continue
        lng, lat = coords

        # 距离护栏：离群的种草点（如起终点在 A 城、灵感点却在几十公里外）会被后续
        # _ensure_seed_pois_retained 强制串联，把路线撑到几十公里。这里在入口直接丢弃，
        # 使其根本进不了候选池。无主线参考时（route_points 为空）跳过该校验。
        dist_to_route = _min_dist_to_route_m(lng, lat, route_points)
        if route_points and dist_to_route > MAX_SEED_DIST_TO_ROUTE_M:
            logging.info(
                "种草点「%s」离主线 %d 米，超出 %d 米上限，丢弃",
                name, int(dist_to_route), MAX_SEED_DIST_TO_ROUTE_M,
            )
            continue

        seen.add(name)
        icon = "✨"
        for key, ic in POI_TYPE_ICONS.items():
            if key in name or (category and key in category):
                icon = ic
                break

        seeds.append({
            "name": name,
            "address": (category and f"{category}") or "种草推荐",
            "location": [lng, lat],
            "type": category or "灵感推荐",
            "icon": icon,
            "dist_to_route": dist_to_route,
            "ambience_profile": ambience_profile,
            "ambience_tags": ["种草"],
            "semantic_score": 10.0,
            "detour_cost": 0.0,
            "final_score": 99.0,  # 高分优先串联
            "recommendation_reason": reason or "网友种草推荐",
            "sample_idx": -1,
            "is_seed": True,
        })
    return seeds


def fetch_poi_photos(name: str, city: str = "", lng: float = None,
                     lat: float = None, limit: int = 3) -> List[str]:
    """高德官方 POI 图片（place/text）。仅返回图片直链，合规可用。"""
    if not AMAP_KEY or not name:
        return []
    params = {
        "key": AMAP_KEY,
        "keywords": name,
        "offset": 5,
        "page": 1,
        "extensions": "all",
        "output": "json",
    }
    if city:
        params["city"] = city
    if lng is not None and lat is not None:
        params["location"] = f"{lng},{lat}"
    try:
        data = api_request_with_retry("https://restapi.amap.com/v3/place/text", params)
    except Exception as e:
        logging.warning("POI 图片检索失败：%s", e)
        return []
    pois = (data.get("pois") if data else None) or []
    urls: List[str] = []
    for poi in pois:
        for ph in (poi.get("photos") or []):
            url = (ph.get("url") or "").strip()
            if url:
                urls.append(url)
            if len(urls) >= limit:
                return urls
        if urls:
            break
    return urls[:limit]


def _execute_loop_plan_request(
        data: Dict[str, Any],
        meta: Dict[str, Any],
) -> Tuple[dict, int, dict]:
    """探索模式：仅中心点，环形漫步。"""
    start_raw = data.get("start", "")
    plan_time = int(data.get("plan_time", 60))
    poi_type = normalize_poi_type((data.get("poi_type") or "无偏好").strip() or "无偏好")
    ambience_profile = resolve_ambience_profile(
        poi_type, (data.get("ambience_profile") or "").strip() or poi_type
    )
    city_raw = (data.get("city") or "").strip().replace("市", "")
    city_for_geocode = city_raw or None
    target_city = normalize_city_name(city_raw) if city_raw else None

    start_lng, start_lat = None, None
    if isinstance(start_raw, list) and len(start_raw) == 2:
        start_lng, start_lat = float(start_raw[0]), float(start_raw[1])
        start_address = f"{start_lng},{start_lat}"
    elif isinstance(start_raw, str) and start_raw.strip():
        start_address = start_raw.strip()
    else:
        return ({
            "success": False,
            "message": "探索模式请在地图上选择中心点，或输入地址。",
        }, 400, meta)

    meta["plan_stage"] = "geocode"
    if start_lng is None or start_lat is None:
        start_coords = resolve_location(start_address, city_for_geocode)
        if not start_coords:
            return ({
                "success": False,
                "message": f"没能定位探索中心「{start_address}」，请写清城市或地标。",
            }, 400, meta)
        start_lng, start_lat = start_coords

    if not target_city:
        detected_city = get_city_from_location(start_lng, start_lat)
        if detected_city:
            city_for_geocode = detected_city.replace("市", "")
            target_city = normalize_city_name(city_for_geocode)

    center = (start_lng, start_lat)
    meta["start_coords"] = [start_lng, start_lat]
    meta["center_coords"] = [start_lng, start_lat]
    meta["start_address"] = start_address

    meta["plan_stage"] = "sample_poi"
    route_pois = sample_poi_in_circle(
        center,
        plan_time,
        poi_type,
        target_city,
        POI_PROFILE_WEIGHTS,
        POI_TYPE_ICONS,
        normalize_poi_type,
        filter_low_value_poi,
        is_poi_in_target_city,
    )

    if not route_pois:
        return ({
            "success": True,
            "mode": "loop",
            "message": "该区域未找到符合条件的打卡点，请换位置或偏好再试",
            "path": [list(center), list(center)],
            "distance": 0,
            "duration": 0,
            "pois": [],
            "center": list(center),
            "plan_time_min": plan_time,
            "filtered_pois": [],
            "new_route": {},
        }, 200, meta)

    walk_time_est = int(plan_time * 0.6)
    visit_pace = normalize_visit_pace(data.get("visit_pace"))
    meta["visit_pace"] = visit_pace
    filtered_pois = filter_poi_for_route(
        route_pois,
        plan_time,
        walk_time_est,
        route_style="balanced",
        route_points=None,
        end=None,
        detour_mode=False,
        visit_pace=visit_pace,
    )

    meta["plan_stage"] = "build_route"
    loop_route = generate_loop_route(center, filtered_pois)
    total_distance = loop_route["new_total_distance"]
    total_duration = loop_route["new_total_duration"]
    route_points = loop_route["new_route_points"]

    stay_hint = ""
    if filtered_pois:
        filtered_pois = mark_optional_pois(filtered_pois, visit_pace)
        for p in filtered_pois:
            p.pop("_fill_added", None)
        filtered_pois, stay_hint, _free_hint = allocate_poi_stay_times(
            filtered_pois,
            plan_time,
            total_duration,
            poi_type=poi_type,
            ambience_profile=ambience_profile,
            visit_pace=visit_pace,
        )

    time_fields = _plan_time_response_fields(plan_time, total_duration, filtered_pois)
    optional_count = sum(1 for p in filtered_pois if p.get("optional"))
    route_tip = build_user_route_tip(
        mode="loop",
        poi_count=len(filtered_pois),
        start_address=start_address,
        stay_hint=stay_hint,
        optional_poi_count=optional_count,
        plan_time_min=plan_time,
        activity_total_min=time_fields["activity_total_min"],
        free_time_min=time_fields["free_time_min"],
    )

    meta["plan_stage"] = "complete"
    return ({
        "success": True,
        "mode": "loop",
        "message": "探索路线规划成功",
        "route_tip": route_tip,
        "plan_time_min": plan_time,
        "visit_pace": visit_pace,
        **time_fields,
        "path": route_points,
        "distance": total_distance,
        "duration": total_duration,
        "pois": filtered_pois,
        "center": list(center),
        "filtered_pois": filtered_pois,
        "new_route": {
            "waypoints_count": len(loop_route.get("waypoints", [])),
            "walk_distance_m": total_distance,
            "walk_duration_min": loop_route["new_walk_duration"],
            "total_duration_min": total_duration,
            "route_points": route_points,
        },
    }, 200, meta)


def execute_plan_request(data: Dict[str, Any]) -> Tuple[dict, int, dict]:
    """
    执行路线规划。
    返回 (response_body, http_status, meta)，meta 含 start_coords / end_coords。
    """
    meta: Dict[str, Any] = {}
    try:

        mode = (data.get("mode") or "route").strip().lower()
        if mode not in ("route", "loop"):
            return ({
                "success": False,
                "message": "mode 仅支持 route（起终点）或 loop（探索模式）",
            }, 400, meta)

        start_raw = data.get("start", "")
        end_raw = data.get("end", "")
        plan_time = int(data.get("plan_time", 60))  # 默认 60 分钟
        # None-安全：键存在但为 null 时 .strip() 会抛错，故先 `or 默认`（与 loop 分支一致）
        poi_type = (data.get("poi_type") or "无偏好").strip() or "无偏好"
        route_style = (data.get("route_style") or "balanced").strip() or "balanced"
        ambience_profile = (data.get("ambience_profile") or "").strip() or poi_type
        city_raw = (data.get("city") or "").strip().replace("市", "")
        city_for_geocode = city_raw or None
        target_city = normalize_city_name(city_raw) if city_raw else None

        poi_type = normalize_poi_type(poi_type)
        ambience_profile = resolve_ambience_profile(poi_type, ambience_profile)
        visit_pace = normalize_visit_pace(data.get("visit_pace"))
        meta["visit_pace"] = visit_pace
        error_msg = None
        if plan_time < MIN_PLAN_TIME_MIN or plan_time > MAX_PLAN_TIME_MIN:
            error_msg = f"游玩时长请设在 {MIN_PLAN_TIME_MIN}–{MAX_PLAN_TIME_MIN} 分钟之间"
        elif poi_type not in POI_PROFILE_WEIGHTS.keys():
            error_msg = "这个偏好暂不支持，请重新选择"
        elif mode == "route" and route_style not in ROUTE_STYLE_CONFIG:
            error_msg = "这个路线风格暂不支持，请重新选择"

        if error_msg:
            return ({"success": False, "message": error_msg}, 400, meta)

        if not AMAP_KEY:
            return ({
                "success": False,
                "message": "地图服务未配置，请在服务端设置 AMAP_KEY。",
            }, 503, meta)

        if mode == "loop":
            return _execute_loop_plan_request(data, meta)

        start_lng, start_lat = None, None
        if isinstance(start_raw, list) and len(start_raw) == 2:
            start_lng, start_lat = float(start_raw[0]), float(start_raw[1])
            start_address = f"{start_lng},{start_lat}"
        elif isinstance(start_raw, str) and start_raw.strip():
            start_address = start_raw.strip()
        else:
            start_address = "北京市东城区天安门"  # 缺省起点

        end_lng, end_lat = None, None
        if isinstance(end_raw, list) and len(end_raw) == 2:
            end_lng, end_lat = float(end_raw[0]), float(end_raw[1])
            end_address = f"{end_lng},{end_lat}"
        elif isinstance(end_raw, str) and end_raw.strip():
            end_address = end_raw.strip()
        else:
            end_address = "北京市西城区王府井"  # 缺省终点

        meta["plan_stage"] = "geocode"

        # 起点—终点地理编码；坐标已给则跳过
        if start_lng is None or start_lat is None:
            start_coords = resolve_location(start_address, city_for_geocode)
            if not start_coords:
                return ({
                    "success": False,
                    "message": f"没能定位起点「{start_address}」，请写清城市或地标。",
                }, 400, meta)
            start_lng, start_lat = start_coords

        if not target_city:
            detected_city = get_city_from_location(start_lng, start_lat)
            if detected_city:
                city_for_geocode = detected_city.replace("市", "")
                target_city = normalize_city_name(city_for_geocode)
                logging.info(f"自动识别城市：{city_for_geocode}")

        if end_lng is None or end_lat is None:
            end_coords = resolve_location(end_address, city_for_geocode)
            if not end_coords:
                return ({
                    "success": False,
                    "message": (
                        f"没能定位终点「{end_address}」，"
                        "请确认与起点在同一座城市。"
                    ),
                }, 400, meta)
            end_lng, end_lat = end_coords

        start = (start_lng, start_lat)
        end = (end_lng, end_lat)
        meta["start_coords"] = [start_lng, start_lat]
        meta["end_coords"] = [end_lng, end_lat]
        meta["start_address"] = start_address
        meta["end_address"] = end_address

        ok, walk_err = validate_citywalk_endpoints(start, end, target_city)
        if not ok:
            meta["validation_failed"] = True
            return ({"success": False, "message": walk_err}, 400, meta)

        meta["plan_stage"] = "shortest_route"
        shortest_route = get_shortest_route(start, end)
        if shortest_route.get("total_distance", 0) <= 0:
            return ({
                "success": False,
                "message": _walking_route_fail_message(
                    shortest_route.get("amap_info", ""),
                ),
            }, 400, meta)
        logging.info(f"最短路线：距离{shortest_route['total_distance']}米，耗时{shortest_route['total_duration']}分钟")

        meta["plan_stage"] = "sample_poi"
        # 沿路采样 POI（类型与权重见 VALID_POI_WEIGHT）
        if DEBUG_PLAN_LOG:
            logging.info(
                f"[plan_debug] request city={target_city or 'auto'} poi_type={poi_type} "
                f"route_style={route_style} ambience_profile={ambience_profile} "
                f"plan_time={plan_time} start={start} end={end}"
            )
        detour_mode = is_detour_mode(plan_time, shortest_route["total_duration"])
        route_pois = sample_poi_along_shortest_route(
            shortest_route["route_points"],
            poi_type,
            target_city,
            route_style,
            ambience_profile,
            detour_mode=detour_mode,
            plan_time=plan_time,
        )

        # ④ 种子点注入：把灵感/种草点合并进候选池，交给现有筛选自然串联。
        # 完全可选（仅当 data 带 seed_pois 时生效）且防御式，不影响既有 /plan 流程。
        seed_specs = data.get("seed_pois")
        if seed_specs:
            try:
                seeds = build_seed_pois(
                    seed_specs,
                    shortest_route["route_points"],
                    ambience_profile=resolve_ambience_profile(poi_type, ambience_profile),
                    route_style=route_style,
                    city=city_for_geocode,
                )
                if seeds:
                    existing = {p.get("name") for p in route_pois}
                    seeds = [s for s in seeds if s["name"] not in existing]
                    route_pois = seeds + route_pois
                    meta["seed_poi_count"] = len(seeds)
                    logging.info("注入种子点 %d 个", len(seeds))
            except Exception as e:
                logging.warning("种子点注入失败，忽略：%s", e)

        if not route_pois:
            return ({
                "success": True,
                "message": "这条路线沿途暂时没找到合适的打卡点，随心走走也不错",
                "route_style": route_style,
                "ambience_profile": resolve_ambience_profile(poi_type, ambience_profile),
                # 与前端约定的空结果字段结构
                "path": shortest_route["route_points"],
                "distance": shortest_route["total_distance"],
                "duration": shortest_route["total_duration"],
                "pois": [],
                "original_route": {
                    "distance": shortest_route["total_distance"],
                    "duration": shortest_route["total_duration"],
                    "route_points": shortest_route["route_points"]
                },
                "filtered_pois": [],
                "new_route": {}
            }, 200, meta)

        base_route_points = shortest_route["route_points"]
        shortest_walk_min = shortest_route["total_duration"]
        distance_est_m = float(shortest_route.get("total_distance") or 0)
        max_poi_count = compute_max_poi_count(
            plan_time, shortest_walk_min, visit_pace,
        )

        filtered_pois = filter_poi_for_route(
            route_pois,
            plan_time,
            shortest_walk_min,
            route_style,
            route_points=base_route_points,
            end=end,
            detour_mode=detour_mode,
            visit_pace=visit_pace,
            distance_m=distance_est_m,
        )
        filtered_pois = _ensure_seed_pois_retained(
            filtered_pois, route_pois, max_poi_count, base_route_points,
        )
        trim_relaxed = detour_mode
        if end and filtered_pois:
            filtered_pois = trim_backtrack_pois_toward_end(
                filtered_pois, end, route_style, base_route_points,
                relaxed=trim_relaxed,
            )
            filtered_pois = _ensure_seed_pois_retained(
                filtered_pois, route_pois, max_poi_count, base_route_points,
            )

        seed_names = [p.get("name") for p in filtered_pois if p.get("is_seed") and p.get("name")]
        if seed_names:
            meta["seed_matched_names"] = seed_names

        walk_est = estimate_chained_walk_minutes(
            start, end, filtered_pois, shortest_walk_min, base_route_points
        )
        filtered_pois = try_fill_pois_for_plan_time(
            filtered_pois,
            route_pois,
            plan_time,
            walk_est,
            max_poi_count,
            route_style,
            base_route_points,
            end,
            detour_mode,
            start=start,
            shortest_walk_min=shortest_walk_min,
            visit_pace=visit_pace,
            distance_m=distance_est_m,
        )
        if end and filtered_pois:
            filtered_pois = trim_backtrack_pois_toward_end(
                filtered_pois, end, route_style, base_route_points,
                relaxed=trim_relaxed,
            )
            tail_min_keep = compute_min_poi_count(
                plan_time, detour_mode, max_poi_count, visit_pace,
                distance_m=distance_est_m,
            )
            filtered_pois = ensure_last_poi_near_end(
                filtered_pois,
                end,
                base_route_points,
                visit_pace=visit_pace,
                min_keep=tail_min_keep,
            )

        meta["plan_stage"] = "build_route"
        try:
            new_route = generate_new_route(
                start, end, filtered_pois, route_points=base_route_points,
                plan_time=plan_time, visit_pace=visit_pace,
            )
        except AmapQuotaError:
            raise

        new_route_valid = (new_route.get("new_route_points") and
                          len(new_route.get("new_route_points", [])) > 0 and
                          new_route.get("new_total_distance", 0) > 0)

        route_points = new_route["new_route_points"] if new_route_valid else shortest_route["route_points"]
        total_distance = new_route["new_total_distance"] if new_route_valid else shortest_route["total_distance"]
        total_duration = new_route["new_total_duration"] if new_route_valid else shortest_route["total_duration"]

        stay_hint = ""
        if filtered_pois:
            filtered_pois = mark_optional_pois(filtered_pois, visit_pace)
            filtered_pois, stay_hint, _free_hint = allocate_poi_stay_times(
                filtered_pois,
                plan_time,
                total_duration,
                poi_type=poi_type,
                ambience_profile=resolve_ambience_profile(poi_type, ambience_profile),
                visit_pace=visit_pace,
            )

        for p in filtered_pois:
            p.pop("_route_progress_m", None)
            p.pop("_dist_to_end_m", None)
            p.pop("_fill_added", None)

        time_fields = _plan_time_response_fields(
            plan_time, total_duration, filtered_pois,
        )
        optional_count = sum(1 for p in filtered_pois if p.get("optional"))
        degraded_route = not new_route_valid
        route_tip = build_user_route_tip(
            mode="route",
            poi_count=len(filtered_pois),
            end_address=end_address,
            detour_mode=detour_mode,
            route_style=route_style,
            route_waypoints_truncated=bool(new_route.get("route_waypoints_truncated")),
            degraded_route=degraded_route,
            stay_hint=stay_hint,
            optional_poi_count=optional_count,
            plan_time_min=plan_time,
            activity_total_min=time_fields["activity_total_min"],
            free_time_min=time_fields["free_time_min"],
        )

        meta["plan_stage"] = "complete"
        return ({
            "success": True,
            "mode": "route",
            "message": "路线规划成功" if not degraded_route else "已生成基础路线（部分地图服务受限）",
            "route_tip": route_tip,
            "degraded_route": degraded_route,
            "plan_time_min": plan_time,
            **time_fields,
            "detour_mode": detour_mode,
            "route_style": route_style,
            "visit_pace": visit_pace,
            "ambience_profile": resolve_ambience_profile(poi_type, ambience_profile),
            "path": route_points,
            "distance": total_distance,
            "duration": total_duration,
            "pois": filtered_pois,
            "original_route": {
                "start": start_address,
                "end": end_address,
                "distance_m": shortest_route["total_distance"],
                "duration_min": shortest_route["total_duration"],
                "route_points": shortest_route["route_points"]
            },
            "filtered_pois": filtered_pois,
            "new_route": {
                "waypoints_count": len(new_route["waypoints"]),
                "walk_distance_m": new_route["new_total_distance"],
                "walk_duration_min": new_route["new_walk_duration"],
                "total_duration_min": new_route["new_total_duration"],
                "route_points": new_route["new_route_points"],
                "warning": new_route.get("warning", "")
            }
        }, 200, meta)

    except AmapQuotaError as qe:
        logging.warning("高德配额限流：%s", qe)
        return ({
            "success": False,
            "message": (
                "高德地图请求过于频繁，请约 30 秒后再试。"
                "若持续出现，请缩短路线或稍后再规划。"
            ),
            "retry_after": getattr(qe, "retry_after", 30),
            "quota_exceeded": True,
        }, 429, meta)
    except Exception as e:
        logging.error(f"系统异常：{str(e)}", exc_info=True)
        return ({
            "success": False,
            "message": "服务开小差了，请稍后再试"
        }, 500, meta)

