"""Service configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gcp_project_id: str = Field(default="sf-fan360")
    bq_dataset_raw: str = Field(default="sf_fan360_raw")
    bq_location: str = Field(default="EU")

    live_events_table: str = Field(default="live_events")
    api_football_key: str | None = Field(default=None)
    football_data_api_key: str | None = Field(default=None)

    # FPL official endpoints don't need a key.
    fpl_bootstrap_url: str = Field(
        default="https://fantasy.premierleague.com/api/bootstrap-static/"
    )
    fpl_event_live_url_tpl: str = Field(
        default="https://fantasy.premierleague.com/api/event/{gw}/live/"
    )

    # Salesforce Data Cloud Ingestion API (filled by Phase 3).
    sf_ingest_url: str | None = Field(default=None)
    sf_ingest_token: str | None = Field(default=None)

    user_agent: str = "fan360-labs-live-ingest/0.1"


settings = Settings()


def live_events_table_id() -> str:
    return f"{settings.gcp_project_id}.{settings.bq_dataset_raw}.{settings.live_events_table}"
