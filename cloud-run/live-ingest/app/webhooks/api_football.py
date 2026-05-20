"""API-Football webhook normalizer.

API-Football does not push webhooks in the free tier; callers either poll
the `/fixtures/events` endpoint themselves and POST results here, or this
service polls on a schedule. The endpoint accepts both shapes.
"""

from __future__ import annotations

from typing import Any

from app.models import LiveEvent


def parse_api_football_event(fixture: dict[str, Any], event: dict[str, Any]) -> LiveEvent:
    """Convert a single API-Football fixture event into a LiveEvent."""
    fixture_id = fixture.get("id") or fixture.get("fixture", {}).get("id")
    home = (fixture.get("teams", {}).get("home") or {}).get("name")
    away = (fixture.get("teams", {}).get("away") or {}).get("name")
    label = f"{home} v {away}" if home and away else None

    minute = (event.get("time") or {}).get("elapsed")
    extra = (event.get("time") or {}).get("extra")
    detail = {
        "type": event.get("type"),
        "detail": event.get("detail"),
        "comments": event.get("comments"),
        "extra": extra,
    }
    return LiveEvent(
        event_id=f"af-{fixture_id}-{event.get('time', {}).get('elapsed', 0)}-{event.get('player', {}).get('id', 'x')}",
        source="api-football",
        match_id=str(fixture_id),
        fixture_label=label,
        minute=minute,
        period=None,
        event_type=str(event.get("type") or "unknown"),
        team=(event.get("team") or {}).get("name"),
        player=(event.get("player") or {}).get("name"),
        detail=detail,
    )


def parse_api_football_batch(payload: dict[str, Any]) -> list[LiveEvent]:
    """Parse the standard API-Football `/fixtures/events?fixture=` response."""
    fixture = payload.get("fixture") or payload
    events = payload.get("events") or payload.get("response") or []
    return [parse_api_football_event(fixture, e) for e in events]
