# -*- coding: utf-8 -*-
"""POST /api/citywalk/poi/enrich：fetch_poi_photos 导入与路由行为。"""
import unittest
from unittest.mock import patch

from app import app

class TestPoiEnrich(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_routes_agent_imports_fetch_poi_photos(self):
        import citywalk.api.routes_agent as routes_agent
        from citywalk.core.planning.plan_service import fetch_poi_photos as fps

        self.assertTrue(hasattr(routes_agent, "fetch_poi_photos"))
        self.assertIs(routes_agent.fetch_poi_photos, fps)

    @patch("citywalk.core.agent.enrichment.describe_poi", return_value="一句介绍")
    @patch("citywalk.api.routes_agent.fetch_poi_photos", return_value=["https://example.com/a.jpg"])
    def test_poi_enrich_success(self, mock_photos, mock_describe):
        resp = self.client.post(
            "/api/citywalk/poi/enrich",
            json={"name": "测试咖啡馆", "city": "上海", "category": "咖啡"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("photos"), ["https://example.com/a.jpg"])
        self.assertEqual(data.get("description"), "一句介绍")
        mock_photos.assert_called_once()
        mock_describe.assert_called_once()

    def test_poi_enrich_missing_name(self):
        resp = self.client.post("/api/citywalk/poi/enrich", json={"city": "上海"})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data.get("success"))

if __name__ == "__main__":
    unittest.main()
