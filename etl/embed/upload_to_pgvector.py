"""Fallback vector store: pgvector on Supabase or self-hosted Postgres.

Used if Data Cloud Vector DB is gated in the Developer Edition org. The
table schema is:

    CREATE TABLE broadcast_knowledge (
        chunk_id     text PRIMARY KEY,
        source_url   text,
        title        text,
        entity_type  text,
        entity_slug  text,
        text         text,
        token_count  int,
        vector       vector(768)
    );
    CREATE INDEX ON broadcast_knowledge USING ivfflat (vector vector_cosine_ops);

The Cloud Run llm-shim exposes `/rag/search` against this table; Agentforce
calls that as an External Service Action (see Phase 5).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
import typer

logger = logging.getLogger(__name__)


def _chunks(seq: list[tuple], size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def upload(
    parquet: Path,
    *,
    dsn: str | None = None,
    table: str = "broadcast_knowledge",
    batch_size: int = 200,
    log_every_batches: int = 5,
) -> int:
    dsn = dsn or os.environ.get("PGVECTOR_DSN")
    if not dsn:
        raise RuntimeError("PGVECTOR_DSN not set")
    try:
        import psycopg
        from pgvector.psycopg import register_vector
        from psycopg import sql
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pip install psycopg pgvector for the fallback path") from exc

    df = pd.read_parquet(parquet)

    with psycopg.connect(dsn) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                CREATE TABLE IF NOT EXISTS {} (
                    chunk_id text PRIMARY KEY,
                    source_url text,
                    title text,
                    entity_type text,
                    entity_slug text,
                    text text,
                    token_count int,
                    vector vector(768)
                );
                """
                ).format(sql.Identifier(table))
            )

            stmt = sql.SQL(
                """
                INSERT INTO {} (chunk_id, source_url, title, entity_type, entity_slug, text, token_count, vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    source_url = EXCLUDED.source_url,
                    title      = EXCLUDED.title,
                    entity_type= EXCLUDED.entity_type,
                    entity_slug= EXCLUDED.entity_slug,
                    text       = EXCLUDED.text,
                    token_count= EXCLUDED.token_count,
                    vector     = EXCLUDED.vector
                """
            ).format(sql.Identifier(table))

            # Materialize rows in Python once so we can batch efficiently.
            rows: list[tuple] = []
            for r in df.itertuples(index=False):
                rows.append(
                    (
                        r.chunk_id,
                        r.source_url,
                        r.title,
                        r.entity_type,
                        r.entity_slug,
                        r.text,
                        int(r.token_count),
                        list(r.vector),
                    )
                )

            if batch_size <= 0:
                raise ValueError("batch_size must be > 0")

            total = len(rows)
            upserted = 0
            for batches, batch in enumerate(_chunks(rows, batch_size), start=1):
                cur.executemany(stmt, batch)
                conn.commit()
                upserted += len(batch)
                if log_every_batches > 0 and batches % log_every_batches == 0:
                    logger.info("pgvector: upserted %d/%d rows", upserted, total)

            cur.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS {} ON {} USING ivfflat (vector vector_cosine_ops);"
                ).format(sql.Identifier(f"{table}_vec_idx"), sql.Identifier(table))
            )
            conn.commit()

    logger.info("pgvector: upserted %d chunks", len(df))
    return len(df)


app = typer.Typer(no_args_is_help=False)


@app.command()
def main(
    parquet: Path = typer.Option(Path("data/embeddings/wikipedia.parquet")),
    table: str = typer.Option("broadcast_knowledge"),
    dsn: str | None = typer.Option(None),
    batch_size: int = typer.Option(200, help="Rows per transaction/commit."),
    log_every_batches: int = typer.Option(5, help="Log progress every N batches."),
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    n = upload(
        parquet,
        dsn=dsn,
        table=table,
        batch_size=batch_size,
        log_every_batches=log_every_batches,
    )
    typer.echo(f"pgvector upsert: {n}")


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
