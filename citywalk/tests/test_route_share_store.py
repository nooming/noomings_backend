# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest
from pathlib import Path

from citywalk.core import route_share_store as store


def _minimal_snapshot():
    return {
        "v": 1,
        "city": "上海",
        "result": {
            "success": True,
            "mode": "route",
            "path": [[121.47, 31.23], [121.48, 31.24]],
            "distance": 1200,
            "duration": 15,
            "pois": [{"name": "A", "location": [121.475, 31.235], "stay_time": 5}],
        },
    }


class TestRouteShareStore(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("CITYWALK_SHARED_ROUTES_DIR")
        os.environ["CITYWALK_SHARED_ROUTES_DIR"] = self._tmpdir.name
        os.environ["CITYWALK_ROUTE_SHARE_TTL_DAYS"] = "90"

    def tearDown(self):
        if self._old is None:
            os.environ.pop("CITYWALK_SHARED_ROUTES_DIR", None)
        else:
            os.environ["CITYWALK_SHARED_ROUTES_DIR"] = self._old
        self._tmpdir.cleanup()

    def test_save_and_load(self):
        snap = _minimal_snapshot()
        rid, err = store.save_shared_route(snap)
        self.assertIsNone(err)
        self.assertTrue(rid)
        loaded, err2 = store.load_shared_route(rid)
        self.assertIsNone(err2)
        self.assertEqual(loaded["city"], "上海")
        self.assertTrue(loaded["result"]["success"])

    def test_reject_bad_snapshot(self):
        rid, err = store.save_shared_route({"result": {"success": False}})
        self.assertIsNone(rid)
        self.assertTrue(err)

    def test_invalid_id(self):
        loaded, err = store.load_shared_route("../etc/passwd")
        self.assertIsNone(loaded)
        self.assertTrue(err)


if __name__ == "__main__":
    unittest.main()
