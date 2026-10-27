# -*- coding: utf-8 -*-
from parking.core.simulator.schedule_parse import build_arrivals


def test_poisson_arrivals_deterministic_with_seed():
    a = build_arrivals(5, {"mode": "poisson", "lambda": 0.05, "seed": 99})
    b = build_arrivals(5, {"mode": "poisson", "lambda": 0.05, "seed": 99})
    assert a == b
    assert len(a) == 5
    assert a[0] > 0


def test_normal_gap_starts_at_zero():
    a = build_arrivals(4, {"mode": "normal_gap", "mean_gap_sec": 20, "sigma_gap_sec": 2, "seed": 1})
    assert a[0] == 0.0
    assert all(a[i] <= a[i + 1] for i in range(len(a) - 1))
