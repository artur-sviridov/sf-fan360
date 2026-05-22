"""Shim configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = Field(default="")
    primary_model: str = Field(default="gemini-2.5-flash")
    fallback_model: str = Field(default="gemini-2.5-flash-lite")
    embed_model: str = Field(default="text-embedding-004")

    shim_shared_secret: str = Field(default="")
    cache_ttl_seconds: int = Field(default=60)
    cache_maxsize: int = Field(default=512)

    pgvector_dsn: str = Field(default="")
    pgvector_table: str = Field(default="broadcast_knowledge")

    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta")
    request_timeout_seconds: float = Field(default=30.0)


settings = Settings()
