"""Specification tests for SlidingWindowRateLimiter."""

import threading
import unittest

from rate_limiter import MAX_TRACKED_CLIENTS, SlidingWindowRateLimiter


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_limiter(per_client=3, global_limit=5, window=60, clock=None):
    return SlidingWindowRateLimiter(per_client, global_limit, window, clock or FakeClock())


class ConstructionTests(unittest.TestCase):
    def test_rejects_non_positive_limits(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                SlidingWindowRateLimiter(bad, 5, 60)
            with self.assertRaises(ValueError):
                SlidingWindowRateLimiter(1, bad, 60)
        with self.assertRaises(ValueError):
            SlidingWindowRateLimiter(1, 5, 0)

    def test_rejects_bad_client_key(self):
        limiter = make_limiter()
        for bad in ("", None, 42):
            with self.assertRaises(ValueError):
                limiter.check_and_record(bad)


class PerClientLimitTests(unittest.TestCase):
    def test_allows_up_to_limit_then_blocks(self):
        limiter = make_limiter(per_client=3)
        results = [limiter.check_and_record("a").allowed for _ in range(4)]
        self.assertEqual(results, [True, True, True, False])

    def test_block_reports_client_reason_and_retry_after(self):
        clock = FakeClock()
        limiter = make_limiter(per_client=1, window=60, clock=clock)
        limiter.check_and_record("a")
        clock.advance(10)
        decision = limiter.check_and_record("a")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "client_limit")
        self.assertAlmostEqual(decision.retry_after_seconds, 50.0)

    def test_rejected_request_does_not_extend_lockout(self):
        clock = FakeClock()
        limiter = make_limiter(per_client=1, window=60, clock=clock)
        limiter.check_and_record("a")
        clock.advance(59)
        limiter.check_and_record("a")  # rejected, must not count
        clock.advance(1)
        self.assertTrue(limiter.check_and_record("a").allowed)

    def test_window_slides_at_boundary(self):
        clock = FakeClock()
        limiter = make_limiter(per_client=1, window=60, clock=clock)
        limiter.check_and_record("a")
        clock.advance(59.999)
        self.assertFalse(limiter.check_and_record("a").allowed)
        clock.advance(0.001)
        self.assertTrue(limiter.check_and_record("a").allowed)

    def test_clients_are_independent(self):
        limiter = make_limiter(per_client=1, global_limit=10)
        self.assertTrue(limiter.check_and_record("a").allowed)
        self.assertTrue(limiter.check_and_record("b").allowed)
        self.assertFalse(limiter.check_and_record("a").allowed)


class GlobalLimitTests(unittest.TestCase):
    def test_global_cap_blocks_fresh_clients(self):
        limiter = make_limiter(per_client=10, global_limit=2)
        limiter.check_and_record("a")
        limiter.check_and_record("b")
        decision = limiter.check_and_record("c")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "global_limit")

    def test_spoofed_identities_cannot_exceed_global_cap(self):
        limiter = make_limiter(per_client=1, global_limit=50)
        allowed = sum(limiter.check_and_record(f"spoof-{i}").allowed for i in range(500))
        self.assertEqual(allowed, 50)

    def test_client_limit_checked_before_global(self):
        limiter = make_limiter(per_client=1, global_limit=1)
        limiter.check_and_record("a")
        self.assertEqual(limiter.check_and_record("a").reason, "client_limit")


class MemoryBoundTests(unittest.TestCase):
    def test_tracked_clients_never_exceed_cap(self):
        limiter = make_limiter(per_client=1, global_limit=10 ** 6)
        for i in range(MAX_TRACKED_CLIENTS + 500):
            limiter.check_and_record(f"c{i}")
        self.assertLessEqual(len(limiter._client_history), MAX_TRACKED_CLIENTS)

    def test_emptied_client_entry_is_cleaned_up(self):
        clock = FakeClock()
        limiter = make_limiter(per_client=1, global_limit=1, window=60, clock=clock)
        limiter.check_and_record("old")
        clock.advance(61)
        # "old" is pruned to empty, then the global cap (already refilled below) blocks it.
        limiter.check_and_record("filler")
        self.assertFalse(limiter.check_and_record("old").allowed)
        self.assertIn("old", limiter._client_history)
        clock.advance(61)
        limiter.check_and_record("filler")
        self.assertNotIn("old", limiter._client_history)


class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_requests_never_exceed_global_limit(self):
        limiter = SlidingWindowRateLimiter(per_client_limit=1000, global_limit=100, window_seconds=60)
        allowed_count = [0]
        count_lock = threading.Lock()
        barrier = threading.Barrier(50)

        def worker(index):
            barrier.wait()
            for _ in range(10):
                if limiter.check_and_record(f"client-{index}").allowed:
                    with count_lock:
                        allowed_count[0] += 1

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(allowed_count[0], 100)


if __name__ == "__main__":
    unittest.main()
