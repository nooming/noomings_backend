# -*- coding: utf-8 -*-
"""路线说明 route_tip 用户向文案。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from planning.route_tip import build_user_route_tip, _destination_label_for_tip


class TestRouteTipCopy(unittest.TestCase):
    def test_coord_end_hidden(self):
        self.assertEqual(_destination_label_for_tip("121.46,31.23"), "")
        tip = build_user_route_tip(
            mode="route",
            poi_count=3,
            end_address="121.463057,31.234733",
            detour_mode=True,
            route_style="atmosphere_first",
            route_waypoints_truncated=True,
        )
        self.assertNotIn("121.463", tip)
        self.assertNotIn("氛围节点", tip)
        self.assertNotIn("响应速度", tip)
        self.assertIn("氛围优先", tip)
        self.assertIn("完整顺序见下方列表", tip)

    def test_named_end_shown(self):
        tip = build_user_route_tip(
            mode="route",
            poi_count=2,
            end_address="东方明珠",
        )
        self.assertIn("东方明珠", tip)
        self.assertNotIn("（", tip)

    def test_no_time_gap_in_tip(self):
        tip = build_user_route_tip(
            mode="route",
            poi_count=1,
            end_address="外滩",
            detour_mode=False,
        )
        self.assertNotIn("比计划", tip)

    def test_degraded_copy(self):
        tip = build_user_route_tip(
            mode="route",
            poi_count=2,
            end_address="test",
            degraded_route=True,
        )
        self.assertIn("示意路线", tip)
        self.assertNotIn("重试完整串点", tip)


if __name__ == "__main__":
    unittest.main()
