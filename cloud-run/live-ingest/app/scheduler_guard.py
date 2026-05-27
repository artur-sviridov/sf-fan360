"""Fixture-driven Cloud Scheduler control for the FPL poll job.

The FPL poll job (``fpl-poll`` in Cloud Scheduler) fires
``POST /webhook/fpl`` every minute. Running it 24/7 wastes Cloud Run
invocations, so a sibling "guard" job (``fpl-poll-guard``, every 5
minutes) hits ``POST /scheduler/sync`` on this service. ``sync`` reads
the EPL calendar from football-data.org, computes the active match
window per fixture, and resumes / pauses ``fpl-poll`` accordingly.

Window rules (UTC):
    * window start: kickoff - ``pre_kickoff_minutes``
    * default end:  kickoff + ``match_duration_minutes`` + ``post_match_minutes``
    * in-play matches extend the end to ``now + post_match_minutes`` so the
      poll keeps running through stoppage / extra time. Once the status
      flips to ``FINISHED`` no further extension happens, so the window
      closes ``post_match_minutes`` after the last in-play tick.

When at least one fixture is in window, the job is resumed with the
current Fantasy Premier League gameweek in the HTTP body so
``/webhook/fpl`` queries the right ``/event/{gw}/live`` endpoint.

Failure mode is fail-safe: any uncaught error pauses the poll job.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from dateutil import parser as date_parser

from app.config import settings
from app.webhooks.fpl import fetch_bootstrap

logger = logging.getLogger(__name__)


FOOTBALL_DATA_MATCHES_URL = "https://api.football-data.org/v4/competitions/PL/matches"

_IN_PLAY_STATUSES = frozenset({"IN_PLAY", "LIVE", "PAUSED"})


@dataclass(frozen=True)
class MatchWindow:
    """Single fixture's poll window."""

    match_id: str
    kickoff_utc: datetime
    window_start: datetime
    window_end: datetime
    status: str
    label: str = ""


@dataclass
class SyncSummary:
    """JSON-serializable summary of one ``/scheduler/sync`` call."""

    action: str
    job_state: str
    gw: int | None = None
    active_windows: int = 0
    matches_considered: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "action": self.action,
            "job_state": self.job_state,
            "gw": self.gw,
            "active_windows": self.active_windows,
            "matches_considered": self.matches_considered,
        }
        if self.detail:
            out["detail"] = self.detail
        return out


# ---------------------------------------------------------------------------
# Pure helpers (no I/O)
# ---------------------------------------------------------------------------


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.isoparse(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def poll_window(match: dict[str, Any], now: datetime) -> MatchWindow | None:
    """Return a :class:`MatchWindow` for one football-data.org match.

    ``None`` is returned for matches that are already long finished or
    that lack a parseable kickoff time.
    """
    kickoff = _parse_utc(match.get("utcDate"))
    if kickoff is None:
        return None

    status = (match.get("status") or "").upper()
    home = (match.get("homeTeam") or {}).get("shortName") or ""
    away = (match.get("awayTeam") or {}).get("shortName") or ""
    label = f"{home} v {away}".strip(" v")

    pre = timedelta(minutes=settings.pre_kickoff_minutes)
    post = timedelta(minutes=settings.post_match_minutes)
    duration = timedelta(minutes=settings.match_duration_minutes)

    window_start = kickoff - pre
    window_end = kickoff + duration + post

    if status in _IN_PLAY_STATUSES:
        live_end = now + post
        window_end = max(window_end, live_end)

    return MatchWindow(
        match_id=str(match.get("id") or ""),
        kickoff_utc=kickoff,
        window_start=window_start,
        window_end=window_end,
        status=status or "UNKNOWN",
        label=label,
    )


def active_windows(matches: Iterable[dict[str, Any]], now: datetime) -> list[MatchWindow]:
    """Return the windows currently covering ``now``."""
    out: list[MatchWindow] = []
    for m in matches:
        w = poll_window(m, now)
        if w is None:
            continue
        if w.window_start <= now <= w.window_end:
            out.append(w)
    return out


def any_match_in_poll_window(matches: Iterable[dict[str, Any]], now: datetime) -> bool:
    return bool(active_windows(matches, now))


def resolve_current_gameweek(bootstrap: dict[str, Any] | None = None) -> int | None:
    """Pick the FPL gameweek id to drive ``/webhook/fpl`` with.

    Preference order: ``is_current`` -> ``is_next`` -> latest event id.
    """
    if bootstrap is None:
        try:
            bootstrap = fetch_bootstrap()
        except httpx.HTTPError as exc:
            logger.warning("scheduler_guard: bootstrap fetch failed: %s", exc)
            return None

    events = bootstrap.get("events") or []
    if not events:
        return None

    for ev in events:
        if ev.get("is_current"):
            return int(ev["id"])
    for ev in events:
        if ev.get("is_next"):
            return int(ev["id"])
    try:
        return int(max(int(ev["id"]) for ev in events if "id" in ev))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# I/O: football-data + Cloud Scheduler
# ---------------------------------------------------------------------------


def fetch_pl_matches(
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Fetch Premier League matches in the given UTC window.

    ``date_from`` / ``date_to`` default to today +/- the configured
    ``guard_lookback_days`` / ``guard_lookahead_days`` to absorb
    timezone edges in the football-data.org calendar.
    """
    if not settings.football_data_api_key:
        raise RuntimeError("football-data API key not configured")

    today = datetime.now(UTC).date()
    date_from = date_from or datetime.combine(
        today - timedelta(days=settings.guard_lookback_days), datetime.min.time(), tzinfo=UTC
    )
    date_to = date_to or datetime.combine(
        today + timedelta(days=settings.guard_lookahead_days), datetime.min.time(), tzinfo=UTC
    )

    params = {
        "dateFrom": date_from.date().isoformat(),
        "dateTo": date_to.date().isoformat(),
    }
    owns_client = client is None
    client = client or httpx.Client(
        timeout=20,
        headers={
            "X-Auth-Token": settings.football_data_api_key,
            "User-Agent": settings.user_agent,
        },
    )
    try:
        r = client.get(FOOTBALL_DATA_MATCHES_URL, params=params)
        r.raise_for_status()
        body = r.json()
    finally:
        if owns_client:
            client.close()
    return list(body.get("matches", []))


def _scheduler_client():
    from google.cloud import scheduler_v1  # type: ignore[import-not-found]

    return scheduler_v1.CloudSchedulerClient()


def _job_path(client: Any) -> str:
    return client.job_path(
        settings.gcp_project_id, settings.scheduler_location, settings.fpl_poll_job_id
    )


def _set_job_body(client: Any, job_name: str, gw: int) -> str | None:
    """Update the HTTP target body of the poll job to the current gw.

    Returns the gw previously encoded in the body (or ``None`` when we
    cannot tell), so callers can avoid noisy ``update_job`` calls.
    """
    from google.protobuf.field_mask_pb2 import FieldMask  # type: ignore[import-not-found]

    job = client.get_job(name=job_name)
    previous_gw: int | None = None
    if job.http_target and job.http_target.body:
        try:
            previous_gw = int(json.loads(job.http_target.body.decode("utf-8")).get("gw"))
        except (ValueError, json.JSONDecodeError):
            previous_gw = None
    if previous_gw == gw:
        return previous_gw

    job.http_target.body = json.dumps({"gw": gw}).encode("utf-8")
    mask = FieldMask(paths=["http_target.body"])
    client.update_job(job=job, update_mask=mask)
    return previous_gw


def sync_fpl_poll_scheduler(*, now: datetime | None = None) -> SyncSummary:
    """Resume the poll job when a match is in window, pause it otherwise.

    Designed to be called every few minutes by ``fpl-poll-guard``. Any
    error pauses the poll job and is reflected in the returned summary.
    """
    now = now or datetime.now(UTC)

    try:
        matches = fetch_pl_matches()
    except Exception as exc:
        logger.exception("scheduler_guard: fetch_pl_matches failed: %s", exc)
        return _safe_pause(reason=f"football-data error: {exc}")

    windows = active_windows(matches, now)
    summary = SyncSummary(
        action="noop",
        job_state="UNKNOWN",
        active_windows=len(windows),
        matches_considered=len(matches),
    )

    try:
        client = _scheduler_client()
        job_name = _job_path(client)
    except Exception as exc:
        logger.exception("scheduler_guard: client init failed: %s", exc)
        summary.action = "error"
        summary.detail["error"] = str(exc)
        return summary

    if not windows:
        try:
            client.pause_job(name=job_name)
            summary.action = "paused"
            summary.job_state = "PAUSED"
        except Exception as exc:
            logger.exception("scheduler_guard: pause failed: %s", exc)
            summary.action = "error"
            summary.detail["error"] = f"pause: {exc}"
        return summary

    gw = resolve_current_gameweek()
    if gw is None:
        logger.warning("scheduler_guard: could not resolve current gameweek; pausing")
        summary.detail["warning"] = "no current gameweek"
        return _safe_pause(
            reason="no current gameweek",
            base=summary,
            client=client,
            job_name=job_name,
        )

    summary.gw = gw
    summary.detail["windows"] = [
        {
            "match_id": w.match_id,
            "kickoff": w.kickoff_utc.isoformat(),
            "window_end": w.window_end.isoformat(),
            "status": w.status,
            "label": w.label,
        }
        for w in windows
    ]

    try:
        previous_gw = _set_job_body(client, job_name, gw)
        if previous_gw not in (None, gw):
            summary.detail["previous_gw"] = previous_gw
        client.resume_job(name=job_name)
        summary.action = "resumed"
        summary.job_state = "ENABLED"
    except Exception as exc:
        logger.exception("scheduler_guard: resume failed: %s", exc)
        summary.action = "error"
        summary.detail["error"] = f"resume: {exc}"
    return summary


def _safe_pause(
    *,
    reason: str,
    base: SyncSummary | None = None,
    client: Any | None = None,
    job_name: str | None = None,
) -> SyncSummary:
    summary = base or SyncSummary(action="paused", job_state="PAUSED")
    summary.action = "paused"
    summary.job_state = "PAUSED"
    summary.detail["reason"] = reason

    if client is None:
        try:
            client = _scheduler_client()
            job_name = _job_path(client)
        except Exception as exc:
            logger.exception("scheduler_guard: client init failed during safe pause: %s", exc)
            summary.action = "error"
            summary.detail["error"] = str(exc)
            return summary
    try:
        client.pause_job(name=job_name)
    except Exception as exc:
        logger.exception("scheduler_guard: safe pause failed: %s", exc)
        summary.action = "error"
        summary.detail["error"] = f"safe-pause: {exc}"
    return summary
