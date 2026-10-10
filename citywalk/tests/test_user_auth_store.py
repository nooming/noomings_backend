# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

from citywalk.core.user_auth import issue_token, verify_token
from citywalk.core.user_store import authenticate_user, get_user_footprints, register_user, save_user_footprints


class TestUserAuthStore(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["CITYWALK_USER_DATA_DIR"] = self._tmpdir.name
        os.environ["CITYWALK_AUTH_SECRET"] = "test-secret-key"

    def tearDown(self):
        os.environ.pop("CITYWALK_USER_DATA_DIR", None)
        os.environ.pop("CITYWALK_AUTH_SECRET", None)
        self._tmpdir.cleanup()

    def test_register_login_token(self):
        profile, err = register_user("a@example.com", "password123", "Alice")
        self.assertIsNone(err)
        self.assertEqual(profile["email"], "a@example.com")
        token = issue_token(profile["user_id"])
        self.assertEqual(verify_token(token), profile["user_id"])
        prof2, err2 = authenticate_user("a@example.com", "password123")
        self.assertIsNone(err2)
        self.assertEqual(prof2["user_id"], profile["user_id"])

    def test_footprints_roundtrip(self):
        profile, _ = register_user("b@example.com", "longpassword")
        uid = profile["user_id"]
        saved, err = save_user_footprints(uid, {
            "walked": [{"routeId": "x", "date": "2026-01-01", "note": "hi"}],
            "favorite_routes": ["x"],
            "favorite_spots": ["x::0"],
            "planned_routes": {},
        })
        self.assertIsNone(err)
        self.assertEqual(len(saved["walked"]), 1)
        loaded, err2 = get_user_footprints(uid)
        self.assertIsNone(err2)
        self.assertEqual(loaded["favorite_routes"], ["x"])


if __name__ == "__main__":
    unittest.main()
