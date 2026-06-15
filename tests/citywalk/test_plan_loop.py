# -*- coding: utf-8 -*-
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from planning.plan_loop import generate_loop_route


class TestGenerateLoopRoute(unittest.TestCase):
    def test_empty_pois_returns_center_only(self):
        center = (121.47, 31.23)
        out = generate_loop_route(center, [])
        self.assertEqual(len(out["new_route_points"]), 2)
        self.assertEqual(out["new_total_distance"], 0)

    def test_orders_pois_by_angle(self):
        center = (0.0, 0.0)
        pois = [
            {"location": [1.0, 0.1], "angle": 0.1},
            {"location": [0.0, 1.0], "angle": math.pi / 2},
            {"location": [-1.0, 0.0], "angle": math.pi},
        ]

        def fake_fetch(a, b):
            return {
                "status": "1",
                "route": {
                    "paths": [{
                        "distance": "100",
                        "duration": "120",
                        "steps": [{"polyline": f"{a[0]},{a[1]};{b[0]},{b[1]}"}],
                    }],
                },
            }

        import planning.plan_loop as pl
        pl._fetch_walking_segment = fake_fetch
        out = generate_loop_route(center, pois)
        self.assertGreater(out["new_total_distance"], 0)
        self.assertEqual(len(out["waypoints"]), 3)


if __name__ == "__main__":
    unittest.main()
