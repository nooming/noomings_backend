# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest

from parking.core.simulator.entrance_schedule import schedule_drive_times
from parking.core.simulator.engine import run_simulation
from parking.core.optimizer.run_optimize import run_optimize

FIX = Path(__file__).resolve().parent / "fixtures" / "default-scenario.json"


@pytest.mark.skipif(not FIX.is_file(), reason="default scenario missing")
def test_entrance_capacity_queues_single_gate():
    starts, ends = schedule_drive_times(
        [0, 0, 0],
        [10, 10, 10],
        entrance_capacity=1,
        entrance_indices=[0, 0, 0],
    )
    assert starts[0] == 0
    assert starts[1] == 10
    assert starts[2] == 20
    assert ends[2] == 30


def test_two_entrances_parallel():
    starts, _ = schedule_drive_times(
        [0, 0, 0],
        [10, 10, 10],
        entrance_capacity=1,
        entrance_indices=[0, 1, 0],
    )
    assert starts[0] == 0
    assert starts[1] == 0
    assert starts[2] == 10


@pytest.mark.skipif(not FIX.is_file(), reason="default scenario missing")
def test_realistic_sim_has_wait_with_burst():
    scenario = json.loads(FIX.read_text(encoding="utf-8"))
    result = run_optimize(scenario, method="exact")
    schedule = {"mode": "burst", "realistic": True, "entrance_capacity": 1}
    tl = run_simulation(result, schedule=schedule)
    assert tl["stats"]["peak_queue"] >= 1
    assert tl["stats"]["avg_wait_until_drive"] > 0
