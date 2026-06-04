# -*- coding: utf-8 -*-
"""route_engine / poi_selection 导入回归：sqrt、normalize_city_name、route_total_length_m。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planning.route_engine import (
    _detour_extra_sample_points,
    _lateral_offset_points,
    normalize_city_name,
)
from planning.poi_selection import is_poi_in_target_city, select_pois_by_route_segments


class TestRouteEngineDetour(unittest.TestCase):
    def test_lateral_offset_points_returns_two_offsets(self):
        plus, minus = _lateral_offset_points(
            121.48, 31.23, 0.01, 0.02, offset_m=80.0,
        )
        self.assertEqual(len(plus), 2)
        self.assertEqual(len(minus), 2)
        self.assertNotEqual(plus, minus)

    def test_detour_extra_sample_points_no_name_error(self):
        route = [
            (121.470, 31.230),
            (121.475, 31.235),
            (121.480, 31.240),
        ]
        extras = _detour_extra_sample_points(route)
        self.assertGreater(len(extras), 0)
        for pt in extras:
            self.assertEqual(len(pt), 2)

    def test_detour_extra_sample_points_short_route_empty(self):
        self.assertEqual(_detour_extra_sample_points([(121.47, 31.23)]), [])

    def test_normalize_city_name_imported(self):
        self.assertEqual(normalize_city_name("上海市"), "上海")

    def test_is_poi_in_target_city_no_name_error(self):
        poi = {"cityname": "上海市", "name": "测试点"}
        self.assertTrue(is_poi_in_target_city(poi, "上海"))

    def test_select_pois_by_route_segments_no_name_error(self):
        route = [(121.47, 31.23), (121.48, 31.24), (121.49, 31.25)]
        pois = [{
            "name": "A",
            "location": [121.475, 31.235],
            "final_score": 1.0,
            "dist_to_route": 10,
        }]
        out = select_pois_by_route_segments(
            pois,
            route,
            end=route[-1],
            max_poi_count=3,
            min_poi_count=1,
            route_style="balanced",
            detour_mode=False,
        )
        self.assertIsInstance(out, list)


if __name__ == "__main__":
    unittest.main()
