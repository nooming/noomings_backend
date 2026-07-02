# -*- coding: utf-8 -*-
"""高德 Web 服务：TTL 缓存、并发限流、CUQPS 退避。"""
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

import requests

AMAP_KEY = os.environ.get("AMAP_KEY", "").strip()
AMAP_CACHE_TTL_SEC = int(os.environ.get("AMAP_CACHE_TTL_SEC", "1800"))
AMAP_MAX_CONCURRENT = int(os.environ.get("AMAP_MAX_CONCURRENT", "4"))
AMAP_CUQPS_BACKOFF_SEC = float(os.environ.get("AMAP_CUQPS_BACKOFF_SEC", "1.2"))

_amap_semaphore = threading.Semaphore(max(1, AMAP_MAX_CONCURRENT))
_cache: Dict[str, Tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_last_amap_info_local = threading.local()


def _set_last_amap_info(info: str) -> None:
    _last_amap_info_local.info = (info or "").strip()


def consume_last_amap_info() -> str:
    """取走上一次 api_request_with_retry 失败时的高德 info（线程局部）。"""
    return getattr(_last_amap_info_local, "info", "") or ""


def clear_last_amap_info() -> None:
    _set_last_amap_info("")


class AmapQuotaError(Exception):
    """高德 QPS/配额超限。"""

    def __init__(self, message: str = "", retry_after: int = 30):
        super().__init__(message or "高德请求过于频繁，请稍后再试")
        self.retry_after = retry_after


def get_amap_key() -> str:
    """始终读当前环境变量（避免 import 早于 load_dotenv 时缓存为空）。"""
    return os.environ.get("AMAP_KEY", "").strip() or AMAP_KEY


def _cache_key(url: str, params: dict) -> str:
    safe = {k: v for k, v in params.items() if k != "key"}
    raw = url + "|" + json.dumps(safe, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[dict]:
    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)
        if not entry:
            return None
        expires, data = entry
        if now > expires:
            _cache.pop(key, None)
            return None
        return data


def _cache_set(key: str, data: dict) -> None:
    with _cache_lock:
        _cache[key] = (time.time() + AMAP_CACHE_TTL_SEC, data)
        if len(_cache) > 2000:
            oldest = sorted(_cache.items(), key=lambda x: x[1][0])[:500]
            for k, _ in oldest:
                _cache.pop(k, None)


def _is_quota_error(data: Optional[dict]) -> bool:
    if not data:
        return False
    info = (data.get("info") or "").upper()
    return "CUQPS" in info or "QPS" in info or "EXCEEDED" in info


def api_request_with_retry(
        url: str,
        params: dict,
        max_retries: int = 3,
        timeout: int = 30,
        use_cache: bool = True) -> Optional[dict]:
    """统一高德 GET：缓存 + 信号量限流 + CUQPS 退避。"""
    key = os.environ.get("AMAP_KEY", AMAP_KEY).strip() if not params.get("key") else params["key"]
    if not key:
        logging.error("未配置 AMAP_KEY")
        _set_last_amap_info("未配置 AMAP_KEY")
        return None

    clear_last_amap_info()
    req_params = dict(params)
    req_params["key"] = key

    ck = _cache_key(url, req_params) if use_cache else None
    if ck:
        cached = _cache_get(ck)
        if cached is not None:
            return cached

    last_quota = False
    for retry in range(max_retries):
        try:
            with _amap_semaphore:
                resp = requests.get(url, params=req_params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "1":
                if ck:
                    _cache_set(ck, data)
                clear_last_amap_info()
                return data

            info = (data.get("info") or "未知错误").strip()
            _set_last_amap_info(info)
            if _is_quota_error(data):
                last_quota = True
                wait = AMAP_CUQPS_BACKOFF_SEC * (2 ** retry)
                logging.warning(
                    "高德限流，退避 %.1fs（%d/%d）：%s",
                    wait, retry + 1, max_retries, info,
                )
                time.sleep(wait)
                continue

            logging.warning(
                "API返回错误码，重试%d/%d：%s",
                retry + 1, max_retries, info,
            )
            time.sleep(0.3)
        except requests.exceptions.Timeout:
            _set_last_amap_info("请求超时")
            logging.warning("API请求超时，重试%d/%d", retry + 1, max_retries)
            time.sleep(0.5)
        except requests.exceptions.RequestException as e:
            _set_last_amap_info(str(e))
            logging.warning("API请求异常，重试%d/%d：%s", retry + 1, max_retries, e)
            time.sleep(0.5)
        except Exception as e:
            _set_last_amap_info(str(e))
            logging.error("API请求未知错误：%s", e)
            break

    if last_quota:
        raise AmapQuotaError(retry_after=30)
    if not getattr(_last_amap_info_local, "info", ""):
        _set_last_amap_info("未知错误")
    return None


def around_cache_key(lng: float, lat: float, radius: int, keywords: str, city: str = "") -> str:
    grid_lng = round(lng, 3)
    grid_lat = round(lat, 3)
    return f"around|{grid_lng}|{grid_lat}|{radius}|{keywords}|{city}"
