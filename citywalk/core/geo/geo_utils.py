# -*- coding: utf-8 -*-
"""地理小工具（无外部 API）。"""
import ipaddress
import re
from math import radians, cos, sin, asin, sqrt
from typing import Optional

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


def _strip_optional_port(ip: str) -> str:
    """去掉 IPv4:port；保留裸 IPv6 / [IPv6]:port。"""
    s = (ip or "").strip()
    if not s:
        return ""
    if s.startswith("[") and "]" in s:
        return s[1 : s.index("]")]
    if s.count(":") == 1:
        host, _, port = s.rpartition(":")
        if port.isdigit():
            return host
    return s


def is_public_ip(ip: str) -> bool:
    """True only for globally routable addresses (skip loopback / private / link-local)."""
    try:
        addr = ipaddress.ip_address(_strip_optional_port(ip))
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def first_public_ip(*candidates: Optional[str]) -> Optional[str]:
    """从 X-Forwarded-For / X-Real-IP / remote_addr 候选中取第一个公网 IP。"""
    for raw in candidates:
        if not raw:
            continue
        for part in str(raw).split(","):
            ip = _strip_optional_port(part)
            if is_public_ip(ip):
                return ip
    return None
