# -*- coding: utf-8 -*-
"""逐车调试：累积滚动 + 预计算缓存（自测）。"""
import copy
import json
import time
from pathlib import Path

import pytest

from parking.core.optimizer.cost_matrix import clear_precompute_cache, precompute_from_normalized
from parking.core.optimizer.scenario_normalize import normalize_scenario
from parking.core.simulator.rolling import run_rolling_simulation

FIX = Path(__file__).resolve().parent / "fixtures" / "default-scenario.json"


def _load_scenario():
    s = json.loads(FIX.read_text(encoding="utf-8"))
    s["entrance_mode"] = "fixed"
    return s


def _through_index_scenario(base, vehicle_index):
    """与前端 buildStepScenarioThroughIndex 一致。"""
    i = max(0, int(vehicle_index))
    n = min(i + 1, max(1, int(base.get("n_veh") or 1)))
    one = copy.deepcopy(base)
    one["n_veh"] = n
    one["entrance_mode"] = "fixed"
    one["vehicle_destinations"] = (base.get("vehicle_destinations") or [])[:n]
    one["vehicle_entrances"] = (base.get("vehicle_entrances") or [])[:n]
    one["vehicle_requirements"] = (base.get("vehicle_requirements") or [])[:n]
    while len(one["vehicle_requirements"]) < n:
        one["vehicle_requirements"].append("normal")
    arr = (base.get("vehicle_arrival_sec") or [])[:n]
    while len(arr) < n:
        arr.append(len(arr) * 2)
    one["vehicle_arrival_sec"] = [max(0, float(x)) for x in arr]
    return one, one["vehicle_arrival_sec"]


@pytest.mark.skipif(not FIX.is_file(), reason="default scenario missing")
def test_precompute_cache_shared_across_n_veh():
    clear_precompute_cache()
    base = normalize_scenario(_load_scenario())
    s1, _ = _through_index_scenario(base, 0)
    s2, _ = _through_index_scenario(base, 5)
    s1 = normalize_scenario(s1)
    s2 = normalize_scenario(s2)
    t0 = time.perf_counter()
    precompute_from_normalized(s1)
    cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    precompute_from_normalized(s2)
    warm = time.perf_counter() - t0
    assert warm < cold * 0.05 or warm < 0.5, f"cache miss? cold={cold:.2f}s warm={warm:.2f}s"


@pytest.mark.skipif(not FIX.is_file(), reason="default scenario missing")
def test_cumulative_rolling_vehicle_counts():
    base = _load_scenario()
    for idx, expect_n in [(0, 1), (2, 3), (5, 6)]:
        sc, arrivals = _through_index_scenario(base, idx)
        schedule = {
            "mode": "explicit",
            "arrivals_sec": arrivals,
            "count": expect_n,
            "entrance_capacity": 1,
            "realistic": True,
        }
        out = run_rolling_simulation(sc, schedule=schedule)
        assert out.get("success"), out.get("message")
        tl = out.get("timeline") or {}
        assert tl.get("stats", {}).get("vehicle_count") == expect_n
        last = (tl.get("frames") or [])[-1]
        assert len(last.get("vehicles") or []) == expect_n


@pytest.mark.skipif(not FIX.is_file(), reason="default scenario missing")
def test_incremental_prefix_assign():
    base = _load_scenario()
    sc, arrivals = _through_index_scenario(base, 2)
    schedule_full = {
        "mode": "explicit",
        "arrivals_sec": arrivals,
        "count": 3,
        "entrance_capacity": 1,
        "realistic": False,
    }
    full = run_rolling_simulation(sc, schedule=schedule_full)
    prefix = full["result"]["assign"][:2]
    schedule_inc = {**schedule_full, "prefix_assign": prefix}
    inc = run_rolling_simulation(sc, schedule=schedule_inc)
    assert inc.get("success")
    assert inc["result"]["assign"][:2] == prefix


def test_cumulative_rolling_distinct_slot_assignments():
    base = _load_scenario()
    sc, arrivals = _through_index_scenario(base, 2)
    schedule = {
        "mode": "explicit",
        "arrivals_sec": arrivals,
        "count": 3,
        "entrance_capacity": 1,
        "realistic": False,
    }
    out = run_rolling_simulation(sc, schedule=schedule)
    assign = out["result"]["assign"]
    assert len(assign) == 3
    assert len(set(assign)) == 3
