# -*- coding: utf-8 -*-
"""到达过程配置 → 每车到达时刻（秒）。"""
import random


def _schedule_rng(schedule):
    seed = schedule.get("seed")
    if seed is not None and str(seed).strip() != "":
        return random.Random(int(seed))
    return random.Random()


def build_arrivals(n, schedule=None):
    if n <= 0:
        return []
    sched = schedule or {}
    mode = str(sched.get("mode") or "uniform").strip().lower()
    if mode == "explicit":
        raw = sched.get("arrivals_sec") or sched.get("arrivals") or []
        out = []
        for i in range(n):
            if i < len(raw):
                try:
                    out.append(max(0.0, float(raw[i])))
                except (TypeError, ValueError):
                    out.append(i * 60.0)
            else:
                out.append(out[-1] + 60.0 if out else i * 60.0)
        return out
    if mode == "burst":
        gap = float(sched.get("burst_gap_sec") or 2.0)
        return [i * gap for i in range(n)]
    if mode == "poisson":
        rng = _schedule_rng(sched)
        rate = float(sched.get("lambda") or sched.get("arrival_lambda") or 0.04)
        rate = max(1e-6, rate)
        t = 0.0
        out = []
        for _ in range(n):
            t += rng.expovariate(rate)
            out.append(round(t, 3))
        return out
    if mode == "normal_gap":
        rng = _schedule_rng(sched)
        mean = float(sched.get("mean_gap_sec") or 30.0)
        sigma = max(0.0, float(sched.get("sigma_gap_sec") or 10.0))
        t = 0.0
        out = [0.0]
        for _ in range(1, n):
            gap = max(0.5, rng.gauss(mean, sigma))
            t += gap
            out.append(round(t, 3))
        return out
    duration_s = float(sched.get("duration_min") or 20) * 60.0
    step = duration_s / max(1, n)
    return [i * step for i in range(n)]


def sim_options(schedule=None):
    sched = schedule or {}
    realistic = sched.get("realistic")
    if realistic is None:
        realistic = True
    cap = int(sched.get("entrance_capacity") or 1)
    cap = max(1, min(8, cap))
    dwell_min = float(sched.get("dwell_min") or sched.get("default_stay_min") or 0)
    dwell_s = max(0.0, dwell_min) * 60.0
    if sched.get("stay_after_walk_sec") is not None:
        dwell_s = max(0.0, float(sched.get("stay_after_walk_sec") or 0))
    return {"realistic": bool(realistic), "entrance_capacity": cap, "dwell_s": dwell_s}
