# -*- coding: utf-8 -*-
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.geocoding import resolve_location_detail
from lib.geo_utils import normalize_city_name


import unittest


class TestGeocoding(unittest.TestCase):
    def test_normalize_city(self):
        self.assertEqual(normalize_city_name("上海市"), "上海")

    @patch("lib.geocoding.api_request_with_retry")
    def test_resolve_place_text(self, mock_api):
        mock_api.return_value = {
            "status": "1",
            "pois": [{
                "cityname": "上海市",
                "location": "121.499718,31.239703",
            }],
        }
        detail = resolve_location_detail("东方明珠", "上海")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["source"], "place_text")
        self.assertAlmostEqual(detail["lng"], 121.5, delta=0.1)


if __name__ == "__main__":
    unittest.main()
