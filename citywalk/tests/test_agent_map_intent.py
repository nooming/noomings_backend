# -*- coding: utf-8 -*-
"""智能规划：地图起终点兜底意图。"""
import unittest

from citywalk.core.agent import intent as citywalk

class TestAgentMapIntent(unittest.TestCase):
    def test_map_endpoints_ready_route(self):
        payload = {
            "mode": "route",
            "start": [121.45, 31.23],
            "end": [121.48, 31.24],
        }
        self.assertTrue(citywalk._map_endpoints_ready(payload))
        self.assertFalse(citywalk._map_endpoints_ready({"mode": "route", "start": [1, 2]}))

    def test_map_endpoints_ready_loop(self):
        self.assertTrue(citywalk._map_endpoints_ready({
            "mode": "loop",
            "start": [121.45, 31.23],
        }))

    def test_build_intent_from_map_labels(self):
        intent = citywalk._build_intent_from_map({
            "city": "上海",
            "start": [121.45, 31.23],
            "end": [121.48, 31.24],
            "start_label": "自然博物馆",
            "end_label": "人民广场",
            "plan_time_min": 120,
            "poi_type": "无偏好",
            "route_style": "balanced",
            "mode": "route",
        }, "上海")
        self.assertEqual(intent["status"], "ready")
        self.assertEqual(intent["start"], "自然博物馆")
        self.assertEqual(intent["end"], "人民广场")
        self.assertEqual(intent["plan_time"], 120)

    def test_resolve_map_only_no_query(self):
        payload = {
            "mode": "route",
            "start": [121.45, 31.23],
            "end": [121.48, 31.24],
            "start_label": "A",
            "end_label": "B",
            "plan_time_min": 90,
            "city": "上海",
        }
        intent = citywalk._resolve_agent_intent("", "上海", payload)
        self.assertEqual(intent["status"], "ready")
        plan_data = citywalk._intent_to_agent_plan_data(intent)
        self.assertEqual(plan_data["start"], [121.45, 31.23])
        self.assertEqual(plan_data["end"], [121.48, 31.24])
        self.assertEqual(plan_data["plan_time"], 90)

    def test_resolve_clarify_without_map_or_query(self):
        intent = citywalk._resolve_agent_intent("", "", {})
        self.assertEqual(intent["status"], "clarify")

    def test_merge_poi_default_does_not_override_llm(self):
        intent = {
            "status": "ready",
            "poi_type": "咖啡甜品",
            "route_style": "balanced",
            "plan_time": 90,
            "city": "上海",
            "start": "A",
            "end": "B",
            "visit_pace": "checkin",
        }
        out = citywalk._merge_payload_into_intent(intent, {
            "poi_type": "无偏好",
            "visit_pace": "relaxed",
        })
        self.assertEqual(out["poi_type"], "咖啡甜品")
        self.assertEqual(out["visit_pace"], "relaxed")

    def test_merge_poi_explicit_wins(self):
        intent = {
            "status": "ready",
            "poi_type": "咖啡甜品",
            "route_style": "balanced",
            "plan_time": 90,
            "city": "上海",
            "start": "A",
            "end": "B",
        }
        out = citywalk._merge_payload_into_intent(intent, {
            "poi_type": "历史",
            "poi_type_locked": True,
        })
        self.assertEqual(out["poi_type"], "历史")

    def test_merge_explicit_none_preference_locked(self):
        intent = {
            "status": "ready",
            "poi_type": "咖啡甜品",
            "route_style": "balanced",
            "plan_time": 60,
            "city": "上海",
            "start": "A",
            "end": "B",
        }
        out = citywalk._merge_payload_into_intent(intent, {
            "poi_type": "无偏好",
            "poi_type_locked": True,
        })
        self.assertEqual(out["poi_type"], "无偏好")

    def test_time_of_day_normalize(self):
        self.assertEqual(citywalk.normalize_time_of_day("傍晚"), "evening")
        self.assertIn("夜景", citywalk.time_of_day_query_clause("夜晚"))

if __name__ == "__main__":
    unittest.main()
