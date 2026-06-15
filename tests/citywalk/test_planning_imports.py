# -*- coding: utf-8 -*-
"""规划链路：import * 不导出 _ 前缀符号，本测试防止 NameError 回归。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import planning.plan_service as plan_service
import planning.route_engine as route_engine
from planning.poi_selection import _location_grid_key as poi_location_grid_key
from planning.route_engine import _ensure_seed_pois_retained


class TestPlanningImports(unittest.TestCase):
    def test_route_engine_private_symbols(self):
        for name in (
            "_location_grid_key",
            "_attach_route_progress",
            "_order_pois_along_route",
            "_attach_route_progress_and_end",
            "_filter_poi_greedy",
            "_sort_poi_candidates",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(route_engine, name), f"route_engine missing {name}")

    def test_plan_service_ensure_seed_imported(self):
        self.assertTrue(hasattr(plan_service, "_ensure_seed_pois_retained"))
        self.assertIs(plan_service._ensure_seed_pois_retained, _ensure_seed_pois_retained)

    def test_location_grid_key_callable(self):
        key = route_engine._location_grid_key(121.47, 31.23)
        self.assertEqual(key, poi_location_grid_key(121.47, 31.23))

    def test_ensure_seed_pois_retained_callable(self):
        out = _ensure_seed_pois_retained([], [], max_poi_count=0)
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
