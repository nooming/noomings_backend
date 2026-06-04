"""简易请求限流（按 IP）。"""

import time
from collections import defaultdict
from typing import Dict, List

WINDOW_SEC = 60
MAX_REQUESTS_PER_WINDOW = 30

_buckets: Dict[str, List[float]] = defaultdict(list)


def allow_request(client_ip: str) -> bool:
    now = time.time()
    bucket = _buckets[client_ip]
    _buckets[client_ip] = [t for t in bucket if now - t < WINDOW_SEC]
    if len(_buckets[client_ip]) >= MAX_REQUESTS_PER_WINDOW:
        return False
    _buckets[client_ip].append(now)
    return True
