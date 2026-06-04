# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planning.poi_selection import (
    allocate_poi_stay_times,
    compute_max_poi_count,
    ensure_last_poi_near_end,
    mark_optional_pois,
    select_pois_by_route_segments,
    target_poi_count_by_distance,
)


def _poi(name: str, score: float, progress: float) -> dict:
    return {
        "name": name,
        "location": [121.50 + progress / 10000, 31.24],
        "final_score": score,
        "dist_to_route": 100,
        "type": "公园",
    }


class TestVisitPace(unittest.TestCase):
    def test_max_poi_checkin_greater_than_relaxed(self):
        checkin = compute_max_poi_count(240, 90, "checkin")
        relaxed = compute_max_poi_count(240, 90, "relaxed")
        self.assertGreater(checkin, relaxed)
        self.assertLessEqual(checkin, 15)

    def test_target_by_distance(self):
        self.assertEqual(target_poi_count_by_distance(7230, "checkin"), 7)

    def test_allocate_checkin_caps_stay(self):
        pois = [_poi(f"p{i}", 5.0, i * 500) for i in range(5)]
        out, hint, free_m = allocate_poi_stay_times(
            pois, 240, 100, visit_pace="checkin",
        )
        self.assertGreaterEqual(free_m, 80)
        for p in out:
            self.assertLessEqual(p["stay_time"], 12)
        total_stay = sum(p["stay_time"] for p in out)
        self.assertLess(total_stay, 240 - 100)
        self.assertIn("自由安排", hint)

    def test_mark_optional_low_score_and_fill(self):
        pois = [
            {"name": "核心A", "final_score": 9.0, "is_seed": True},
            {"name": "核心B", "final_score": 8.0},
            {"name": "核心C", "final_score": 7.5},
            {"name": "补点D", "final_score": 2.0, "_fill_added": True},
            {"name": "边缘E", "final_score": 1.0},
        ]
        mark_optional_pois(pois, "checkin")
        self.assertFalse(pois[0].get("optional"))
        self.assertTrue(pois[3].get("optional"))
        self.assertTrue(pois[4].get("optional"))

    def test_segment_checkin_picks_more_than_relaxed_spacing(self):
        route = [(121.50, 31.24), (121.52, 31.25), (121.54, 31.26)]
        candidates = [
            _poi(f"点{i}", 8.0 - i * 0.1, i * 400)
            for i in range(12)
        ]
        checkin = select_pois_by_route_segments(
            candidates, route, (121.54, 31.26),
            max_poi_count=10, min_poi_count=7,
            route_style="balanced", detour_mode=True,
            visit_pace="checkin",
        )
        relaxed = select_pois_by_route_segments(
            candidates, route, (121.54, 31.26),
            max_poi_count=10, min_poi_count=5,
            route_style="balanced", detour_mode=True,
            visit_pace="relaxed",
        )
        self.assertGreaterEqual(len(checkin), len(relaxed))

    def test_ensure_last_poi_does_not_strip_all_checkin(self):
        end = (121.54, 31.26)
        route = [(121.50, 31.24), (121.52, 31.25), (121.54, 31.26)]
        pois = []
        for i in range(8):
            pois.append({
                "name": f"站{i}",
                "location": [121.50 + i * 0.003, 31.24 + i * 0.002],
                "final_score": 5.0,
            })
        out = ensure_last_poi_near_end(
            pois, end, route, visit_pace="checkin", min_keep=5,
        )
        self.assertGreaterEqual(len(out), 5)


if __name__ == "__main__":
    unittest.main()
