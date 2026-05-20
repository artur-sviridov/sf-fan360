"""Tests for the shared-secret check."""

from __future__ import annotations

import sys
from pathlib import Path

SVC_ROOT = Path(__file__).resolve().parents[1]
if str(SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(SVC_ROOT))

import pytest
from fastapi import HTTPException

from app import auth as auth_mod  # noqa: E402
from app.auth import require_shared_secret  # noqa: E402


def test_rejects_when_unconfigured(monkeypatch):
    monkeypatch.setattr(auth_mod.settings, "shim_shared_secret", "")
    with pytest.raises(HTTPException) as ei:
        require_shared_secret(x_shim_auth="anything")
    assert ei.value.status_code == 503


def test_rejects_wrong_secret(monkeypatch):
    monkeypatch.setattr(auth_mod.settings, "shim_shared_secret", "expected")
    with pytest.raises(HTTPException) as ei:
        require_shared_secret(x_shim_auth="wrong")
    assert ei.value.status_code == 401


def test_accepts_correct_secret(monkeypatch):
    monkeypatch.setattr(auth_mod.settings, "shim_shared_secret", "expected")
    # No exception = accepted.
    require_shared_secret(x_shim_auth="expected")


def test_rejects_missing_header(monkeypatch):
    monkeypatch.setattr(auth_mod.settings, "shim_shared_secret", "expected")
    with pytest.raises(HTTPException):
        require_shared_secret(x_shim_auth=None)
