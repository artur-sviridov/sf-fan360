"""Centralized configuration loaded from environment / .env.

Every other module reads from `etl.config.settings` rather than touching
`os.environ` directly. This keeps the credential surface auditable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = REPO_ROOT / "etl" / ".cache"


class Settings(BaseSettings):
    """Project-wide settings.

    Values are read from `.env` at repo root, then overridden by any process
    environment variables. Missing required values raise on first access -
    fail-fast is preferable to silent misconfiguration.
    """

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # GCP core
    gcp_project_id: str = Field(default="sf-fan360")
    gcp_region: str = Field(default="europe-west1")
    gcp_bq_location: str = Field(default="EU")
    google_application_credentials: str | None = Field(default=None)

    # BigQuery
    bq_dataset_raw: str = Field(default="sf_fan360_raw")
    bq_dataset_marts: str = Field(default="sf_fan360_marts")
    gcs_raw_bucket: str = Field(default="sf-fan360-raw")

    # Source API keys
    football_data_api_key: str | None = Field(default=None)
    api_football_key: str | None = Field(default=None)

    # LLM
    gemini_api_key: str | None = Field(default=None)
    gemini_primary_model: str = Field(default="gemini-2.5-flash")
    gemini_fallback_model: str = Field(default="gemini-2.5-flash-lite")
    gemini_embed_model: str = Field(default="gemini-embedding-001")
    gemini_embed_dimensions: int = Field(default=768)

    # Salesforce
    sf_org_alias: str = Field(default="football_agent")
    sf_instance_url: str | None = Field(default=None)
    sf_access_token: str | None = Field(default=None)
    sf_ingest_client_id: str | None = Field(default=None)
    sf_ingest_username: str | None = Field(default=None)
    sf_ingest_private_key_path: str | None = Field(default=None)
    sf_ingest_audience: str = Field(default="https://login.salesforce.com")

    # Cloud Run shim
    llm_shim_shared_secret: str | None = Field(default=None)
    llm_shim_url: str | None = Field(default=None)

    # Local dev toggles
    etl_local_only: bool = Field(default=False)

    # Repo paths (computed, not env)
    repo_root: Path = REPO_ROOT
    data_dir: Path = DATA_DIR
    cache_dir: Path = CACHE_DIR

    # Shared HTTP behavior
    user_agent: str = "fan360-bot/0.1 (+github.com/fan360-labs)"

    def parquet_target(self, source: str, *parts: str) -> str:
        """Resolve where a Parquet shard should land.

        - In local-only mode returns `./data/<source>/<parts>/`.
        - Otherwise returns `gs://<bucket>/<source>/<parts>/`.
        """
        joined = "/".join(parts) if parts else ""
        if self.etl_local_only:
            target = DATA_DIR / source / joined
            target.parent.mkdir(parents=True, exist_ok=True)
            return str(target)
        bucket = self.gcs_raw_bucket
        prefix = f"{source}/{joined}" if joined else source
        return f"gs://{bucket}/{prefix}"

    def cache_path(self, source: str, *parts: str) -> Path:
        path = CACHE_DIR / source
        for part in parts:
            path = path / part
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def mode(self) -> Literal["local", "gcs"]:
        return "local" if self.etl_local_only else "gcs"


def _apply_google_credentials(s: Settings) -> None:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    raw = s.google_application_credentials
    if not raw:
        return
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"GOOGLE_APPLICATION_CREDENTIALS file not found: {path}. "
            "Set the path in `.env` or run `gcloud auth application-default login`."
        )
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)


settings = Settings()
_apply_google_credentials(settings)
