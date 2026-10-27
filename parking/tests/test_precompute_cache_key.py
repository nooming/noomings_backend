# -*- coding: utf-8 -*-
from parking.core.optimizer.cost_matrix import _precompute_cache_key


def test_precompute_cache_key_ignores_vehicle_fields():
    base = {
        "lot": {"width": 100, "height": 80},
        "slots": [[1, 2, 0]],
        "buildings": [[10, 10]],
        "entrances": [[0, 0]],
        "n_veh": 12,
        "vehicle_destinations": [0, 1, 2],
        "vehicle_arrival_sec": [0, 2, 4],
    }
    one_veh = {**base, "n_veh": 1, "vehicle_destinations": [2], "vehicle_arrival_sec": [6]}
    assert _precompute_cache_key(base) == _precompute_cache_key(one_veh)
