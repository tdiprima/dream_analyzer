"""Specification tests for the dream analysis service."""

import json
import unittest
from types import SimpleNamespace

from dream_analysis import (
    ANALYSIS_RESPONSE_FORMAT,
    MAX_DREAM_CHARS,
    MIN_DREAM_CHARS,
    REQUIRED_SECTIONS,
    AnalysisFormatError,
    DreamAnalyzer,
    DreamValidationError,
    ModelRefusalError,
    validate_analysis,
    validate_dream,
)

VALID_DREAM = "I was standing at the edge of a vast ocean at dusk."
GOOD_ANALYSIS = {key: f"{key} text" for key in REQUIRED_SECTIONS}


class FakeChatClient:
    """Records the request and returns a canned message."""

    def __init__(self, content=None, refusal=None, error=None):
        self.calls = []
        message = SimpleNamespace(content=content, refusal=refusal)
        self._response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


class ValidateDreamTests(unittest.TestCase):
    def test_strips_and_returns_text(self):
        self.assertEqual(validate_dream(f"  {VALID_DREAM}\n"), VALID_DREAM)

    def test_rejects_non_string(self):
        for bad in (None, 42, ["a"], b"bytes"):
            with self.assertRaises(DreamValidationError):
                validate_dream(bad)

    def test_rejects_empty_and_whitespace(self):
        for bad in ("", "   ", "\n\t"):
            with self.assertRaises(DreamValidationError):
                validate_dream(bad)

    def test_rejects_below_minimum(self):
        with self.assertRaises(DreamValidationError):
            validate_dream("a" * (MIN_DREAM_CHARS - 1))
        self.assertEqual(len(validate_dream("a" * MIN_DREAM_CHARS)), MIN_DREAM_CHARS)

    def test_rejects_above_maximum(self):
        self.assertEqual(len(validate_dream("a" * MAX_DREAM_CHARS)), MAX_DREAM_CHARS)
        with self.assertRaises(DreamValidationError):
            validate_dream("a" * (MAX_DREAM_CHARS + 1))

    def test_whitespace_padding_does_not_evade_max(self):
        padded = "a" * MAX_DREAM_CHARS + " " * 50
        self.assertEqual(len(validate_dream(padded)), MAX_DREAM_CHARS)

    def test_huge_input_rejected(self):
        with self.assertRaises(DreamValidationError):
            validate_dream("z" * 1_000_000)


class ValidateAnalysisTests(unittest.TestCase):
    def test_accepts_complete_analysis(self):
        self.assertEqual(validate_analysis(dict(GOOD_ANALYSIS)), GOOD_ANALYSIS)

    def test_rejects_non_dict(self):
        for bad in (None, [], "text", 3):
            with self.assertRaises(AnalysisFormatError):
                validate_analysis(bad)

    def test_rejects_missing_section(self):
        partial = dict(GOOD_ANALYSIS)
        del partial["symbol_interpretation"]
        with self.assertRaisesRegex(AnalysisFormatError, "symbol_interpretation"):
            validate_analysis(partial)

    def test_rejects_blank_or_non_string_section(self):
        for bad_value in ("", "   ", None, 7, ["x"]):
            broken = dict(GOOD_ANALYSIS, emotional_understanding=bad_value)
            with self.assertRaises(AnalysisFormatError):
                validate_analysis(broken)


class DreamAnalyzerTests(unittest.TestCase):
    def test_rejects_bad_token_ceiling(self):
        with self.assertRaises(ValueError):
            DreamAnalyzer(FakeChatClient(), 0)

    def test_sends_validated_dream_with_schema_and_cap(self):
        client = FakeChatClient(content=json.dumps(GOOD_ANALYSIS))
        analyzer = DreamAnalyzer(client, max_output_tokens=321, model="test-model")
        result = analyzer.analyze(f"  {VALID_DREAM}  ")
        self.assertEqual(result, GOOD_ANALYSIS)
        request = client.calls[0]
        self.assertEqual(request["model"], "test-model")
        self.assertEqual(request["max_completion_tokens"], 321)
        self.assertEqual(request["response_format"], ANALYSIS_RESPONSE_FORMAT)
        self.assertEqual(request["messages"][1], {"role": "user", "content": VALID_DREAM})

    def test_invalid_dream_never_reaches_model(self):
        client = FakeChatClient(content=json.dumps(GOOD_ANALYSIS))
        analyzer = DreamAnalyzer(client, max_output_tokens=100)
        for bad in ("", "short", "a" * (MAX_DREAM_CHARS + 1), None):
            with self.assertRaises(DreamValidationError):
                analyzer.analyze(bad)
        self.assertEqual(client.calls, [])

    def test_refusal_raises(self):
        analyzer = DreamAnalyzer(FakeChatClient(refusal="no"), 100)
        with self.assertRaises(ModelRefusalError):
            analyzer.analyze(VALID_DREAM)

    def test_empty_content_raises_format_error(self):
        analyzer = DreamAnalyzer(FakeChatClient(content=""), 100)
        with self.assertRaises(AnalysisFormatError):
            analyzer.analyze(VALID_DREAM)

    def test_invalid_json_raises_format_error(self):
        analyzer = DreamAnalyzer(FakeChatClient(content="{not json"), 100)
        with self.assertRaises(AnalysisFormatError):
            analyzer.analyze(VALID_DREAM)

    def test_markup_in_prose_is_returned_untouched_for_renderer_to_escape(self):
        hostile = dict(GOOD_ANALYSIS, psychological_insights="<script>alert(1)</script>")
        analyzer = DreamAnalyzer(FakeChatClient(content=json.dumps(hostile)), 100)
        self.assertEqual(analyzer.analyze(VALID_DREAM)["psychological_insights"], "<script>alert(1)</script>")

    def test_provider_error_propagates(self):
        analyzer = DreamAnalyzer(FakeChatClient(error=RuntimeError("boom")), 100)
        with self.assertRaises(RuntimeError):
            analyzer.analyze(VALID_DREAM)


if __name__ == "__main__":
    unittest.main()
