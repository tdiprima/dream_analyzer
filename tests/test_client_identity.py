"""Specification tests for client identity resolution."""

import unittest

from client_identity import (
    LOCAL_CLIENT_KEY,
    MAX_CLIENT_KEY_LENGTH,
    ClientIdentityError,
    resolve_client_key,
)


class NoTrustedHeaderTests(unittest.TestCase):
    def test_uses_connection_ip(self):
        self.assertEqual(resolve_client_key("203.0.113.9", {}, None), "203.0.113.9")

    def test_missing_ip_falls_back_to_local(self):
        for empty in (None, ""):
            self.assertEqual(resolve_client_key(empty, {}, None), LOCAL_CLIENT_KEY)

    def test_ignores_forwarded_headers_when_not_trusted(self):
        headers = {"X-Forwarded-For": "10.0.0.1"}
        self.assertEqual(resolve_client_key("203.0.113.9", headers, None), "203.0.113.9")
        self.assertEqual(resolve_client_key("203.0.113.9", headers, ""), "203.0.113.9")


class TrustedHeaderTests(unittest.TestCase):
    HEADER = "X-Forwarded-For"

    def test_uses_header_value(self):
        key = resolve_client_key("10.0.0.1", {"X-Forwarded-For": "198.51.100.7"}, self.HEADER)
        self.assertEqual(key, "198.51.100.7")

    def test_header_lookup_is_case_insensitive(self):
        key = resolve_client_key(None, {"x-forwarded-for": "198.51.100.7"}, "X-FORWARDED-FOR")
        self.assertEqual(key, "198.51.100.7")

    def test_takes_last_entry_so_client_supplied_prefix_is_ignored(self):
        spoofed = "1.1.1.1, 2.2.2.2 , 198.51.100.7"
        key = resolve_client_key(None, {self.HEADER: spoofed}, self.HEADER)
        self.assertEqual(key, "198.51.100.7")

    def test_missing_header_fails_closed(self):
        with self.assertRaises(ClientIdentityError):
            resolve_client_key("10.0.0.1", {}, self.HEADER)

    def test_blank_or_trailing_comma_fails_closed(self):
        for bad in ("", "   ", "198.51.100.7,", ","):
            with self.assertRaises(ClientIdentityError):
                resolve_client_key(None, {self.HEADER: bad}, self.HEADER)

    def test_oversized_value_fails_closed(self):
        too_long = "a" * (MAX_CLIENT_KEY_LENGTH + 1)
        with self.assertRaises(ClientIdentityError):
            resolve_client_key(None, {self.HEADER: too_long}, self.HEADER)
        just_fits = "a" * MAX_CLIENT_KEY_LENGTH
        self.assertEqual(resolve_client_key(None, {self.HEADER: just_fits}, self.HEADER), just_fits)

    def test_control_or_non_ascii_fails_closed(self):
        for bad in ("1.2.3.4\r\nX: y", "1.2.3.4\x00", "ünïcode", "a b"):
            with self.assertRaises(ClientIdentityError):
                resolve_client_key(None, {self.HEADER: bad}, self.HEADER)


if __name__ == "__main__":
    unittest.main()
