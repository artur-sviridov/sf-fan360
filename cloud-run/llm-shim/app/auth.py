"""Shared-secret authentication for callers (Salesforce Named Credential).

The Named Credential injects `X-Shim-Auth: <secret>` on every request. The
shim compares against `SHIM_SHARED_SECRET` (read from Secret Manager at
container startup). Rejected requests get a 401.

This is intentionally simple: the shim is private (Cloud Run with
`--no-allow-unauthenticated`), and the shared secret is the second factor
inside the trust boundary.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from app.config import settings


def require_shared_secret(x_shim_auth: str | None = Header(default=None)) -> None:
    expected = settings.shim_shared_secret
    if not expected:
        # Mis-configured shim - fail closed.
        raise HTTPException(503, "shim shared secret not configured")
    if not x_shim_auth or not hmac.compare_digest(x_shim_auth, expected):
        raise HTTPException(401, "invalid X-Shim-Auth")
