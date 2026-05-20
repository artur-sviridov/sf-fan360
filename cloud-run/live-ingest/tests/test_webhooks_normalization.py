"""Unit tests for the webhook normalizers. No network, no BigQuery."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `import app.*` when running from repo root.
SVC_ROOT = Path(__file__).resolve().parents[1]
if str(SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(SVC_ROOT))

from app.webhooks.api_football import parse_api_football_batch  # noqa: E402
from app.webhooks.fpl import normalize_event_live  # noqa: E402


def test_parse_api_football_batch_basic():
    payload = {
        "fixture": {
            "id": 12345,
            "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Liverpool"}},
        },
        "events": [
            {
                "time": {"elapsed": 23, "extra": None},
                "type": "Goal",
                "detail": "Normal Goal",
                "team": {"name": "Arsenal"},
                "player": {"name": "Bukayo Saka", "id": 99},
            }
        ],
    }
    events = parse_api_football_batch(payload)
    assert len(events) == 1
    e = events[0]
    assert e.source == "api-football"
    assert e.match_id == "12345"
    assert e.minute == 23
    assert e.event_type == "Goal"
    assert e.player == "Bukayo Saka"
    assert e.fixture_label == "Arsenal v Liverpool"


def test_normalize_event_live_diffs_goals():
    payload = {
        "elements": [
            {"id": 1, "stats": {"goals_scored": 2, "minutes": 67}},
            {"id": 2, "stats": {"goals_scored": 0, "yellow_cards": 1, "minutes": 70}},
        ]
    }
    previous = {
        1: {"stats": {"goals_scored": 1, "minutes": 60}},
        2: {"stats": {"goals_scored": 0, "yellow_cards": 0, "minutes": 55}},
    }
    events = normalize_event_live(gw=12, payload=payload, previous=previous)
    types = sorted(e.event_type for e in events)
    assert types == ["Goal", "Yellow Card"]
    goal = next(e for e in events if e.event_type == "Goal")
    assert goal.match_id == "gw-12"
    assert goal.source == "fpl"


def test_normalize_event_live_first_tick_no_history():
    # First poll of the day: previous is empty. Any nonzero stat is a new
    # event; this is acceptable because the simulator deduplicates by
    # event_id (gw-pid-stat-value).
    payload = {"elements": [{"id": 9, "stats": {"goals_scored": 1, "minutes": 30}}]}
    events = normalize_event_live(gw=1, payload=payload, previous=None)
    assert len(events) == 1
    assert events[0].event_id == "fpl-1-9-goals_scored-1"
