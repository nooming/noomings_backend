# -*- coding: utf-8 -*-
import unittest

from citywalk.core.geo.geo_utils import first_public_ip, is_public_ip


class TestVisitorIp(unittest.TestCase):
    def test_is_public_ip(self):
        self.assertTrue(is_public_ip("8.8.8.8"))
        self.assertFalse(is_public_ip("127.0.0.1"))
        self.assertFalse(is_public_ip("10.0.0.1"))
        self.assertFalse(is_public_ip("192.168.1.1"))
        self.assertFalse(is_public_ip("172.16.5.9"))
        self.assertFalse(is_public_ip("172.31.255.1"))
        self.assertTrue(is_public_ip("172.32.0.1"))
        self.assertFalse(is_public_ip("not-an-ip"))

    def test_first_public_from_xff(self):
        self.assertEqual(
            first_public_ip("8.8.8.8, 10.0.0.1", "127.0.0.1", "192.168.0.2"),
            "8.8.8.8",
        )
        self.assertEqual(
            first_public_ip("10.0.0.1, 192.168.1.2", "1.1.1.1", "127.0.0.1"),
            "1.1.1.1",
        )
        self.assertIsNone(first_public_ip("127.0.0.1", "10.1.2.3", "192.168.0.1"))
        self.assertEqual(first_public_ip(None, None, "8.8.4.4"), "8.8.4.4")
        self.assertEqual(first_public_ip("1.2.3.4:443"), "1.2.3.4")


if __name__ == "__main__":
    unittest.main()
