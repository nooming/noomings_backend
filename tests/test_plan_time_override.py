# -*- coding: utf-8 -*-
"""智能规划：侧栏 plan_time 覆盖 LLM/描述推断。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.orchestrator import clamp_plan_time, normalize_intent
from api.agent_intent import _plan_time_from_payload


class TestPlanTimeOverride(unittest.TestCase):
    def test_plan_time_from_payload(self):
        self.assertEqual(_plan_time_from_payload({"plan_time_min": 120}), 120)
        self.assertEqual(_plan_time_from_payload({"plan_time": 90}), 90)
        self.assertIsNone(_plan_time_from_payload({"plan_time_min": 10}))
        self.assertIsNone(_plan_time_from_payload({}))

    def test_slider_overrides_llm_and_query(self):
        raw = {
            "status": "ready",
            "message": "ok",
            "city": "上海",
            "start": "同济大学",
            "end": "五角场",
            "plan_time": 60,
            "poi_type": "无偏好",
            "route_style": "balanced",
        }
        intent = normalize_intent(
            raw,
            user_query="约60分钟",
            plan_time_override=120,
        )
        self.assertEqual(intent["plan_time"], 120)

    def test_clamp(self):
        self.assertEqual(clamp_plan_time(300), 240)
        self.assertEqual(clamp_plan_time(10), 30)


if __name__ == "__main__":
    unittest.main()
