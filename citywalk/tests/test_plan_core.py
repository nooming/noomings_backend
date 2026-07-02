# -*- coding: utf-8 -*-
import unittest

from citywalk.core.planning.plan_core import estimate_chained_walk_minutes, validate_span_only
from citywalk.core.planning.plan_budget import compute_max_sample_points, cap_waypoints_for_walking

class TestPlanCore(unittest.TestCase):
    def test_validate_span_shanghai(self):
        start = (121.506, 31.282)
        end = (121.500, 31.240)
        ok, _ = validate_span_only(start, end)
        self.assertTrue(ok)

    def test_validate_span_cross_city(self):
        start = (121.47, 31.23)
        end = (116.40, 39.90)
        ok, msg = validate_span_only(start, end)
        self.assertFalse(ok)
        self.assertIn("超限", msg)

    def test_estimate_chained_walk(self):
        start = (121.506, 31.282)
        end = (121.500, 31.240)
        pois = [
            {"location": [121.51, 31.27], "_route_progress_m": 1000},
            {"location": [121.50, 31.25], "_route_progress_m": 3000},
        ]
        est = estimate_chained_walk_minutes(start, end, pois, 12)
        self.assertGreaterEqual(est, 12)

    def test_estimate_chained_walk_with_route_points(self):
        start = (121.506, 31.282)
        end = (121.500, 31.240)
        route_pts = [start, (121.508, 31.260), end]
        pois = [
            {"location": [121.50, 31.25], "final_score": 1.0, "dist_to_route": 0},
            {"location": [121.51, 31.27], "final_score": 9.0, "dist_to_route": 0},
        ]
        est = estimate_chained_walk_minutes(start, end, pois, 10, route_points=route_pts)
        self.assertGreaterEqual(est, 10)

    def test_sample_points_budget(self):
        self.assertEqual(compute_max_sample_points(60, False), 6)
        self.assertLessEqual(compute_max_sample_points(120, True), 12)

    def test_cap_waypoints(self):
        wps = list(range(10))
        capped, truncated = cap_waypoints_for_walking(wps)
        self.assertTrue(truncated)
        self.assertEqual(len(capped), 5)

if __name__ == "__main__":
    unittest.main()
