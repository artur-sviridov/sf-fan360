"""Orchestrator: refresh every source, load into BigQuery, run marts.

Idempotent. Re-runnable. Safe to schedule via Cloud Scheduler (when billing
is on) or to run manually during development.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from etl import bigquery_load, openfootball, understat, wikipedia
from etl.config import settings

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=False, help="Full ETL refresh.")


@app.command()
def main(
    skip_openfootball: bool = typer.Option(False),
    skip_understat: bool = typer.Option(False),
    skip_wikipedia: bool = typer.Option(False),
    skip_bigquery: bool = typer.Option(False, help="Stop after Parquet write."),
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(
        level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    logger.info("run_full: mode=%s project=%s", settings.mode(), settings.gcp_project_id)

    if not skip_openfootball:
        openfootball.to_parquet()
    if not skip_understat:
        understat.to_parquet()
    if not skip_wikipedia:
        wikipedia.to_parquet()

    if skip_bigquery:
        logger.info("run_full: skipping BigQuery load")
        return

    bigquery_load.ensure_datasets()

    if settings.etl_local_only:
        _load_local_native()
    else:
        _create_external_tables()

    bigquery_load.run_marts()


def _load_local_native() -> None:
    """Sandbox mode: load local Parquet directly into native BQ tables."""
    project = settings.gcp_project_id
    raw = settings.bq_dataset_raw
    data = settings.data_dir

    targets = [
        (f"{project}.{raw}.openfootball_matches", data / "openfootball" / "matches"),
        (f"{project}.{raw}.understat_matches", data / "understat" / "matches"),
        (f"{project}.{raw}.wikipedia_documents", data / "wikipedia" / "documents"),
    ]
    for table_id, source in targets:
        if not Path(source).exists():
            logger.warning("run_full: %s does not exist, skipping", source)
            continue
        bigquery_load.load_parquet_native(table_id, source)


def _create_external_tables() -> None:
    """Cloud mode: external tables over GCS Parquet."""
    project = settings.gcp_project_id
    raw = settings.bq_dataset_raw
    bucket = settings.gcs_raw_bucket

    sources = {
        "openfootball_matches": f"gs://{bucket}/openfootball/matches",
        "understat_matches": f"gs://{bucket}/understat/matches",
        "wikipedia_documents": f"gs://{bucket}/wikipedia/documents",
    }
    for table, gcs in sources.items():
        bigquery_load.create_external_table(f"{project}.{raw}.{table}", gcs)


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
