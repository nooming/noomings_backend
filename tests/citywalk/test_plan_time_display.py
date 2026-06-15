# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from planning.plan_budget import cap_waypoints_for_walking, max_route_waypoints
from planning.plan_service import _plan_time_response_fields
from planning.poi_selection import allocate_poi_stay_times, compute_activity_and_free_min
from planning.route_tip import build_user_route_tip


class TestPlanTimeDisplay(unittest.TestCase):
    def test_activity_plus_free_equals_plan_checkin(self):
        pois = [{"name": f"p{i}", "stay_time": 10} for i in range(5)]
        activity, free_m = compute_activity_and_free_min(100, pois, 240)
        self.assertEqual(activity, 150)
        self.assertEqual(free_m, 90)
        self.assertEqual(activity + free_m, 240)

    def test_plan_time_response_fields(self):
        pois = [{"stay_time": 10}, {"stay_time": 10}]
        fields = _plan_time_response_fields(240, 100, pois)
        self.assertEqual(fields["activity_total_min"], 120)
        self.assertEqual(fields["free_time_min"], 120)
        self.assertEqual(fields["estimated_total_min"], 120)
        self.assertEqual(fields["time_breakdown"]["walk_min"], 100)
        self.assertEqual(fields["time_breakdown"]["stay_min"], 20)

    def test_route_tip_explains_free_time_not_gap(self):
        tip = build_user_route_tip(
            mode="route",
            poi_count=5,
            plan_time_min=240,
            activity_total_min=146,
            free_time_min=94,
        )
        self.assertIn("自由安排", tip)
        self.assertIn("146", tip)
        self.assertIn("240", tip)
        self.assertNotIn("比计划少", tip)

    def test_checkin_long_plan_more_waypoints(self):
        self.assertGreaterEqual(max_route_waypoints(240, "checkin"), 10)
        wps = [(121.5 + i * 0.001, 31.2) for i in range(15)]
        capped, truncated = cap_waypoints_for_walking(wps, 240, "checkin")
        self.assertTrue(truncated)
        self.assertGreater(len(capped), 5)


if __name__ == "__main__":
    unittest.main()
