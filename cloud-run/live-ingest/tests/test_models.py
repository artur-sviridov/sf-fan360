"""Tests for the canonical LiveEvent model."""

from __future__ import annotations

import sys
from pathlib import Path

SVC_ROOT = Path(__file__).resolve().parents[1]
if str(SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(SVC_ROOT))

from app.models import LiveEvent  # noqa: E402


def test_live_event_to_bq_row_serializes_timestamp():
    ev = LiveEvent(
        event_id="x",
        source="fpl",
        match_id="gw-1",
        event_type="Goal",
    )
    row = ev.to_bq_row()
    assert "received_at" in row
    assert isinstance(row["received_at"], str)
    assert row["mode"] == "live"
    assert row["match_id"] == "gw-1"
