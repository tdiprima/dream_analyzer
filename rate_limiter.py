"""Thread-safe sliding-window rate limiter with a per-client and a global cap.

Pure logic: no Streamlit, no network, no clock dependency beyond the injected
``clock`` callable, so it can be unit-tested deterministically.
"""

import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Callable, Deque

# Upper bound on distinct client keys tracked at once. Keeps memory bounded
# under a flood of spoofed identities; the oldest idle key is evicted first.
MAX_TRACKED_CLIENTS = 10_000

GLOBAL_KEY = "__global__"


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of a rate-limit check."""

    allowed: bool
    retry_after_seconds: float
    reason: str


class SlidingWindowRateLimiter:
    """Allow at most N requests per key, and M requests overall, per window.

    A request is recorded only when it is allowed, so a rejected request never
    extends the caller's own lockout.
    """

    def __init__(
        self,
        per_client_limit: int,
        global_limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if per_client_limit < 1:
            raise ValueError("per_client_limit must be at least 1")
        if global_limit < 1:
            raise ValueError("global_limit must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._per_client_limit = per_client_limit
        self._global_limit = global_limit
        self._window_seconds = float(window_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._client_history: "OrderedDict[str, Deque[float]]" = OrderedDict()
        self._global_history: Deque[float] = deque()

    def check_and_record(self, client_key: str) -> RateLimitDecision:
        """Atomically decide whether ``client_key`` may proceed and record it if so."""
        if not isinstance(client_key, str) or not client_key:
            raise ValueError("client_key must be a non-empty string")

        now = self._clock()
        with self._lock:
            self._prune(self._global_history, now)
            client_history = self._client_history_for(client_key)
            self._prune(client_history, now)

            if len(client_history) >= self._per_client_limit:
                retry_after = self._seconds_until_slot(client_history, now)
                return RateLimitDecision(False, retry_after, "client_limit")

            if len(self._global_history) >= self._global_limit:
                retry_after = self._seconds_until_slot(self._global_history, now)
                return RateLimitDecision(False, retry_after, "global_limit")

            client_history.append(now)
            self._global_history.append(now)
            self._evict_idle_clients()
            return RateLimitDecision(True, 0.0, "ok")

    def _client_history_for(self, client_key: str) -> Deque[float]:
        history = self._client_history.get(client_key)
        if history is None:
            history = deque()
            self._client_history[client_key] = history
        else:
            # Most recently seen key goes to the end so eviction drops the idlest.
            self._client_history.move_to_end(client_key)
        return history

    def _prune(self, history: Deque[float], now: float) -> None:
        cutoff = now - self._window_seconds
        while history and history[0] <= cutoff:
            history.popleft()

    def _seconds_until_slot(self, history: Deque[float], now: float) -> float:
        oldest = history[0]
        return max(0.0, oldest + self._window_seconds - now)

    def _evict_idle_clients(self) -> None:
        # Drop empty histories first, then the least recently seen keys.
        empty_keys = [key for key, history in self._client_history.items() if not history]
        for key in empty_keys:
            del self._client_history[key]
        while len(self._client_history) > MAX_TRACKED_CLIENTS:
            self._client_history.popitem(last=False)
