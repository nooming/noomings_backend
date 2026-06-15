# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.geocoding import place_text_search, resolve_seed_location
from planning.plan_service import build_seed_pois


class TestSeedGeocode(unittest.TestCase):
    def setUp(self):
        self.route = [(121.50, 31.24), (121.51, 31.25)]
        self.ref = ((121.50 + 121.51) / 2, (31.24 + 31.25) / 2)

    @patch("lib.geocoding.get_city_from_location")
    @patch("lib.geocoding.place_text_search")
    def test_resolve_seed_rejects_far_match(self, mock_pts, mock_city):
        mock_pts.return_value = (116.40, 39.90)
        mock_city.return_value = "北京"
        coords = resolve_seed_location("大隐书局", "上海", self.route)
        self.assertIsNone(coords)

    @patch("lib.geocoding._coords_match_target_city", return_value=True)
    @patch("lib.geocoding.place_text_search")
    def test_resolve_seed_accepts_near_match(self, mock_pts, _mock_city_ok):
        mock_pts.return_value = (121.505, 31.245)
        coords = resolve_seed_location("大隐书局", "上海", self.route)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 121.505, places=3)

    @patch("lib.geocoding.api_request_with_retry")
    def test_place_text_search_passes_location_bias(self, mock_api):
        mock_api.return_value = {
            "status": "1",
            "pois": [{
                "cityname": "上海市",
                "location": "121.500000,31.240000",
            }],
        }
        place_text_search("书店", "上海", location=self.ref)
        _url, params = mock_api.call_args[0]
        self.assertEqual(params.get("citylimit"), "true")
        self.assertIn("location", params)
        self.assertIn("121.5", params["location"])

    @patch("planning.plan_service.resolve_seed_location")
    def test_build_seed_pois_skips_failed_resolve(self, mock_resolve):
        mock_resolve.return_value = None
        seeds = build_seed_pois(
            ["大隐书局", {"name": "某咖啡", "lng": 121.5, "lat": 31.24}],
            self.route,
            city="上海",
        )
        self.assertEqual(seeds, [])
        self.assertEqual(mock_resolve.call_count, 2)


if __name__ == "__main__":
    unittest.main()
