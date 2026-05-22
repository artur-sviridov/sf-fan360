"""Tests for the token-bucket throttle."""

from __future__ import annotations

import time

from etl.utils.throttle import TokenBucket, throttled


def test_token_bucket_allows_initial_burst():
    bucket = TokenBucket(rate_per_sec=10, capacity=3)
    start = time.monotonic()
    for _ in range(3):
        bucket.take()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05, f"first burst should be instant, got {elapsed:.3f}s"


def test_token_bucket_enforces_rate():
    bucket = TokenBucket(rate_per_sec=5, capacity=1)
    start = time.monotonic()
    # First take is free; second must wait ~200 ms.
    bucket.take()
    bucket.take()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15, f"throttle should pace; got {elapsed:.3f}s"


def test_throttled_decorator_paces_calls():
    calls = []

    @throttled(rate_per_sec=10)
    def f():
        calls.append(time.monotonic())

    start = time.monotonic()
    for _ in range(3):
        f()
    elapsed = time.monotonic() - start
    assert len(calls) == 3
    # 3 calls at 10/s with capacity=1 burst -> ~0.2s.
    assert elapsed < 0.5
