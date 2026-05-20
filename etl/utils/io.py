"""Parquet IO helpers that transparently write to local disk or GCS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from etl.config import settings


def write_parquet(df: pd.DataFrame, target: str, *, partition_cols: list[str] | None = None) -> str:
    """Write a DataFrame to Parquet.

    `target` may be a local path or a `gs://` URI. Returns the resolved
    target path so callers can log it.
    """
    if df.empty:
        # Materialize an empty file so downstream BigQuery loads do not fail
        # silently. The schema is preserved.
        table = pa.Table.from_pandas(df, preserve_index=False)
    else:
        table = pa.Table.from_pandas(df, preserve_index=False)

    if target.startswith("gs://"):
        # pyarrow can write directly to GCS via gcsfs; let it discover creds
        # from GOOGLE_APPLICATION_CREDENTIALS.
        if partition_cols:
            pq.write_to_dataset(
                table,
                root_path=target,
                partition_cols=partition_cols,
                use_dictionary=True,
            )
        else:
            pq.write_table(table, target)
    else:
        path = Path(target)
        if partition_cols:
            path.mkdir(parents=True, exist_ok=True)
            pq.write_to_dataset(
                table,
                root_path=str(path),
                partition_cols=partition_cols,
                use_dictionary=True,
            )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(table, str(path))
    return target


def read_parquet(target: str) -> pd.DataFrame:
    if target.startswith("gs://"):
        return pq.read_table(target).to_pandas()
    return pq.read_table(target).to_pandas()


def parquet_target(source: str, *parts: str) -> str:
    """Convenience wrapper around `settings.parquet_target`."""
    return settings.parquet_target(source, *parts)


def safe_filename(value: str) -> str:
    """Normalize a string for filesystem-safe use."""
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in value).strip("_")


def chunked(seq: list[Any], size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
