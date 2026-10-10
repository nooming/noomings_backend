# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

from citywalk.core.community_store import (
    create_buddy,
    create_post,
    delete_post,
    join_buddy,
    list_buddies,
    list_posts,
    toggle_like_post,
)


class TestCommunityStore(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["CITYWALK_COMMUNITY_DATA_DIR"] = self._tmpdir.name

    def tearDown(self):
        os.environ.pop("CITYWALK_COMMUNITY_DATA_DIR", None)
        self._tmpdir.cleanup()

    def test_post_and_list(self):
        post, err = create_post("u1", "Alice", {
            "type": "攻略",
            "title": "测试帖",
            "desc": "正文内容",
            "city": "上海",
            "tags": ["#Walk"],
        })
        self.assertIsNone(err)
        items = list_posts(keyword="测试")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "测试帖")

    def test_like_and_delete_post(self):
        post, _ = create_post("u1", "Alice", {
            "type": "打卡",
            "title": "like me",
            "desc": "body",
            "city": "上海",
        })
        pid = post["id"]
        liked, err = toggle_like_post(pid, "u2")
        self.assertIsNone(err)
        self.assertTrue(liked["liked_by_me"])
        self.assertEqual(liked["like_count"], 1)
        err_del = delete_post(pid, "u2")
        self.assertTrue(err_del)
        err_ok = delete_post(pid, "u1")
        self.assertIsNone(err_ok)

    def test_buddy_join(self):
        buddy, err = create_buddy("u1", "Bob", {
            "title": "周末 Walk",
            "desc": "一起走走",
            "city": "台北",
            "date": "周六 14:00",
            "slots_max": 4,
            "filter": "周末",
            "tags": ["摄影"],
        })
        self.assertIsNone(err)
        bid = buddy["id"]
        joined, err2 = join_buddy(bid, "u2")
        self.assertIsNone(err2)
        self.assertEqual(joined["people_filled"], 2)
        items = list_buddies(buddy_filter="周末")
        self.assertEqual(len(items), 1)


if __name__ == "__main__":
    unittest.main()
