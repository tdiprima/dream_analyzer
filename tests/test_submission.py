"""Specification tests for the submission workflow."""

import unittest

from dream_analysis import AnalysisFormatError, ModelRefusalError
from rate_limiter import RateLimitDecision, SlidingWindowRateLimiter
from submission import (
    BAD_RESPONSE_MESSAGE,
    FAILURE_MESSAGE,
    REFUSAL_MESSAGE,
    SubmissionStatus,
    rate_limit_message,
    submit_dream,
)

VALID_DREAM = "I was standing at the edge of a vast ocean at dusk."
ANALYSIS = {"psychological_insights": "a", "symbol_interpretation": "b",
            "emotional_understanding": "c", "personal_growth_guidance": "d"}


class FakeAnalyzer:
    def __init__(self, result=None, error=None):
        self.calls = []
        self._result = result
        self._error = error

    def analyze(self, dream):
        self.calls.append(dream)
        if self._error:
            raise self._error
        return self._result


class FakeLimiter:
    def __init__(self, decision):
        self.keys = []
        self._decision = decision

    def check_and_record(self, client_key):
        self.keys.append(client_key)
        return self._decision


ALLOW = RateLimitDecision(True, 0.0, "ok")


class HappyPathTests(unittest.TestCase):
    def test_valid_dream_is_analyzed(self):
        analyzer = FakeAnalyzer(result=ANALYSIS)
        limiter = FakeLimiter(ALLOW)
        outcome = submit_dream(f"  {VALID_DREAM} ", "client-a", limiter, analyzer)
        self.assertTrue(outcome.is_success)
        self.assertIs(outcome.status, SubmissionStatus.ANALYZED)
        self.assertEqual(outcome.analysis, ANALYSIS)
        self.assertEqual(analyzer.calls, [VALID_DREAM])
        self.assertEqual(limiter.keys, ["client-a"])


class ValidationTests(unittest.TestCase):
    def test_invalid_input_skips_limiter_and_analyzer(self):
        for bad in ("", "   ", "too short", "x" * 5001, None):
            analyzer = FakeAnalyzer(result=ANALYSIS)
            limiter = FakeLimiter(ALLOW)
            outcome = submit_dream(bad, "client-a", limiter, analyzer)
            self.assertIs(outcome.status, SubmissionStatus.INVALID_INPUT)
            self.assertFalse(outcome.is_success)
            self.assertTrue(outcome.message)
            self.assertEqual(limiter.keys, [], msg=repr(bad))
            self.assertEqual(analyzer.calls, [], msg=repr(bad))


class RateLimitTests(unittest.TestCase):
    def test_blocked_request_never_reaches_analyzer(self):
        blocked = RateLimitDecision(False, 12.2, "client_limit")
        analyzer = FakeAnalyzer(result=ANALYSIS)
        outcome = submit_dream(VALID_DREAM, "client-a", FakeLimiter(blocked), analyzer)
        self.assertIs(outcome.status, SubmissionStatus.RATE_LIMITED)
        self.assertEqual(outcome.decision, blocked)
        self.assertIn("13 seconds", outcome.message)
        self.assertEqual(analyzer.calls, [])

    def test_real_limiter_blocks_after_cap(self):
        limiter = SlidingWindowRateLimiter(per_client_limit=2, global_limit=10, window_seconds=60)
        analyzer = FakeAnalyzer(result=ANALYSIS)
        statuses = [submit_dream(VALID_DREAM, "k", limiter, analyzer).status for _ in range(3)]
        self.assertEqual(statuses, [SubmissionStatus.ANALYZED] * 2 + [SubmissionStatus.RATE_LIMITED])
        self.assertEqual(len(analyzer.calls), 2)

    def test_rate_limit_message_rounds_up_and_floors_at_one(self):
        self.assertIn("1 seconds", rate_limit_message(RateLimitDecision(False, 0.0, "client_limit")))
        self.assertIn("about 3 seconds", rate_limit_message(RateLimitDecision(False, 2.01, "global_limit")))
        self.assertIn("busy", rate_limit_message(RateLimitDecision(False, 5, "global_limit")))


class FailureMappingTests(unittest.TestCase):
    def _submit_with_error(self, error):
        return submit_dream(VALID_DREAM, "k", FakeLimiter(ALLOW), FakeAnalyzer(error=error))

    def test_refusal(self):
        outcome = self._submit_with_error(ModelRefusalError("no"))
        self.assertIs(outcome.status, SubmissionStatus.MODEL_REFUSED)
        self.assertEqual(outcome.message, REFUSAL_MESSAGE)

    def test_bad_response(self):
        outcome = self._submit_with_error(AnalysisFormatError("missing"))
        self.assertIs(outcome.status, SubmissionStatus.BAD_RESPONSE)
        self.assertEqual(outcome.message, BAD_RESPONSE_MESSAGE)

    def test_configuration_error_surfaces_its_message(self):
        outcome = self._submit_with_error(EnvironmentError("OPENAI_API_KEY environment variable is not set."))
        self.assertIs(outcome.status, SubmissionStatus.CONFIGURATION_ERROR)
        self.assertIn("OPENAI_API_KEY", outcome.message)

    def test_unexpected_error_does_not_leak_details(self):
        outcome = self._submit_with_error(RuntimeError("secret internal detail sk-abc"))
        self.assertIs(outcome.status, SubmissionStatus.FAILED)
        self.assertEqual(outcome.message, FAILURE_MESSAGE)
        self.assertNotIn("sk-abc", outcome.message)
        self.assertIsNone(outcome.analysis)


if __name__ == "__main__":
    unittest.main()
