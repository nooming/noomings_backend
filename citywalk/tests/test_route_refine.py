# -*- coding: utf-8 -*-
"""真实步行线折返修剪、计划时长减站、慢慢逛停留，以及结果页删站不再被补回。"""
import unittest
from unittest.mock import patch

from citywalk.core.planning.plan_service import execute_plan_request
from citywalk.core.planning.poi_selection import (
    allocate_poi_stay_times,
    drop_non_seed_stops_to_fit_plan,
    refine_stops_after_walk,
    trim_backtrack_on_walk_polyline,
    try_fill_pois_for_plan_time,
)
from citywalk.core.planning.route_engine import _cap_pois_keeping_seeds


def _pt(name, lat, score=5.0, seed=False):
    poi = {
        "name": name,
        "location": [121.50, lat],
        "final_score": score,
        "dist_to_route": 10,
        "type": "公园",
    }
    if seed:
        poi["is_seed"] = True
    return poi


def _out_and_back():
    """向北走到 31.240，再沿原线折返到 31.232。约每步 111 米。"""
    pts = [(121.50, 31.230 + i * 0.001) for i in range(0, 11)]
    pts.extend((121.50, 31.240 - i * 0.001) for i in range(1, 9))
    return pts


def _same_points_out_and_back():
    """向北走到 31.240，再沿同一串点走回 31.230。单程约 1.1 公里。"""
    out = [(121.50, 31.230 + i * 0.001) for i in range(0, 11)]
    return out + list(reversed(out[:-1]))


def _pt_lng(name, lng, lat, score=5.0, seed=False):
    poi = _pt(name, lat, score, seed)
    poi["location"] = [lng, lat]
    return poi


class TestWalkRetraceTrim(unittest.TestCase):
    def test_drops_non_seed_that_retraces(self):
        walk = _out_and_back()
        pois = [
            _pt("前站", 31.234, 8),
            _pt("远站", 31.239, 7),
            _pt("折返站", 31.233, 6),
        ]
        kept = trim_backtrack_on_walk_polyline(pois, walk, "balanced")
        names = [p["name"] for p in kept]
        self.assertIn("前站", names)
        self.assertIn("远站", names)
        self.assertNotIn("折返站", names)

    def test_keeps_seed_even_when_it_retraces(self):
        walk = _out_and_back()
        pois = [
            _pt("前站", 31.234, 8),
            _pt("远站", 31.239, 7),
            _pt("必去折返", 31.233, 1, seed=True),
        ]
        kept = trim_backtrack_on_walk_polyline(pois, walk, "balanced")
        self.assertIn("必去折返", [p["name"] for p in kept])

    def test_straight_walk_keeps_forward_stops(self):
        walk = [(121.50, 31.230 + i * 0.001) for i in range(0, 11)]
        pois = [_pt("甲", 31.233, 8), _pt("乙", 31.236, 7), _pt("丙", 31.239, 6)]
        kept = trim_backtrack_on_walk_polyline(pois, walk, "efficiency_first")
        self.assertEqual([p["name"] for p in kept], ["甲", "乙", "丙"])

    def test_same_points_spur_drops_non_seed_keeps_seed(self):
        walk = _same_points_out_and_back()
        dropped = trim_backtrack_on_walk_polyline(
            [_pt("沿途", 31.233, 8), _pt("远公园", 31.240, 7)],
            walk,
            "balanced",
        )
        self.assertEqual([p["name"] for p in dropped], ["沿途"])

        kept = trim_backtrack_on_walk_polyline(
            [_pt("沿途", 31.233, 8), _pt("必去远点", 31.240, 7, seed=True)],
            walk,
            "balanced",
        )
        self.assertEqual([p["name"] for p in kept], ["沿途", "必去远点"])

    def test_parallel_return_within_40m_drops_spur_tip(self):
        """回程偏开约 30 米（对侧人行道），仍应删掉支路尽头。"""
        out = [(121.50, 31.230 + i * 0.001) for i in range(0, 11)]
        back = [(121.50032, lat) for _lng, lat in reversed(out[:-1])]
        walk = out + back
        kept = trim_backtrack_on_walk_polyline(
            [_pt("沿途", 31.233, 8), _pt("远公园", 31.240, 7)],
            walk,
            "balanced",
        )
        self.assertEqual([p["name"] for p in kept], ["沿途"])

        seeded = trim_backtrack_on_walk_polyline(
            [_pt("沿途", 31.233, 8), _pt("必去远点", 31.240, 1, seed=True)],
            walk,
            "balanced",
        )
        self.assertIn("必去远点", [p["name"] for p in seeded])

    def test_spur_tip_dropped_onward_stop_kept(self):
        """向南走到远点再原路返回，然后向东。删尽头，保留返回之后的站。"""
        south = [(121.50, 31.240 - i * 0.001) for i in range(0, 11)]
        back = list(reversed(south[:-1]))
        east = [(121.50 + i * 0.001, 31.240) for i in range(1, 5)]
        walk = south + back + east
        kept = trim_backtrack_on_walk_polyline(
            [
                _pt("沿途", 31.236, 8),
                _pt("远公园", 31.230, 7),
                _pt_lng("东站", 121.504, 31.240, 6),
            ],
            walk,
            "balanced",
        )
        names = [p["name"] for p in kept]
        self.assertNotIn("远公园", names)
        self.assertIn("沿途", names)
        self.assertIn("东站", names)

        seeded = trim_backtrack_on_walk_polyline(
            [
                _pt("沿途", 31.236, 8),
                _pt("必去远点", 31.230, 1, seed=True),
                _pt_lng("东站", 121.504, 31.240, 6),
            ],
            walk,
            "balanced",
        )
        seed_names = [p["name"] for p in seeded]
        self.assertIn("必去远点", seed_names)
        self.assertIn("东站", seed_names)


class TestFitPlanDuration(unittest.TestCase):
    def test_drops_lowest_non_seed_until_checkin_fits(self):
        pois = [_pt(f"站{i}", 31.23 + i * 0.001, score=float(i)) for i in range(5)]
        # 步行 40 + 打卡上限 10 * n；计划 60 → 最多 2 站
        kept = drop_non_seed_stops_to_fit_plan(
            pois, 60, 40, visit_pace="checkin",
        )
        self.assertEqual(len(kept), 2)
        self.assertEqual([p["name"] for p in kept], ["站3", "站4"])

    def test_never_drops_seed_to_fit_time(self):
        pois = [
            _pt("必去", 31.231, score=0.1, seed=True),
            _pt("低分", 31.232, score=1),
            _pt("高分", 31.233, score=9),
        ]
        kept = drop_non_seed_stops_to_fit_plan(
            pois, 60, 55, visit_pace="checkin",
        )
        names = [p["name"] for p in kept]
        self.assertIn("必去", names)
        self.assertNotIn("低分", names)
        self.assertNotIn("高分", names)

    def test_refine_reports_change_once_for_both_trims(self):
        walk = _out_and_back()
        pois = [
            _pt("前站", 31.234, 9),
            _pt("远站", 31.239, 8),
            _pt("折返站", 31.233, 1),
            _pt("另一站", 31.236, 2),
        ]
        kept, changed = refine_stops_after_walk(
            pois, walk, 40, 60, route_style="balanced", visit_pace="checkin",
        )
        self.assertTrue(changed)
        self.assertNotIn("折返站", [p["name"] for p in kept])
        self.assertLessEqual(len(kept), 2)

    def test_cap_keeps_all_seeds(self):
        pois = [
            {"name": "必去A", "is_seed": True, "final_score": 1},
            {"name": "必去B", "is_seed": True, "final_score": 1},
            {"name": "普通", "final_score": 9},
        ]
        kept = _cap_pois_keeping_seeds(pois, 1)
        self.assertEqual([p["name"] for p in kept], ["必去A", "必去B"])


class TestRelaxedStay(unittest.TestCase):
    def test_raises_toward_cap_not_five_and_not_forty_five(self):
        pois = [_pt("甲", 31.23), _pt("乙", 31.24)]
        out, _hint, free_m = allocate_poi_stay_times(
            pois, 90, 20, visit_pace="relaxed",
        )
        stays = [p["stay_time"] for p in out]
        self.assertEqual(stays, [25, 25])
        self.assertGreater(free_m, 0)

    def test_partial_budget_sits_between_floor_and_cap(self):
        pois = [_pt("甲", 31.23), _pt("乙", 31.24)]
        out, _hint, _free = allocate_poi_stay_times(
            pois, 60, 20, visit_pace="relaxed",
        )
        stays = [p["stay_time"] for p in out]
        self.assertEqual(stays, [20, 20])

    def test_history_cap_stays_thirty(self):
        pois = [_pt("甲", 31.23), _pt("乙", 31.24)]
        out, _hint, _free = allocate_poi_stay_times(
            pois, 120, 20, poi_type="历史", ambience_profile="历史", visit_pace="relaxed",
        )
        self.assertEqual([p["stay_time"] for p in out], [30, 30])


class TestExcludedNamesNotRefilled(unittest.TestCase):
    def test_fill_skips_removed_name(self):
        route = [(121.47, 31.23), (121.49, 31.25)]
        end = (121.49, 31.25)
        kept = [{
            "name": "已有",
            "location": [121.475, 31.235],
            "final_score": 9.0,
            "dist_to_route": 10,
        }]
        removed = {
            "name": "已删除",
            "location": [121.48, 31.24],
            "final_score": 8.0,
            "dist_to_route": 10,
        }
        blocked = try_fill_pois_for_plan_time(
            list(kept),
            kept + [removed],
            180,
            20,
            6,
            "balanced",
            route,
            end,
            True,
            start=(121.47, 31.23),
            shortest_walk_min=20,
            visit_pace="checkin",
            excluded_names={"已删除"},
        )
        self.assertNotIn("已删除", {p["name"] for p in blocked})
        allowed = try_fill_pois_for_plan_time(
            list(kept),
            kept + [dict(removed)],
            180,
            20,
            6,
            "balanced",
            route,
            end,
            True,
            start=(121.47, 31.23),
            shortest_walk_min=20,
            visit_pace="checkin",
        )
        self.assertIn("已删除", {p["name"] for p in allowed})


class TestExtraWalkOnce(unittest.TestCase):
    def _pois(self):
        return [{
            "name": f"站{i}",
            "location": [121.50 + i * 0.001, 31.23 + i * 0.001],
            "final_score": float(10 - i),
            "dist_to_route": 8,
            "type": "公园",
        } for i in range(6)]

    def _route(self, start, end, filtered, **_kwargs):
        pts = [start] + [(p["location"][0], p["location"][1]) for p in filtered] + [end]
        return {
            "new_route_points": pts,
            "new_total_distance": 900,
            "new_walk_duration": 40,
            "new_total_duration": 40,
            "waypoints": pts[1:-1],
            "route_waypoints_truncated": False,
        }

    @patch("citywalk.core.planning.plan_service.ensure_last_poi_near_end", side_effect=lambda pois, *a, **k: pois)
    @patch("citywalk.core.planning.plan_service.trim_backtrack_pois_toward_end", side_effect=lambda pois, *a, **k: pois)
    @patch("citywalk.core.planning.plan_service.try_fill_pois_for_plan_time", side_effect=lambda pois, *a, **k: pois)
    @patch("citywalk.core.planning.plan_service._ensure_seed_pois_retained", side_effect=lambda pois, *a, **k: pois)
    @patch("citywalk.core.planning.plan_service.filter_poi_for_route", side_effect=lambda pois, *a, **k: list(pois))
    @patch("citywalk.core.planning.plan_service.generate_new_route")
    @patch("citywalk.core.planning.plan_service.sample_poi_along_shortest_route")
    @patch("citywalk.core.planning.plan_service.get_shortest_route")
    @patch("citywalk.core.planning.plan_service.validate_citywalk_endpoints", return_value=(True, ""))
    @patch("citywalk.core.planning.plan_service.AMAP_KEY", "test-key")
    def test_over_plan_regenerates_walking_once(
            self, _valid, mock_short, mock_sample, mock_gen,
            _filter, _ensure, _fill, _trim, _tail):
        mock_sample.return_value = self._pois()
        mock_short.return_value = {
            "route_points": [(121.50, 31.23), (121.51, 31.24)],
            "total_distance": 1200,
            "total_duration": 40,
            "amap_info": "",
        }
        mock_gen.side_effect = self._route
        body, status, _meta = execute_plan_request({
            "mode": "route",
            "start": [121.50, 31.23],
            "end": [121.51, 31.24],
            "city": "上海",
            "plan_time": 60,
            "visit_pace": "checkin",
            "poi_type": "无偏好",
        })
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        self.assertEqual(mock_gen.call_count, 2)
        self.assertLessEqual(len(body.get("pois") or []), 2)

    @patch("citywalk.core.planning.plan_service.ensure_last_poi_near_end", side_effect=lambda pois, *a, **k: pois)
    @patch("citywalk.core.planning.plan_service.trim_backtrack_pois_toward_end", side_effect=lambda pois, *a, **k: pois)
    @patch("citywalk.core.planning.plan_service.try_fill_pois_for_plan_time", side_effect=lambda pois, *a, **k: pois)
    @patch("citywalk.core.planning.plan_service._ensure_seed_pois_retained", side_effect=lambda pois, *a, **k: pois)
    @patch("citywalk.core.planning.plan_service.filter_poi_for_route", side_effect=lambda pois, *a, **k: list(pois))
    @patch("citywalk.core.planning.plan_service.generate_new_route")
    @patch("citywalk.core.planning.plan_service.sample_poi_along_shortest_route")
    @patch("citywalk.core.planning.plan_service.get_shortest_route")
    @patch("citywalk.core.planning.plan_service.validate_citywalk_endpoints", return_value=(True, ""))
    @patch("citywalk.core.planning.plan_service.AMAP_KEY", "test-key")
    def test_seeds_over_plan_keep_one_walk_and_tip(
            self, _valid, mock_short, mock_sample, mock_gen,
            _filter, _ensure, _fill, _trim, _tail):
        seed = {
            "name": "必去",
            "location": [121.505, 31.235],
            "final_score": 99,
            "dist_to_route": 5,
            "type": "公园",
            "is_seed": True,
        }
        mock_sample.return_value = [seed]
        mock_short.return_value = {
            "route_points": [(121.50, 31.23), (121.51, 31.24)],
            "total_distance": 1200,
            "total_duration": 55,
            "amap_info": "",
        }

        def _one(start, end, filtered, **_kwargs):
            pts = [start, end]
            return {
                "new_route_points": pts,
                "new_total_distance": 1200,
                "new_walk_duration": 55,
                "new_total_duration": 55,
                "waypoints": [],
                "route_waypoints_truncated": False,
            }

        mock_gen.side_effect = _one
        body, status, _meta = execute_plan_request({
            "mode": "route",
            "start": [121.50, 31.23],
            "end": [121.51, 31.24],
            "city": "上海",
            "plan_time": 60,
            "visit_pace": "checkin",
            "poi_type": "无偏好",
        })
        self.assertEqual(status, 200)
        self.assertEqual(mock_gen.call_count, 1)
        self.assertTrue(any(p.get("is_seed") for p in body.get("pois") or []))
        self.assertIn("已保留你指定的站点", body.get("route_tip") or "")
        self.assertGreater(body.get("activity_total_min") or 0, 60)


if __name__ == "__main__":
    unittest.main()
