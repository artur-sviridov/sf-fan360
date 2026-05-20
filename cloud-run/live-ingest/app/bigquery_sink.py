"""BigQuery streaming sink.

Uses the storage-write client where available; falls back to the legacy
`insert_rows_json` path for simplicity since the per-second event rate of a
matchday volume is trivially low.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from app.config import live_events_table_id

logger = logging.getLogger(__name__)


def _client():
    from google.cloud import bigquery  # type: ignore[import-not-found]

    return bigquery.Client()


def ensure_live_events_table() -> None:
    from google.cloud import bigquery  # type: ignore[import-not-found]

    client = _client()
    schema = [
        bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("mode", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("match_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fixture_label", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("minute", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("second", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("period", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("team", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("player", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("detail", "JSON", mode="NULLABLE"),
        bigquery.SchemaField("received_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(live_events_table_id(), schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="received_at",
    )
    client.create_table(table, exists_ok=True)
    logger.info("bq: ensured table %s", live_events_table_id())


def write_rows(rows: Iterable[dict[str, Any]]) -> int:
    client = _client()
    rows = list(rows)
    if not rows:
        return 0
    errors = client.insert_rows_json(live_events_table_id(), rows)
    if errors:
        logger.error("bq insert errors: %s", errors)
        raise RuntimeError(f"BigQuery insert failed: {errors}")
    return len(rows)
