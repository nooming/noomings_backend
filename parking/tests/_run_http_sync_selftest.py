# -*- coding: utf-8 -*-
import copy
import json
import time
import urllib.request
from pathlib import Path

FIX = Path(__file__).resolve().parent / "fixtures" / "default-scenario.json"
API = "http://127.0.0.1:5000/api/parking/simulate-rolling"


def through(base, i):
    n = i + 1
    one = copy.deepcopy(base)
    one["n_veh"] = n
    one["entrance_mode"] = "fixed"
    arr = (base.get("vehicle_arrival_sec") or [])[:n]
    while len(arr) < n:
        arr.append(len(arr) * 2)
    one["vehicle_arrival_sec"] = [max(0, float(x)) for x in arr]
    one["vehicle_destinations"] = (base.get("vehicle_destinations") or [])[:n]
    one["vehicle_entrances"] = (base.get("vehicle_entrances") or [])[:n]
    return one, arr


def main():
    base = json.loads(FIX.read_text(encoding="utf-8"))
    for i in (0, 1, 5):
        sc, arr = through(base, i)
        payload = {
            "scenario": sc,
            "schedule": {
                "mode": "explicit",
                "arrivals_sec": arr,
                "count": sc["n_veh"],
                "entrance_capacity": 1,
                "realistic": True,
            },
            "async": False,
        }
        t0 = time.perf_counter()
        req = urllib.request.Request(
            API,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        out = json.loads(urllib.request.urlopen(req, timeout=600).read().decode("utf-8"))
        elapsed = time.perf_counter() - t0
        vc = (out.get("timeline") or {}).get("stats", {}).get("vehicle_count")
        print(
            f"车1-{i + 1} n={sc['n_veh']} {elapsed:.1f}s success={out.get('success')} vehicle_count={vc}"
        )


if __name__ == "__main__":
    main()
