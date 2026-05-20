"""Smoke tests for `etl.config.settings`."""

from __future__ import annotations

import os
from pathlib import Path

from etl.config import REPO_ROOT, settings


def test_settings_loads():
    # Defaults should be populated; only env-driven fields may be None.
    assert settings.gcp_region
    assert settings.bq_dataset_raw == "sf_fan360_raw"
    assert settings.bq_dataset_marts == "sf_fan360_marts"
    assert settings.user_agent.startswith("fan360-bot")


def test_parquet_target_local_mode(monkeypatch):
    monkeypatch.setattr(settings, "etl_local_only", True)
    target = settings.parquet_target("openfootball", "matches")
    assert target.endswith("openfootball/matches") or target.endswith("openfootball\\matches")
    assert not target.startswith("gs://")


def test_parquet_target_gcs_mode(monkeypatch):
    monkeypatch.setattr(settings, "etl_local_only", False)
    monkeypatch.setattr(settings, "gcs_raw_bucket", "test-bucket")
    target = settings.parquet_target("understat", "matches")
    assert target.startswith("gs://")
    assert "understat/matches" in target


def test_google_credentials_applied_from_env_file(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    key = REPO_ROOT / ".secrets" / "etl-service.json"
    if not key.is_file():
        return  # skip when Phase 0 key not present locally
    monkeypatch.setattr(settings, "google_application_credentials", ".secrets/etl-service.json")
    from etl.config import _apply_google_credentials

    _apply_google_credentials(settings)
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(key.resolve())


def test_mode_switch(monkeypatch):
    monkeypatch.setattr(settings, "etl_local_only", True)
    assert settings.mode() == "local"
    monkeypatch.setattr(settings, "etl_local_only", False)
    assert settings.mode() == "gcs"
