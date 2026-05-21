"""TTL+LRU cache shared across translators.

Used to dedupe identical agent retries within 60 seconds so we do not burn
the Gemini AI Studio per-day quota on hot paths.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from cachetools import TTLCache

from app.config import settings

_cache: TTLCache[str, Any] = TTLCache(maxsize=settings.cache_maxsize, ttl=settings.cache_ttl_seconds)


def cache_key(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def get_or_compute(key: str, compute: Callable[[], Any]) -> Any:
    if key in _cache:
        return _cache[key]
    value = compute()
    _cache[key] = value
    return value


def clear() -> None:
    _cache.clear()
