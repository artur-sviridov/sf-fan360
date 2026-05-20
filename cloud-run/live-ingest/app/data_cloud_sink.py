"""Salesforce Data Cloud Ingestion API client.

Mints a JWT-bearer access token against the connected app created in
Phase 3 (`IngestionApiClient`), then POSTs batches of LiveEvent rows to
the `LiveEvents` Ingestion API source.

The Cloud Run service double-publishes:
- BigQuery for analytics + later Calculated Insights.
- Data Cloud Ingestion API for sub-second freshness in Agentforce.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from collections.abc import Iterable

import httpx

from app.config import settings
from app.models import LiveEvent

logger = logging.getLogger(__name__)

JWT_AUDIENCE = "https://login.salesforce.com"
JWT_LIFETIME_SECONDS = 180

_token_cache: dict[str, tuple[str, float]] = {}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _mint_jwt() -> str:
    """Mint a short-lived RS256 JWT for the connected app."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    client_id = os.environ.get("SF_INGEST_CLIENT_ID")
    username = os.environ.get("SF_INGEST_USERNAME")
    key_b64 = os.environ.get("SF_INGEST_PRIVATE_KEY")
    if not (client_id and username and key_b64):
        raise RuntimeError("Data Cloud Ingestion is not configured")

    private_key = serialization.load_pem_private_key(
        key_b64.encode() if isinstance(key_b64, str) else key_b64,
        password=None,
    )

    header = {"alg": "RS256", "typ": "JWT"}
    now = int(time.time())
    claims = {
        "iss": client_id,
        "sub": username,
        "aud": JWT_AUDIENCE,
        "exp": now + JWT_LIFETIME_SECONDS,
    }
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}".encode()
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input.decode()}.{_b64url(signature)}"


def _exchange_jwt(jwt: str) -> str:
    """Exchange the assertion for a Data Cloud access token."""
    r = httpx.post(
        f"{JWT_AUDIENCE}/services/oauth2/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _get_access_token() -> str:
    cached = _token_cache.get("token")
    if cached and cached[1] > time.time() + 30:
        return cached[0]
    jwt = _mint_jwt()
    token = _exchange_jwt(jwt)
    _token_cache["token"] = (token, time.time() + JWT_LIFETIME_SECONDS - 60)
    return token


def publish(events: Iterable[LiveEvent], *, source_name: str = "LiveEvents") -> int:
    """POST a batch of events to Data Cloud Ingestion API."""
    if not settings.sf_ingest_url:
        logger.debug("data-cloud: SF_INGEST_URL not set; skipping")
        return 0
    rows = [_to_payload(e) for e in events]
    if not rows:
        return 0
    token = _get_access_token()
    url = f"{settings.sf_ingest_url}/api/v1/ingest/sources/{source_name}/LiveEvents"
    r = httpx.post(
        url,
        json={"data": rows},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    logger.info("data-cloud: published %d events to %s", len(rows), source_name)
    return len(rows)


def _to_payload(e: LiveEvent) -> dict:
    """Match the OpenAPI schema published to Data Cloud."""
    return {
        "event_id": e.event_id,
        "source": e.source,
        "mode": e.mode,
        "match_id": str(e.match_id),
        "fixture_label": e.fixture_label,
        "minute": e.minute,
        "second": e.second,
        "period": e.period,
        "event_type": e.event_type,
        "team": e.team,
        "player": e.player,
        "detail": json.dumps(e.detail) if e.detail else None,
        "received_at": e.received_at.isoformat(),
    }
