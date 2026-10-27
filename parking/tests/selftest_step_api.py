# -*- coding: utf-8 -*-
"""HTTP 自测 simulate-rolling（需本地 Flask :5000）。非 pytest 用例，直接 python 运行。"""
import copy
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

FIX = Path(__file__).resolve().parent / "fixtures" / "default-scenario.json"
API = "http://127.0.0.1:5000/api/parking/simulate-rolling"


def _through_index_scenario(base, vehicle_index):
    i = max(0, int(vehicle_index))
    n = min(i + 1, max(1, int(base.get("n_veh") or 1)))
    one = copy.deepcopy(base)
    one["n_veh"] = n
    one["entrance_mode"] = "fixed"
    one["vehicle_destinations"] = (base.get("vehicle_destinations") or [])[:n]
    one["vehicle_entrances"] = (base.get("vehicle_entrances") or [])[:n]
    arr = (base.get("vehicle_arrival_sec") or [])[:n]
    while len(arr) < n:
        arr.append(len(arr) * 2)
    one["vehicle_arrival_sec"] = [max(0, float(x)) for x in arr]
    return one, arr


def _post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _poll_job(job_id, max_sec=300):
    url = f"http://127.0.0.1:5000/api/parking/jobs/{job_id}"
    t0 = time.time()
    while time.time() - t0 < max_sec:
        with urllib.request.urlopen(url, timeout=30) as resp:
            job = json.loads(resp.read().decode("utf-8")).get("job") or {}
        st = job.get("status")
        if st == "completed":
            return job.get("result"), time.time() - t0
        if st == "failed":
            raise RuntimeError(job.get("error") or "job failed")
        time.sleep(0.8)
    raise TimeoutError("job poll timeout")


def main():
    if not FIX.is_file():
        print("FAIL: missing fixture", FIX)
        return 1
    try:
        urllib.request.urlopen("http://127.0.0.1:5000/api/health", timeout=3)
    except (urllib.error.URLError, TimeoutError):
        print("SKIP HTTP: backend not on :5000 (core pytest tests still valid)")
        return 0

    base = json.loads(FIX.read_text(encoding="utf-8"))
    timings = []
    for idx in (0, 1, 5):
        sc, arrivals = _through_index_scenario(base, idx)
        n = sc["n_veh"]
        payload = {
            "scenario": sc,
            "schedule": {
                "mode": "explicit",
                "arrivals_sec": arrivals,
                "count": n,
                "entrance_capacity": 1,
                "realistic": True,
            },
            "async": True,
        }
        t0 = time.perf_counter()
        init = _post_json(API, payload)
        if init.get("timeline"):
            elapsed = time.perf_counter() - t0
            out = init
        else:
            out, elapsed = _poll_job(init["job_id"])
        vc = (out.get("timeline") or {}).get("stats", {}).get("vehicle_count")
        ok = vc == n and out.get("success")
        timings.append((idx + 1, n, elapsed, ok, vc))
        print(f"  车1–{idx + 1} (n={n}): {elapsed:.2f}s vehicle_count={vc} ok={ok}")

    if not all(t[3] for t in timings):
        print("FAIL: API cumulative counts")
        return 1
    if len(timings) >= 2 and timings[1][2] > timings[0][2] * 3 + 60:
        print("WARN: 2nd run much slower than 1st (cache may be cold)")
    print("OK: HTTP step cumulative rolling")
    return 0


if __name__ == "__main__":
    sys.exit(main())
