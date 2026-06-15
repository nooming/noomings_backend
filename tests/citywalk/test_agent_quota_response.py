# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api.citywalk.routes_agent import _agent_fail_payload
from lib.amap_client import AmapQuotaError
from planning.plan_service import execute_plan_request


class TestAgentQuotaResponse(unittest.TestCase):
    def test_agent_fail_payload_forwards_quota(self):
        body = {
            "success": False,
            "message": "高德地图请求过于频繁，请约 30 秒后再试。",
            "quota_exceeded": True,
            "retry_after": 45,
        }
        out = _agent_fail_payload(body, "plan_failed", {"city": "上海"})
        self.assertTrue(out.get("quota_exceeded"))
        self.assertEqual(out.get("retry_after"), 45)
        self.assertEqual(out.get("agent_status"), "plan_failed")
        self.assertIn("30", out.get("message", ""))

    @patch("planning.plan_service.AMAP_KEY", "test-key")
    @patch("planning.plan_service.get_shortest_route")
    def test_execute_plan_quota_exceeded(self, mock_route):
        mock_route.side_effect = AmapQuotaError(
            "CUQPS_HAS_EXCEEDED_THE_LIMIT", retry_after=30,
        )
        body, status, _ = execute_plan_request({
            "mode": "route",
            "start": [121.5, 31.2],
            "end": [121.51, 31.21],
            "city": "上海",
            "plan_time": 60,
        })
        self.assertFalse(body.get("success"))
        self.assertEqual(status, 429)
        self.assertTrue(body.get("quota_exceeded"))
        self.assertEqual(body.get("retry_after"), 30)


if __name__ == "__main__":
    unittest.main()
