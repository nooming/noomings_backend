# -*- coding: utf-8 -*-
"""离散事件仿真：到达 → 排队 → 驶入 → 停放 → 步行。"""

import math

from parking.core.simulator.entrance_schedule import schedule_drive_times
from parking.core.simulator.schedule_parse import build_arrivals, sim_options


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
    schedule:
      mode: uniform | burst | explicit
      duration_min, burst_gap_sec, arrivals_sec
      realistic (default True): 入口通行能力导致排队
      entrance_capacity (default 1): 每个入口同时驶入上限
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

    sched = schedule or {}
    opts = sim_options(sched)
    arrivals = build_arrivals(n, sched)
    drive_durations = [float(bd.get("drive_time") or 0) for bd in breakdown]

    entrance_indices = [
        int(bd.get("entrance_index") or 0) if i < len(breakdown) else 0
        for i, bd in enumerate(breakdown)
    ]
    if opts["realistic"]:
        drive_starts, drive_ends = schedule_drive_times(
            arrivals,
            drive_durations,
            opts["entrance_capacity"],
            entrance_indices=entrance_indices,
        )
    else:
        drive_starts = arrivals[:]
        drive_ends = [arrivals[i] + drive_durations[i] for i in range(n)]

    events = []
    for i, bd in enumerate(breakdown):
        arr = arrivals[i] if i < len(arrivals) else i * 5.0
        drive_t = drive_durations[i]
        walk_t = float(bd.get("walk_time") or 0)
        ds = drive_starts[i]
        de = drive_ends[i]
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
        stay_s = float(opts.get("dwell_s") or 0)
        depart_end = de + walk_t + stay_s
        events.append(
            {
                "vehicle_index": i,
                "arrival": arr,
                "drive_start": ds,
                "drive_end": de,
                "walk_end": de + walk_t,
                "depart_end": depart_end,
                "stay_s": stay_s,
                "slot_index": si,
                "park_at": list(slot[:2]),
                "entrance": list(ent),
                "path": path,
                "drive_path": drive_path,
            }
        )

    end_t = max(max(e["walk_end"], e["depart_end"]) for e in events)
    frames = []
    t = 0.0
    queue_len_peak = 0
    wait_samples = []

    while t <= end_t + dt:
        vehicles = []
        queue = 0
        occupied_slots = set()
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
                occupied_slots.add(ev.get("slot_index", ev["vehicle_index"]))
            elif t < ev["depart_end"]:
                state = "parked"
                pos = ev["path"][-1] if ev["path"] else ev["park_at"]
                occupied_slots.add(ev.get("slot_index", ev["vehicle_index"]))
            else:
                state = "departed"
                pos = ev["path"][-1] if ev["path"] else ev["park_at"]
            vehicles.append({"index": ev["vehicle_index"], "state": state, "x": pos[0], "y": pos[1]})
        queue_len_peak = max(queue_len_peak, queue)
        frames.append(
            {
                "t": round(t, 2),
                "vehicles": vehicles,
                "queue": queue,
                "occupied_count": len(occupied_slots),
            }
        )
        t += dt

    total_times = [ev["walk_end"] - ev["arrival"] for ev in events]
    total_times.sort()
    p95 = total_times[int(0.95 * (len(total_times) - 1))] if total_times else 0
    wait_at_arrival = [ev["drive_start"] - ev["arrival"] for ev in events]
    return {
        "frames": frames,
        "duration": end_t,
        "stats": {
            "peak_queue": queue_len_peak,
            "avg_wait": (sum(wait_samples) / len(wait_samples)) if wait_samples else 0,
            "avg_wait_until_drive": (sum(wait_at_arrival) / len(wait_at_arrival)) if wait_at_arrival else 0,
            "p95_total_time": p95,
            "vehicle_count": n,
            "realistic": opts["realistic"],
            "entrance_capacity": opts["entrance_capacity"],
            "entrance_capacity_per_gate": opts["entrance_capacity"],
            "dwell_s": opts.get("dwell_s") or 0,
        },
    }
