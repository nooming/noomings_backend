# -*- coding: utf-8 -*-
"""停留释放后滚动分配可复用车位（车数可大于物理车位）。"""
import copy
import json
from pathlib import Path

import pytest

from parking.core.simulator.rolling import run_rolling_simulation

FIX = Path(__file__).resolve().parent / "fixtures" / "default-scenario.json"


def _load_scenario():
    s = json.loads(FIX.read_text(encoding="utf-8"))
    s["entrance_mode"] = "fixed"
    return s


@pytest.mark.skipif(not FIX.is_file(), reason="default scenario missing")
def test_dwell_enables_slot_reuse_in_rolling():
    base = _load_scenario()
    n_slot = len(base["slots"])
    over = n_slot + 3
    sc = copy.deepcopy(base)
    sc["n_veh"] = over
    arrivals = [float(i * 400) for i in range(over)]
    common = {
        "mode": "explicit",
        "arrivals_sec": arrivals,
        "count": over,
        "entrance_capacity": 1,
        "realistic": False,
    }
    without_dwell = run_rolling_simulation(sc, schedule=common)
    assert without_dwell.get("success")
    assert len(without_dwell["result"]["assign"]) == n_slot

    with_dwell = run_rolling_simulation(sc, schedule={**common, "dwell_min": 2})
    assert with_dwell.get("success"), with_dwell.get("message")
    assign = with_dwell["result"]["assign"]
    assert len(assign) == over
    assert len(set(assign)) < len(assign)
