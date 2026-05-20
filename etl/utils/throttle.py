"""Rate-limit decorator + small HTTP client wrappers.

Designed to keep us inside source-specific quotas:

- football-data.org: 10 req/min => >=6 s between calls.
- API-Football free: 100 req/day => no in-process throttle, daily-budget at
  call-site.
- Understat scraping: <=1 req/s as a courtesy.
- FPL Bootstrap: refresh interval >=60 s.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

T = TypeVar("T")


class TokenBucket:
    """Single-process token bucket. Thread-safe, monotonic-time based."""

    def __init__(self, rate_per_sec: float, capacity: float | None = None) -> None:
        self.rate = rate_per_sec
        self.capacity = capacity if capacity is not None else max(1.0, rate_per_sec)
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def take(self, n: float = 1.0) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= n:
                    self._tokens -= n
                    return
                wait = (n - self._tokens) / self.rate
            time.sleep(wait)


def throttled(rate_per_sec: float) -> Callable[[Callable[..., T]], Callable[..., T]]:
    bucket = TokenBucket(rate_per_sec=rate_per_sec)

    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> T:
            bucket.take()
            return fn(*args, **kwargs)

        return inner

    return deco
