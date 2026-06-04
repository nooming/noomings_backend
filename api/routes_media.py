# -*- coding: utf-8 -*-
"""Flask 路由：/search_image、/locate_city。"""
import logging
from typing import Optional

import requests
from flask import Blueprint, jsonify, request

from lib.amap_client import api_request_with_retry
from lib.geocoding import get_city_from_location
from planning.runtime import AMAP_KEY, AMAP_STATIC_MAP_KEY

bp = Blueprint("cw_media", __name__)

def get_district_by_coords(lng: float, lat: float) -> dict:
    """通过坐标逆地理编码，精确到区/县级"""
    url = "https://restapi.amap.com/v3/geocode/regeo"
    params = {
        "location": f"{lng},{lat}",
        "extensions": "base",
        "output": "json"
    }
    try:
        data = api_request_with_retry(url, params)
        if data and data.get("regeocode"):
            comp = data["regeocode"]["addressComponent"]
            city = comp.get("city", "") or comp.get("province", "")
            district = comp.get("district", "")
            township = comp.get("township", "")
            return {
                "city": city.replace("市", ""),
                "district": district.replace("区", "").replace("县", ""),
                "township": township,
                "raw_district": district,  # 保留原始区/县名
            }
    except Exception as e:
        logging.warning(f"逆地理编码失败：{str(e)}")
    return {}


def get_amap_static_map_url(lng: float, lat: float, zoom: int = 15) -> Optional[str]:
    """生成高德卫星静态地图URL（精确到起点坐标，使用专用静态地图Key）"""
    if not lng or not lat:
        return None
    base_url = "https://restapi.amap.com/v3/staticmap"
    # style=7 卫星图，scale=2 高清，添加中心标记点
    marker = f"mid,,A:{lng:.6f},{lat:.6f}"
    params = (
        f"key={AMAP_STATIC_MAP_KEY}"
        f"&location={lng:.6f},{lat:.6f}"
        f"&zoom={zoom}"
        f"&size=1600*900"
        f"&scale=2"
        f"&style=7"
        f"&markers={marker}"
    )
    return f"{base_url}?{params}"


def smart_image_search(lng: float = None, lat: float = None, city: str = "") -> Optional[str]:
    """生成分享图背景：直接使用高德静态地图API（按起点坐标取卫星静态图）"""
    if lng and lat:
        result = get_amap_static_map_url(lng, lat)
        if result:
            logging.info(f"使用高德卫星地图：lng={lng}, lat={lat}")
            return result
    return None


def fetch_image_as_data_url(url: str) -> Optional[str]:
    """服务端下载图片并转为 base64 data URL，前端可直接用作背景，
    规避高德静态图无 CORS 头导致 html2canvas 画布被污染的问题。"""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/png").split(";")[0].strip()
        if not content_type.startswith("image/"):
            content_type = "image/png"
        import base64
        b64 = base64.b64encode(resp.content).decode("ascii")
        return f"data:{content_type};base64,{b64}"
    except Exception as e:
        logging.warning(f"下载静态地图失败：{str(e)}")
        return None

@bp.route('/search_image', methods=['POST', 'OPTIONS'])
def search_location_image():
    """搜索地点美图接口（支持坐标精确到区/县级）"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    try:
        data = request.get_json(silent=True) or {}
        city = data.get("city", "").strip()
        poi_name = data.get("poi_name", "").strip()   # 第一个POI名称
        start_lng = data.get("start_lng")              # 起点经度
        start_lat = data.get("start_lat")              # 起点纬度

        # 精确到区/县级：通过坐标逆地理编码
        district_info = {}
        if start_lng and start_lat:
            district_info = get_district_by_coords(float(start_lng), float(start_lat))
            logging.info(f"逆地理编码结果：{district_info}")

        city_name = district_info.get("city") or city or "上海"
        district_name = district_info.get("raw_district") or ""  # 如"浦东新区"

        image_url = smart_image_search(
            lng=float(start_lng) if start_lng else None,
            lat=float(start_lat) if start_lat else None,
            city=city_name
        )

        if image_url:
            # 服务端下载为 data URL，前端 html2canvas 可无污染合成
            image_data_url = fetch_image_as_data_url(image_url)
            return jsonify({
                "success": True,
                "image_url": image_url,
                "image_data_url": image_data_url,
                "district": district_name,
                "city": city_name
            })
        else:
            return jsonify({
                "success": False,
                "message": "未找到相关图片，将使用默认背景"
            }), 404

    except Exception as e:
        logging.error(f"图片搜索接口异常：{str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "图片服务暂时不可用，将使用默认背景"}), 500


@bp.route('/locate_city', methods=['GET', 'OPTIONS'])
def locate_city():
    """IP定位城市接口 - 优先使用前端传递的坐标进行逆地理编码"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True})

    try:
        # 尝试获取前端传递的坐标参数
        lng = request.args.get('lng', type=float)
        lat = request.args.get('lat', type=float)

        # 如果有坐标，使用逆地理编码获取城市
        if lng and lat:
            url = "https://restapi.amap.com/v3/geocode/regeo"
            params = {
                "location": f"{lng},{lat}",
                "extensions": "base",
                "output": "json"
            }

            data = api_request_with_retry(url, params)

            if data and data.get("regeocode"):
                address = data["regeocode"]["addressComponent"]
                city = address.get("city", "")
                province = address.get("province", "")

                # 处理直辖市的情况
                if not city and province in ["北京市", "上海市", "天津市", "重庆市"]:
                    city = province.replace("市", "")

                if city:
                    return jsonify({
                        "success": True,
                        "city": city.replace("市", ""),
                        "province": province,
                        "center": [lng, lat],
                        "source": "browser_geolocation"
                    })

        # 降级：使用高德IP定位API（服务器IP）
        url = "https://restapi.amap.com/v3/ip"
        params = {
            "output": "json"
        }

        data = api_request_with_retry(url, params)

        if data and data.get("city"):
            city = data.get("city", "").replace("市", "")
            province = data.get("province", "")
            rectangle = data.get("rectangle", "")

            # 解析矩形区域获取中心点坐标
            center_lng, center_lat = 116.4074, 39.9042
            if rectangle:
                try:
                    coords = rectangle.split(";")
                    if len(coords) == 2:
                        lng1, lat1 = map(float, coords[0].split(","))
                        lng2, lat2 = map(float, coords[1].split(","))
                        center_lng = (lng1 + lng2) / 2
                        center_lat = (lat1 + lat2) / 2
                except (ValueError, AttributeError, IndexError) as e:
                    logging.warning(f"解析IP定位矩形区域坐标失败：{e}")

            return jsonify({
                "success": True,
                "city": city,
                "province": province,
                "center": [center_lng, center_lat],
                "source": "ip_location"
            })
        else:
            # 返回默认城市（北京）
            return jsonify({
                "success": True,
                "city": "北京",
                "province": "北京市",
                "center": [116.4074, 39.9042],
                "source": "default"
            })

    except Exception as e:
        logging.error(f"定位异常：{str(e)}")
        return jsonify({
            "success": True,
            "city": "北京",
            "province": "北京市",
            "center": [116.4074, 39.9042],
            "source": "default"
        })

