# -*- coding: utf-8 -*-
"""灵感种草·联网选点 + 卡片勾选的 mock 测试（无需真实 key / 网络）。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent import inspiration, search_provider


class TestSearchProvider(unittest.TestCase):
    def test_not_configured_without_key(self):
        with mock.patch.dict("os.environ", {"CW_SEARCH_PROVIDER": "tavily", "TAVILY_API_KEY": ""}, clear=False):
            self.assertFalse(search_provider.is_search_configured())

    def test_web_search_empty_when_unconfigured(self):
        with mock.patch.dict("os.environ", {"TAVILY_API_KEY": ""}, clear=False):
            self.assertEqual(search_provider.web_search("上海 咖啡"), [])


class TestDedupeSpots(unittest.TestCase):
    def test_dedupe_and_limit(self):
        items = [
            {"name": "A", "reason": "r1", "category": "咖啡"},
            {"name": "A", "reason": "dup"},          # 重名去掉
            {"name": "", "reason": "空名去掉"},
            {"name": "B", "category": "书店"},
            "非 dict 跳过",
        ]
        out = inspiration._dedupe_spots(items, count=10)
        self.assertEqual([s["name"] for s in out], ["A", "B"])
        self.assertEqual(out[0]["category"], "咖啡")

        capped = inspiration._dedupe_spots(items, count=1)
        self.assertEqual(len(capped), 1)


class TestWebSuggestSpots(unittest.TestCase):
    def test_extracts_from_search_then_dedupes(self):
        fake_results = [{"title": "上海小众咖啡", "url": "u1", "content": "推荐 XX 咖啡馆"}]
        fake_llm = {"spots": [
            {"name": "XX 咖啡馆", "reason": "出片", "category": "咖啡馆"},
            {"name": "XX 咖啡馆", "reason": "dup"},
        ]}
        with mock.patch.object(inspiration, "is_configured", return_value=True), \
             mock.patch("agent.search_provider.is_search_configured", return_value=True), \
             mock.patch("agent.search_provider.web_search", return_value=fake_results), \
             mock.patch.object(inspiration, "chat_json", return_value=fake_llm) as m_llm:
            out = inspiration._web_suggest_spots("上海", "", ["出片"], ["咖啡"], 6)
        self.assertEqual([s["name"] for s in out], ["XX 咖啡馆"])
        self.assertTrue(m_llm.called)

    def test_falls_back_to_llm_when_search_unconfigured(self):
        with mock.patch.object(inspiration, "is_configured", return_value=True), \
             mock.patch("agent.search_provider.is_search_configured", return_value=False), \
             mock.patch.object(inspiration, "_llm_suggest_spots", return_value=[{"name": "FB"}]) as m_fb:
            out = inspiration._web_suggest_spots("上海", "", [], [], 6)
        self.assertEqual(out, [{"name": "FB"}])
        self.assertTrue(m_fb.called)

    def test_suggest_spots_dispatches_to_web(self):
        with mock.patch.dict("os.environ", {"CW_INSPIRATION_PROVIDER": "web_search"}, clear=False), \
             mock.patch.object(inspiration, "_web_suggest_spots", return_value=[{"name": "W"}]) as m_web:
            out = inspiration.suggest_spots("上海", "", ["出片"], ["咖啡"], 6)
        self.assertEqual(out, [{"name": "W"}])
        self.assertTrue(m_web.called)


class TestCleanSelectedSpots(unittest.TestCase):
    def test_keeps_only_coordinated_and_dedupes(self):
        from api.citywalk.routes_agent import _clean_selected_spots
        raw = [
            {"name": "A", "lng": 121.4, "lat": 31.2, "reason": "r", "category": "咖啡"},
            {"name": "A", "lng": 121.4, "lat": 31.2},        # 重名
            {"name": "B"},                                    # 无坐标丢弃
            {"name": "C", "lng": "bad", "lat": 31.2},         # 坐标非法丢弃
            {"name": "D", "lng": 120.0, "lat": 30.0},
        ]
        out = _clean_selected_spots(raw)
        self.assertEqual([s["name"] for s in out], ["A", "D"])
        self.assertEqual(out[0]["lng"], 121.4)
        self.assertEqual(_clean_selected_spots("not a list"), [])


class TestEnsureSeedPoisRetained(unittest.TestCase):
    def test_missing_seed_reinserted(self):
        from planning.route_engine import _ensure_seed_pois_retained
        seed = {
            "name": "种草咖啡馆",
            "location": [121.48, 31.23],
            "is_seed": True,
            "final_score": 99.0,
        }
        other = {
            "name": "普通点",
            "location": [121.49, 31.24],
            "final_score": 5.0,
        }
        pool = [seed, other]
        filtered = [other]
        out = _ensure_seed_pois_retained(filtered, pool, max_poi_count=2)
        names = [p["name"] for p in out]
        self.assertIn("种草咖啡馆", names)


if __name__ == "__main__":
    unittest.main()
