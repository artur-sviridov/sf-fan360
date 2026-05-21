"""Wire-format models shared across webhook handlers and the BigQuery sink."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LiveEvent(BaseModel):
    """Canonical event shape persisted to BigQuery `live_events` table.

    API-Football and FPL Bootstrap webhooks normalize to this.
    """

    event_id: str
    source: Literal["api-football", "fpl"]
    mode: Literal["live"] = "live"
    match_id: int | str
    fixture_label: str | None = None
    minute: int | None = None
    second: int | None = None
    period: int | None = None
    event_type: str
    team: str | None = None
    player: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    def to_bq_row(self) -> dict[str, Any]:
        row = self.model_dump()
        row["received_at"] = self.received_at.isoformat()
        return row
