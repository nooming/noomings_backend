# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from planning.plan_service import _walking_route_fail_message, execute_plan_request


class TestAmapWalkingFail(unittest.TestCase):
    def test_walking_fail_message_contains_info(self):
        msg = _walking_route_fail_message("ENGINE_RESPONSE_DATA_ERROR")
        self.assertIn("ENGINE_RESPONSE_DATA_ERROR", msg)
        self.assertIn("高德步行规划未成功", msg)

    @patch("planning.plan_service.AMAP_KEY", "test-key")
    @patch("planning.plan_service.get_shortest_route")
    def test_execute_plan_request_surfaces_amap_info(self, mock_route):
        mock_route.return_value = {
            "route_points": [(121.5, 31.2), (121.51, 31.21)],
            "total_distance": 0,
            "total_duration": 0,
            "amap_info": "ENGINE_RESPONSE_DATA_ERROR",
        }
        body, status, _ = execute_plan_request({
            "mode": "route",
            "start": [121.5, 31.2],
            "end": [121.51, 31.21],
            "city": "上海",
            "plan_time": 60,
        })
        self.assertFalse(body.get("success"))
        self.assertEqual(status, 400)
        self.assertIn("ENGINE_RESPONSE_DATA_ERROR", body.get("message", ""))


if __name__ == "__main__":
    unittest.main()
