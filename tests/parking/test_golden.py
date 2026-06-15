# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest

from parking.optimizer.run import run_optimize

SCENARIO_PATH = Path(__file__).resolve().parent / "fixtures" / "default-scenario.json"


@pytest.mark.skipif(not SCENARIO_PATH.is_file(), reason="default scenario missing")
def test_golden_exact_gbest():
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    result = run_optimize(scenario, method="exact")
    gbest = float(result.get("gbest_value") or 0)
    assert gbest > 0
    # 默认场景（penalty=0）与历史浏览器验收值对齐（允许 0.1%）
    expected = 618.521623511358
    assert abs(gbest - expected) / expected < 0.001
