"""Specification tests for abuse-control configuration parsing."""

import unittest

from abuse_settings import (
    DEFAULT_GLOBAL_LIMIT,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_PER_CLIENT_LIMIT,
    DEFAULT_WINDOW_SECONDS,
    MAX_ALLOWED_OUTPUT_TOKENS,
    AbuseSettingsError,
    load_abuse_settings,
)


class DefaultsTests(unittest.TestCase):
    def test_empty_env_uses_defaults(self):
        settings = load_abuse_settings({})
        self.assertEqual(settings.per_client_limit, DEFAULT_PER_CLIENT_LIMIT)
        self.assertEqual(settings.global_limit, DEFAULT_GLOBAL_LIMIT)
        self.assertEqual(settings.window_seconds, DEFAULT_WINDOW_SECONDS)
        self.assertEqual(settings.max_output_tokens, DEFAULT_MAX_OUTPUT_TOKENS)

    def test_blank_value_uses_default(self):
        settings = load_abuse_settings({"RATE_LIMIT_PER_CLIENT": "   "})
        self.assertEqual(settings.per_client_limit, DEFAULT_PER_CLIENT_LIMIT)


class ParsingTests(unittest.TestCase):
    def test_valid_overrides(self):
        settings = load_abuse_settings({
            "RATE_LIMIT_PER_CLIENT": "2",
            "RATE_LIMIT_GLOBAL": " 20 ",
            "RATE_LIMIT_WINDOW_SECONDS": "30",
            "ANALYSIS_MAX_OUTPUT_TOKENS": "800",
        })
        self.assertEqual((settings.per_client_limit, settings.global_limit), (2, 20))
        self.assertEqual((settings.window_seconds, settings.max_output_tokens), (30, 800))

    def test_non_integer_rejected(self):
        for bad in ("five", "1.5", "1e3", "; rm -rf /"):
            with self.assertRaises(AbuseSettingsError):
                load_abuse_settings({"RATE_LIMIT_GLOBAL": bad})

    def test_zero_and_negative_rejected(self):
        for bad in ("0", "-1"):
            with self.assertRaises(AbuseSettingsError):
                load_abuse_settings({"RATE_LIMIT_WINDOW_SECONDS": bad})

    def test_output_token_ceiling_enforced(self):
        with self.assertRaises(AbuseSettingsError):
            load_abuse_settings({"ANALYSIS_MAX_OUTPUT_TOKENS": str(MAX_ALLOWED_OUTPUT_TOKENS + 1)})
        settings = load_abuse_settings({"ANALYSIS_MAX_OUTPUT_TOKENS": str(MAX_ALLOWED_OUTPUT_TOKENS)})
        self.assertEqual(settings.max_output_tokens, MAX_ALLOWED_OUTPUT_TOKENS)

    def test_oversized_value_rejected(self):
        with self.assertRaises(AbuseSettingsError):
            load_abuse_settings({"RATE_LIMIT_PER_CLIENT": "9" * 40})

    def test_per_client_cannot_exceed_global(self):
        with self.assertRaises(AbuseSettingsError):
            load_abuse_settings({"RATE_LIMIT_PER_CLIENT": "10", "RATE_LIMIT_GLOBAL": "5"})


if __name__ == "__main__":
    unittest.main()


class ClientIdHeaderTests(unittest.TestCase):
    def test_unset_or_blank_means_none(self):
        self.assertIsNone(load_abuse_settings({}).client_id_header)
        self.assertIsNone(load_abuse_settings({"CLIENT_ID_HEADER": "  "}).client_id_header)

    def test_valid_name_is_kept_trimmed(self):
        settings = load_abuse_settings({"CLIENT_ID_HEADER": " X-Forwarded-For "})
        self.assertEqual(settings.client_id_header, "X-Forwarded-For")

    def test_invalid_name_rejected(self):
        for bad in ("X Forwarded", "X:Y", "a\r\nb", "ü", "x" * 101):
            with self.assertRaises(AbuseSettingsError):
                load_abuse_settings({"CLIENT_ID_HEADER": bad})
