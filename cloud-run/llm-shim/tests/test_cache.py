"""Tests for the TTL+LRU cache helper."""

from __future__ import annotations

import sys
from pathlib import Path

SVC_ROOT = Path(__file__).resolve().parents[1]
if str(SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(SVC_ROOT))

from app.cache import cache_key, clear, get_or_compute  # noqa: E402


def test_cache_key_stable():
    a = cache_key("model-a", {"contents": [{"text": "x"}]})
    b = cache_key("model-a", {"contents": [{"text": "x"}]})
    assert a == b


def test_cache_key_changes_when_input_differs():
    a = cache_key("model-a", {"text": "x"})
    b = cache_key("model-a", {"text": "y"})
    assert a != b


def test_get_or_compute_calls_once():
    clear()
    calls = []

    def factory():
        calls.append(1)
        return {"v": len(calls)}

    k = cache_key("once")
    first = get_or_compute(k, factory)
    second = get_or_compute(k, factory)
    assert first == second
    assert calls == [1]
