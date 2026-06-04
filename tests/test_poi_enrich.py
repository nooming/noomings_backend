# -*- coding: utf-8 -*-
"""POST /poi/enrich：fetch_poi_photos 导入与路由行为。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from citywalk import app


class TestPoiEnrich(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_routes_agent_imports_fetch_poi_photos(self):
        import api.routes_agent as routes_agent
        from planning.plan_service import fetch_poi_photos as fps

        self.assertTrue(hasattr(routes_agent, "fetch_poi_photos"))
        self.assertIs(routes_agent.fetch_poi_photos, fps)

    @patch("agent.enrichment.describe_poi", return_value="一句介绍")
    @patch("api.routes_agent.fetch_poi_photos", return_value=["https://example.com/a.jpg"])
    def test_poi_enrich_success(self, mock_photos, mock_describe):
        resp = self.client.post(
            "/poi/enrich",
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
        resp = self.client.post("/poi/enrich", json={"city": "上海"})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data.get("success"))


if __name__ == "__main__":
    unittest.main()
