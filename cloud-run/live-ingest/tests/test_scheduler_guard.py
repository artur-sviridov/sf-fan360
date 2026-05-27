"""Unit tests for the fixture-driven Cloud Scheduler guard."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SVC_ROOT = Path(__file__).resolve().parents[1]
if str(SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(SVC_ROOT))

from app.scheduler_guard import (  # noqa: E402
    active_windows,
    any_match_in_poll_window,
    poll_window,
    resolve_current_gameweek,
)


def _match(*, mid: int, kickoff: datetime, status: str = "TIMED", home: str = "ARS", away: str = "LIV") -> dict:
    return {
        "id": mid,
        "utcDate": kickoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "homeTeam": {"shortName": home},
        "awayTeam": {"shortName": away},
    }


def test_window_starts_ten_minutes_before_kickoff():
    kickoff = datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc)
    w = poll_window(_match(mid=1, kickoff=kickoff), now=kickoff - timedelta(minutes=30))
    assert w is not None
    assert w.window_start == kickoff - timedelta(minutes=10)
    assert w.window_end == kickoff + timedelta(minutes=120)


def test_scheduled_match_ends_at_kickoff_plus_one_twenty():
    kickoff = datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc)
    w = poll_window(_match(mid=2, kickoff=kickoff, status="SCHEDULED"), now=kickoff - timedelta(minutes=5))
    assert w is not None
    assert w.window_end == kickoff + timedelta(minutes=120)


def test_finished_match_uses_default_window_end_no_extension():
    kickoff = datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc)
    w = poll_window(_match(mid=3, kickoff=kickoff, status="FINISHED"), now=kickoff + timedelta(minutes=200))
    assert w is not None
    assert w.window_end == kickoff + timedelta(minutes=120)


def test_in_play_extends_window_until_now_plus_fifteen():
    kickoff = datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc)
    now = kickoff + timedelta(minutes=130)  # past default 120-minute end
    w = poll_window(_match(mid=4, kickoff=kickoff, status="IN_PLAY"), now=now)
    assert w is not None
    assert w.window_end == now + timedelta(minutes=15)


def test_active_windows_filters_to_currently_open():
    kickoff_active = datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc)
    kickoff_future = datetime(2026, 5, 23, 18, 0, tzinfo=timezone.utc)
    kickoff_past = datetime(2026, 5, 22, 14, 0, tzinfo=timezone.utc)
    now = kickoff_active + timedelta(minutes=45)
    matches = [
        _match(mid=10, kickoff=kickoff_active, status="IN_PLAY"),
        _match(mid=11, kickoff=kickoff_future, status="TIMED"),
        _match(mid=12, kickoff=kickoff_past, status="FINISHED"),
    ]
    out = active_windows(matches, now)
    assert [w.match_id for w in out] == ["10"]
    assert any_match_in_poll_window(matches, now)


def test_no_active_windows_in_offseason():
    kickoff = datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc)
    matches = [_match(mid=1, kickoff=kickoff, status="TIMED")]
    middle_of_week = kickoff + timedelta(days=4)
    assert active_windows(matches, middle_of_week) == []
    assert not any_match_in_poll_window(matches, middle_of_week)


def test_invalid_utc_date_is_skipped():
    bad = {"id": 1, "utcDate": "not-a-date", "status": "TIMED"}
    assert poll_window(bad, now=datetime.now(timezone.utc)) is None


def test_resolve_current_gameweek_prefers_is_current():
    bootstrap = {
        "events": [
            {"id": 11, "is_current": False, "is_next": False},
            {"id": 12, "is_current": True, "is_next": False},
            {"id": 13, "is_current": False, "is_next": True},
        ]
    }
    assert resolve_current_gameweek(bootstrap) == 12


def test_resolve_current_gameweek_falls_back_to_is_next():
    bootstrap = {
        "events": [
            {"id": 11, "is_current": False, "is_next": False},
            {"id": 12, "is_current": False, "is_next": True},
        ]
    }
    assert resolve_current_gameweek(bootstrap) == 12


def test_resolve_current_gameweek_falls_back_to_max_id():
    bootstrap = {"events": [{"id": 4}, {"id": 7}, {"id": 5}]}
    assert resolve_current_gameweek(bootstrap) == 7


def test_resolve_current_gameweek_empty_returns_none():
    assert resolve_current_gameweek({"events": []}) is None
