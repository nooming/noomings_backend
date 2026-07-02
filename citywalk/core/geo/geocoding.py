# -*- coding: utf-8 -*-
"""起终点解析与同城校验。"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from citywalk.core.geo.amap_client import api_request_with_retry
from citywalk.core.geo.geo_utils import MAX_CITYWALK_SPAN_M, haversine, normalize_city_name
from citywalk.core.planning.constants import MAX_SEED_GEO_BIAS_M


def _geocode_entry_matches_city(entry: Dict, target_city_norm: str) -> bool:
    if not target_city_norm:
        return True
    for field in ("city", "province", "district"):
        val = entry.get(field) or ""
        val_norm = normalize_city_name(str(val))
        if val_norm and (
            target_city_norm in val_norm or val_norm in target_city_norm
        ):
            return True
    return False


def _geocode_geo_once(
        address: str, city_api: str = "") -> Optional[Tuple[float, float]]:
    if not (address or "").strip():
        return None

    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {"address": address.strip(), "output": "json"}
    if city_api:
        params["city"] = city_api
    target_norm = normalize_city_name(city_api) if city_api else ""

    data = api_request_with_retry(url, params)
    if not data:
        return None

    geocodes = data.get("geocodes", []) or []
    if not geocodes:
        return None

    chosen = None
    if target_norm:
        for entry in geocodes:
            if _geocode_entry_matches_city(entry, target_norm):
                chosen = entry
                break
    if not chosen:
        chosen = geocodes[0]

    loc = chosen.get("location", "")
    if not loc:
        return None
    lng, lat = map(float, loc.split(","))
    return lng, lat


def place_text_search(
        keywords: str,
        city: str = None,
        location: Optional[Tuple[float, float]] = None,
) -> Optional[Tuple[float, float]]:
    if not (keywords or "").strip():
        return None

    city_api = (city or "").strip().replace("市", "")
    url = "https://restapi.amap.com/v3/place/text"
    params = {
        "keywords": keywords.strip(),
        "offset": 10,
        "page": 1,
        "output": "json",
    }
    if city_api:
        params["city"] = city_api
        params["citylimit"] = "true"
    if location and len(location) == 2:
        params["location"] = f"{location[0]},{location[1]}"

    data = api_request_with_retry(url, params)
    if not data:
        return None

    pois = data.get("pois", []) or []
    if not pois:
        return None

    chosen = None
    if city_api:
        for poi in pois:
            cname = (poi.get("cityname") or "").strip()
            cn = normalize_city_name(cname)
            tn = normalize_city_name(city_api)
            if cn and (tn in cn or cn in tn):
                chosen = poi
                break
    if not chosen:
        chosen = pois[0]

    loc = chosen.get("location", "")
    if not loc:
        return None
    lng, lat = map(float, loc.split(","))
    return lng, lat


def infer_city_from_place_keyword(keywords: str) -> Optional[str]:
    if not (keywords or "").strip():
        return None

    url = "https://restapi.amap.com/v3/place/text"
    params = {
        "keywords": keywords.strip(),
        "offset": 5,
        "page": 1,
        "output": "json",
    }
    data = api_request_with_retry(url, params, max_retries=2)
    if not data:
        return None

    pois = data.get("pois", []) or []
    if not pois:
        return None

    cityname = (pois[0].get("cityname") or "").strip()
    if cityname:
        return cityname.replace("市", "")
    return None


def resolve_location_detail(
        address: str, city: str = None) -> Optional[Dict[str, Any]]:
    if not (address or "").strip():
        return None

    addr = address.strip()
    city_api = (city or "").strip().replace("市", "")

    coords = _geocode_geo_once(addr, city_api)
    if coords:
        return {"lng": coords[0], "lat": coords[1], "source": "geo"}

    coords = place_text_search(addr, city_api or None)
    if coords:
        return {"lng": coords[0], "lat": coords[1], "source": "place_text"}

    if city_api:
        prefixed = f"{city_api}市{addr}"
        coords = _geocode_geo_once(prefixed, city_api)
        if coords:
            return {"lng": coords[0], "lat": coords[1], "source": "geo_prefixed"}

    logging.error("地点解析失败：%s（city=%s）", addr, city_api or "全国")
    return None


def resolve_location(
        address: str, city: str = None) -> Optional[Tuple[float, float]]:
    detail = resolve_location_detail(address, city)
    if not detail:
        return None
    return detail["lng"], detail["lat"]


def _route_reference_point(
        route_points: List[Tuple[float, float]],
) -> Optional[Tuple[float, float]]:
    if not route_points:
        return None
    if len(route_points) >= 2:
        a, b = route_points[0], route_points[-1]
        return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    return route_points[0]


def _coords_match_target_city(lng: float, lat: float, city: str) -> bool:
    if not (city or "").strip():
        return True
    resolved = get_city_from_location(lng, lat)
    if not resolved:
        return True
    tn = normalize_city_name(city)
    rn = normalize_city_name(resolved)
    return bool(rn and (tn in rn or rn in tn))


def resolve_seed_location(
        name: str,
        city: Optional[str],
        route_points: List[Tuple[float, float]],
        area: str = "",
        lng: Optional[float] = None,
        lat: Optional[float] = None,
) -> Optional[Tuple[float, float]]:
    """种草点解析：city + 路线中心 bias，过滤距参考点过远的误匹配。"""
    name = (name or "").strip()
    if not name:
        return None
    city_api = (city or "").strip().replace("市", "")
    ref = _route_reference_point(route_points)
    area = (area or "").strip()

    if lng is not None and lat is not None:
        try:
            lng_f, lat_f = float(lng), float(lat)
        except (TypeError, ValueError):
            lng_f = lat_f = None  # type: ignore
        else:
            dist_ok = not ref or haversine(
                lng_f, lat_f, ref[0], ref[1]) <= MAX_SEED_GEO_BIAS_M
            city_ok = not city_api or _coords_match_target_city(
                lng_f, lat_f, city_api)
            if dist_ok and city_ok:
                return lng_f, lat_f
            logging.info(
                "种草点「%s」自带坐标未通过同城/距离校验，改按名称解析",
                name,
            )

    coords = place_text_search(name, city_api or None, location=ref)
    if not coords and city_api:
        biased_name = f"{city_api}{area}{name}".replace("  ", "")
        coords = place_text_search(biased_name, city_api, location=ref)
    if not coords:
        detail = resolve_location_detail(name, city_api or None)
        if detail:
            coords = (detail["lng"], detail["lat"])
    if not coords:
        return None

    lng, lat = coords
    if ref and haversine(lng, lat, ref[0], ref[1]) > MAX_SEED_GEO_BIAS_M:
        logging.info(
            "种草点「%s」距路线参考点 %d 米，超出 %d 米上限，丢弃",
            name, int(haversine(lng, lat, ref[0], ref[1])), MAX_SEED_GEO_BIAS_M,
        )
        return None
    if city_api and not _coords_match_target_city(lng, lat, city_api):
        logging.info("种草点「%s」解析坐标不在目标城市 %s，丢弃", name, city_api)
        return None
    return lng, lat


def geocode_address(
        address: str, city: str = None) -> Optional[Tuple[float, float]]:
    return resolve_location(address, city)


def get_geo_code(address: str, city: str = None) -> Optional[Tuple[float, float]]:
    return resolve_location(address, city)


def get_city_from_location(lng: float, lat: float) -> Optional[str]:
    url = "https://restapi.amap.com/v3/geocode/regeo"
    params = {
        "location": f"{lng},{lat}",
        "extensions": "base",
        "output": "json",
    }
    try:
        data = api_request_with_retry(url, params, max_retries=2, use_cache=True)
        if data and data.get("regeocode"):
            comp = data["regeocode"]["addressComponent"]
            city = comp.get("city", "") or comp.get("province", "")
            return city.replace("市", "") if city else None
    except Exception as e:
        logging.warning("逆地理编码获取城市失败：%s", e)
    return None


def validate_citywalk_endpoints(
        start: Tuple[float, float],
        end: Tuple[float, float],
        target_city: Optional[str] = None) -> Tuple[bool, str]:
    span_m = haversine(start[0], start[1], end[0], end[1])
    if span_m > MAX_CITYWALK_SPAN_M:
        km = int(span_m / 1000)
        return (
            False,
            f"起终点相距约 {km} 公里，超出 Citywalk 范围。"
            "请确认在同一座城市内的两个地点。",
        )

    if target_city:
        target_norm = normalize_city_name(target_city)
        start_city = get_city_from_location(start[0], start[1])
        end_city = get_city_from_location(end[0], end[1])
        if start_city and end_city:
            sc = normalize_city_name(start_city)
            ec = normalize_city_name(end_city)
            if sc != ec and target_norm not in (sc, ec):
                return (
                    False,
                    "起终点似乎不在同一座城市，请检查城市与地标是否匹配。",
                )
            if sc != ec:
                return (
                    False,
                    f"起点在{start_city}、终点在{end_city}，请改为同城起终点。",
                )
    return True, ""
