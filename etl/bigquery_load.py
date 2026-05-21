"""BigQuery dataset + table provisioning.

Two flavors:

1. **Sandbox / local-only mode** (`settings.etl_local_only=True`): we use
   `bq load` of local Parquet files into native BigQuery tables. Works
   without billing enabled. Tables auto-expire after 60 days per Sandbox
   policy; ETL is idempotent so just re-run.

2. **Cloud mode** (default once billing is on): create external tables over
   GCS parquet folders so re-loading is free, then materialize view-shaped
   marts on top.

Both modes converge on the same logical schema in `sf_fan360_raw` and
`sf_fan360_marts`. The mart SQL lives in `sql/marts/*.sql`.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
import typer

from etl.config import settings

logger = logging.getLogger(__name__)


def _bq_client():
    try:
        from google.cloud import bigquery  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("google-cloud-bigquery not installed") from exc
    return bigquery.Client(project=settings.gcp_project_id, location=settings.gcp_bq_location)


def ensure_datasets(client=None) -> None:
    from google.cloud import bigquery  # type: ignore[import-not-found]

    client = client or _bq_client()
    for name in (settings.bq_dataset_raw, settings.bq_dataset_marts):
        ref = bigquery.Dataset(f"{settings.gcp_project_id}.{name}")
        ref.location = settings.gcp_bq_location
        ref.description = f"Fan360 Labs - {name} dataset (Scenario 7 second-screen build)"
        client.create_dataset(ref, exists_ok=True)
        logger.info("bigquery: ensured dataset %s.%s", ref.project, ref.dataset_id)


def _hive_keys_from_path(parquet_file: Path, root: Path) -> dict[str, str]:
    """Read `key=value` folder segments from a Hive-style layout."""
    try:
        rel = parquet_file.relative_to(root)
    except ValueError:
        return {}
    out: dict[str, str] = {}
    for segment in rel.parts[:-1]:
        if "=" in segment:
            key, val = segment.split("=", 1)
            out[key] = val
    return out


def _dataframe_from_parquet(parquet_file: Path, root: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_file)
    for key, val in _hive_keys_from_path(parquet_file, root).items():
        if key not in df.columns:
            df[key] = val
    return df


def load_parquet_native(table_id: str, source: str | Path, *, schema_auto: bool = True) -> None:
    """Load a Parquet file or folder into a native BigQuery table.

    Used in Sandbox mode where external tables over GCS are unavailable.
    """
    from google.cloud import bigquery  # type: ignore[import-not-found]

    client = _bq_client()
    path = Path(source) if not str(source).startswith("gs://") else None

    if path and path.is_dir():
        files = sorted(path.rglob("*.parquet"))
        if not files:
            logger.warning("bigquery: %s has no parquet files; skipping", path)
            return
        logger.info("bigquery: loading %d parquet files into %s", len(files), table_id)
        write_mode = bigquery.WriteDisposition.WRITE_TRUNCATE
        for f in files:
            df = _dataframe_from_parquet(f, path)
            job_config = bigquery.LoadJobConfig(
                write_disposition=write_mode,
                autodetect=schema_auto,
            )
            job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
            job.result()
            write_mode = bigquery.WriteDisposition.WRITE_APPEND
    elif path:
        df = _dataframe_from_parquet(path, path.parent)
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            autodetect=schema_auto,
        )
        job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
        job.result()
    else:
        uri = str(source)
        if not uri.endswith("*.parquet"):
            uri = uri.rstrip("/") + "/*.parquet"
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            autodetect=schema_auto,
        )
        job_config.hive_partitioning_options = bigquery.HivePartitioningOptions(
            mode=bigquery.HivePartitioningOptions.Mode.AUTO
        )
        job = client.load_table_from_uri(uri, table_id, job_config=job_config)
        job.result()

    table = client.get_table(table_id)
    logger.info("bigquery: %s now has %d rows", table_id, table.num_rows)


def create_external_table(table_id: str, gcs_pattern: str) -> None:
    """Create an external BigQuery table over a GCS Parquet folder.

    Free, recompute-on-query. Use in cloud mode (Phase 2 onward).
    """
    from google.cloud import bigquery  # type: ignore[import-not-found]

    client = _bq_client()
    external_config = bigquery.ExternalConfig(bigquery.ExternalSourceFormat.PARQUET)
    external_config.source_uris = [gcs_pattern.rstrip("/") + "/*.parquet"]
    table = bigquery.Table(table_id)
    table.external_data_configuration = external_config
    client.delete_table(table_id, not_found_ok=True)
    client.create_table(table)
    logger.info("bigquery: external table %s -> %s", table_id, gcs_pattern)


def run_sql_file(path: Path | str) -> None:
    """Execute a `.sql` file with project / dataset placeholder substitution.

    Placeholders the loader understands:
      ${project}        -> settings.gcp_project_id
      ${dataset_raw}    -> settings.bq_dataset_raw
      ${dataset_marts}  -> settings.bq_dataset_marts

    Also tolerates the literal `sf-fan360` from hand-written templates -
    rewritten to the configured project ID so the templates remain readable.
    """

    client = _bq_client()
    sql = Path(path).read_text(encoding="utf-8")
    sql = (
        sql
        .replace("${project}", settings.gcp_project_id)
        .replace("${dataset_raw}", settings.bq_dataset_raw)
        .replace("${dataset_marts}", settings.bq_dataset_marts)
        .replace("sf-fan360", settings.gcp_project_id)
        .replace("sf_fan360_raw", settings.bq_dataset_raw)
        .replace("sf_fan360_marts", settings.bq_dataset_marts)
    )
    # Statement terminators only (ignore semicolons inside `--` comments).
    statements = [s.strip() for s in re.split(r";\s*(?=\n|$)", sql) if s.strip()]
    for stmt in statements:
        logger.info("bigquery: running %s", stmt.split("\n", 1)[0][:80])
        client.query(stmt).result()


# Marts must run in dependency order (not alphabetical).
_MART_SQL_ORDER = (
    "match.sql",
    "team_season_stats.sql",
    "head_to_head.sql",
    "player_vs_opponent.sql",
)


def run_marts() -> None:
    marts_dir = settings.repo_root / "sql" / "marts"
    for name in _MART_SQL_ORDER:
        sql_file = marts_dir / name
        if not sql_file.exists():
            logger.warning("bigquery: mart %s missing, skipping", name)
            continue
        run_sql_file(sql_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(no_args_is_help=True, help="BigQuery provisioning + loading.")


@app.command("ensure-datasets")
def cli_ensure() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ensure_datasets()


@app.command("load-native")
def cli_load(
    table: str = typer.Option(..., help="Fully-qualified table id: project.dataset.table"),
    source: str = typer.Option(..., help="Local path or gs:// uri"),
) -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_parquet_native(table, source)


@app.command("external")
def cli_external(
    table: str = typer.Option(...),
    gcs: str = typer.Option(..., help="gs://bucket/prefix"),
) -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    create_external_table(table, gcs)


@app.command("marts")
def cli_marts() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run_marts()


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
