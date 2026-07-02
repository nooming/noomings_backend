# -*- coding: utf-8 -*-
"""离散事件仿真：到达 → 排队 → 驶入 → 停放 → 步行。"""

import math


def _polyline_len(pts):
    d = 0.0
    for i in range(1, len(pts)):
        d += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
    return d


def _interp_polyline(pts, dist):
    if not pts:
        return [0, 0]
    if len(pts) == 1:
        return list(pts[0])
    remain = max(0.0, dist)
    for i in range(1, len(pts)):
        seg = math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        if remain <= seg or i == len(pts) - 1:
            t = remain / seg if seg > 1e-9 else 0
            t = max(0.0, min(1.0, t))
            return [
                pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t,
                pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t,
            ]
        remain -= seg
    return list(pts[-1])


def run_simulation(result, schedule=None, dt=0.5, v_car=10.0, v_walk=1.5):
    """
    schedule: { mode: 'uniform', duration_min: 30, count: n_veh }
    返回 timeline frames + stats
    """
    scenario = result.get("scenario") or {}
    assign = result.get("assign") or []
    breakdown = result.get("vehicle_breakdown") or []
    paths = result.get("paths") or []
    drive_paths = result.get("drive_paths") or []
    entrances = scenario.get("entrances") or [[0, 0]]
    slots = scenario.get("slots") or []
    n = len(breakdown)
    if not n:
        return {"frames": [], "stats": {}, "duration": 0}

    sched = schedule or {"mode": "uniform", "duration_min": 20, "count": n}
    duration_s = float(sched.get("duration_min") or 20) * 60.0
    arrivals = []
    if sched.get("mode") == "burst":
        for i in range(n):
            arrivals.append(i * 2.0)
    else:
        step = duration_s / max(1, n)
        arrivals = [i * step for i in range(n)]

    events = []
    for i, bd in enumerate(breakdown):
        arr = arrivals[i] if i < len(arrivals) else i * 5.0
        drive_t = float(bd.get("drive_time") or 0)
        walk_t = float(bd.get("walk_time") or 0)
        si = int(bd.get("slot_index") or assign[i] if i < len(assign) else 0)
        ei = int(bd.get("entrance_index") or 0)
        ent = entrances[min(ei, len(entrances) - 1)]
        slot = slots[si] if si < len(slots) else [0, 0, 0]
        path = paths[i] if i < len(paths) else [ent, slot[:2]]
        dp_raw = drive_paths[i] if i < len(drive_paths) else None
        if isinstance(dp_raw, list) and len(dp_raw) >= 2:
            drive_path = [[float(p[0]), float(p[1])] for p in dp_raw]
        else:
            drive_path = [list(ent), list(slot[:2])]
        drive_dist = drive_t * v_car
        events.append(
            {
                "vehicle_index": i,
                "arrival": arr,
                "drive_start": arr,
                "drive_end": arr + drive_t,
                "park_at": list(slot[:2]),
                "walk_end": arr + drive_t + walk_t,
                "entrance": list(ent),
                "path": path,
                "drive_path": drive_path,
                "drive_dist": drive_dist,
            }
        )

    end_t = max(e["walk_end"] for e in events)
    frames = []
    t = 0.0
    queue_len_peak = 0
    wait_samples = []

    while t <= end_t + dt:
        vehicles = []
        queue = 0
        occupied = set()
        for ev in events:
            state = "waiting"
            pos = list(ev["entrance"])
            if t < ev["arrival"]:
                state = "pending"
            elif t < ev["drive_start"]:
                state = "queued"
                queue += 1
                wait_samples.append(t - ev["arrival"])
            elif t < ev["drive_end"]:
                state = "driving"
                prog = (t - ev["drive_start"]) / max(1e-6, ev["drive_end"] - ev["drive_start"])
                dp = ev["drive_path"]
                pos = _interp_polyline(dp, prog * _polyline_len(dp))
            elif t < ev["walk_end"]:
                state = "walking"
                prog = (t - ev["drive_end"]) / max(1e-6, ev["walk_end"] - ev["drive_end"])
                pos = _interp_polyline(ev["path"], prog * _polyline_len(ev["path"]))
                occupied.add(ev["vehicle_index"])
            else:
                state = "done"
                pos = ev["path"][-1] if ev["path"] else ev["park_at"]
                occupied.add(ev["vehicle_index"])
            vehicles.append({"index": ev["vehicle_index"], "state": state, "x": pos[0], "y": pos[1]})
        queue_len_peak = max(queue_len_peak, queue)
        frames.append({"t": round(t, 2), "vehicles": vehicles, "queue": queue, "occupied_count": len(occupied)})
        t += dt

    total_times = [ev["walk_end"] - ev["arrival"] for ev in events]
    total_times.sort()
    p95 = total_times[int(0.95 * (len(total_times) - 1))] if total_times else 0
    return {
        "frames": frames,
        "duration": end_t,
        "stats": {
            "peak_queue": queue_len_peak,
            "avg_wait": (sum(wait_samples) / len(wait_samples)) if wait_samples else 0,
            "p95_total_time": p95,
            "vehicle_count": n,
        },
    }
