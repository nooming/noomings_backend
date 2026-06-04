# -*- coding: utf-8 -*-
"""地理小工具（无外部 API）。"""
import re
from math import radians, cos, sin, asin, sqrt
from typing import Tuple

MAX_CITYWALK_SPAN_M = 25000


def haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


def normalize_city_name(city: str) -> str:
    if not city:
        return ""
    normalized = city.strip().lower().replace(" ", "")
    normalized = re.sub(
        r'(特别行政区|自治州|地区|盟|州|市|区|县|省)$', '', normalized
    )
    return normalized
