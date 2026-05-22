"""FPL Bootstrap normalizer.

The Fantasy Premier League API exposes near-real-time per-player live points
during a gameweek. We poll the `/event/{gw}/live/` endpoint, diff against the
previous tick, and emit one LiveEvent per change.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.models import LiveEvent

logger = logging.getLogger(__name__)


def fetch_bootstrap(client: httpx.Client | None = None) -> dict[str, Any]:
    client = client or httpx.Client(timeout=15, headers={"User-Agent": settings.user_agent})
    r = client.get(settings.fpl_bootstrap_url)
    r.raise_for_status()
    return r.json()


def fetch_event_live(gw: int, client: httpx.Client | None = None) -> dict[str, Any]:
    client = client or httpx.Client(timeout=15, headers={"User-Agent": settings.user_agent})
    url = settings.fpl_event_live_url_tpl.format(gw=gw)
    r = client.get(url)
    r.raise_for_status()
    return r.json()


def normalize_event_live(
    gw: int,
    payload: dict[str, Any],
    previous: dict[int, dict[str, Any]] | None = None,
) -> list[LiveEvent]:
    """Emit one LiveEvent for each meaningful change vs `previous`.

    A "meaningful change" is goals, assists, yellow/red cards, bonus, or
    minutes crossing 0 (player came on) / 45 / 90.
    """
    previous = previous or {}
    out: list[LiveEvent] = []
    for entry in payload.get("elements", []):
        pid = int(entry["id"])
        stats = entry.get("stats", {}) or {}
        prev_stats = (previous.get(pid) or {}).get("stats") or {}
        for stat_key, label in (
            ("goals_scored", "Goal"),
            ("assists", "Assist"),
            ("yellow_cards", "Yellow Card"),
            ("red_cards", "Red Card"),
            ("bonus", "Bonus"),
        ):
            curr = int(stats.get(stat_key, 0))
            prev = int(prev_stats.get(stat_key, 0))
            if curr > prev:
                out.append(
                    LiveEvent(
                        event_id=f"fpl-{gw}-{pid}-{stat_key}-{curr}",
                        source="fpl",
                        match_id=f"gw-{gw}",
                        event_type=label,
                        minute=stats.get("minutes"),
                        player=str(pid),  # mapped to name by the agent via DMO join
                        detail={"player_id": pid, "stat": stat_key, "value": curr},
                    )
                )
    if out:
        logger.info("fpl: gw=%s diffed %d events", gw, len(out))
    return out
