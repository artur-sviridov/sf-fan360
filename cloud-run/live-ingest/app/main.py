"""FastAPI entrypoint for the live-ingest Cloud Run service."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import __version__
from app.bigquery_sink import ensure_live_events_table, write_rows
from app.config import settings
from app.webhooks.api_football import parse_api_football_batch
from app.webhooks.fpl import fetch_event_live, normalize_event_live

logger = logging.getLogger("live-ingest")
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="fan360-labs live-ingest", version=__version__)

_last_fpl_snapshot: dict[int, dict[int, dict[str, Any]]] = {}


@app.on_event("startup")
async def _startup() -> None:
    try:
        ensure_live_events_table()
    except Exception as exc:  # noqa: BLE001 - log and continue; service still serves /health
        logger.error("startup: ensure_live_events_table failed: %s", exc)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


@app.post("/webhook/api-football")
async def api_football_webhook(payload: dict[str, Any]) -> dict[str, int]:
    events = parse_api_football_batch(payload)
    n = write_rows([e.to_bq_row() for e in events])
    logger.info("api-football: persisted %d events", n)
    return {"written": n}


class FplPollRequest(BaseModel):
    gw: int


@app.post("/webhook/fpl")
async def fpl_webhook(req: FplPollRequest) -> dict[str, int]:
    """Triggered by Cloud Scheduler every 60 s during a configured fixture window."""
    payload = fetch_event_live(req.gw)
    diffs = normalize_event_live(req.gw, payload, previous=_last_fpl_snapshot.get(req.gw))
    _last_fpl_snapshot[req.gw] = {int(e["id"]): e for e in payload.get("elements", [])}
    n = write_rows([e.to_bq_row() for e in diffs])
    return {"written": n}


# ---------------------------------------------------------------------------
# Calendar refresh - pulls upcoming EPL fixtures from football-data.org so
# the Cloud Scheduler job knows when to start polling the FPL feed.
# ---------------------------------------------------------------------------


@app.get("/fixtures/upcoming")
async def upcoming_fixtures() -> dict[str, Any]:
    if not settings.football_data_api_key:
        raise HTTPException(503, "football-data API key not configured")
    async with httpx.AsyncClient(
        timeout=20,
        headers={
            "X-Auth-Token": settings.football_data_api_key,
            "User-Agent": settings.user_agent,
        },
    ) as client:
        r = await client.get(
            "https://api.football-data.org/v4/competitions/PL/matches",
            params={"status": "SCHEDULED"},
        )
        r.raise_for_status()
        body = r.json()
    matches = [
        {
            "id": m.get("id"),
            "utcDate": m.get("utcDate"),
            "matchday": m.get("matchday"),
            "home": (m.get("homeTeam") or {}).get("shortName"),
            "away": (m.get("awayTeam") or {}).get("shortName"),
        }
        for m in body.get("matches", [])
    ]
    return {"count": len(matches), "matches": matches}
