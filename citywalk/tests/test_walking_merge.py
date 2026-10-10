# -*- coding: utf-8 -*-
import unittest

from citywalk.core.planning.walking_merge import (
    format_walking_segment_failure_tip,
    stitch_walk_segment_results,
)


class TestWalkingMerge(unittest.TestCase):
    def test_stitch_straight_fallback_on_empty_segment(self):
        specs = [(0, (121.0, 31.0), (121.01, 31.0))]
        results = [([], 0, 0)]
        labels = ["起点", "终点"]
        out = stitch_walk_segment_results(specs, results, labels)
        self.assertEqual(len(out["new_route_points"]), 2)
        self.assertEqual(len(out["walking_segment_failures"]), 1)
        self.assertIn("第 1 段", format_walking_segment_failure_tip(out["walking_segment_failures"]))

    def test_stitch_ok_segment(self):
        specs = [(0, (121.0, 31.0), (121.01, 31.0))]
        results = [([[121.0, 31.0], [121.005, 31.0], [121.01, 31.0]], 100, 2)]
        labels = ["起点", "终点"]
        out = stitch_walk_segment_results(specs, results, labels)
        self.assertGreaterEqual(len(out["new_route_points"]), 2)
        self.assertEqual(out["walking_segment_failures"], [])


if __name__ == "__main__":
    unittest.main()
