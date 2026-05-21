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


def upload(parquet: Path, *, dsn: str | None = None, table: str = "broadcast_knowledge") -> int:
    dsn = dsn or os.environ.get("PGVECTOR_DSN")
    if not dsn:
        raise RuntimeError("PGVECTOR_DSN not set")
    try:
        import psycopg
        from pgvector.psycopg import register_vector
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pip install psycopg pgvector for the fallback path") from exc

    df = pd.read_parquet(parquet)

    with psycopg.connect(dsn) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
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
            )
            for _, row in df.iterrows():
                cur.execute(
                    f"""
                    INSERT INTO {table} (chunk_id, source_url, title, entity_type, entity_slug, text, token_count, vector)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        source_url = EXCLUDED.source_url,
                        title      = EXCLUDED.title,
                        text       = EXCLUDED.text,
                        token_count= EXCLUDED.token_count,
                        vector     = EXCLUDED.vector
                    """,
                    (
                        row["chunk_id"],
                        row["source_url"],
                        row["title"],
                        row["entity_type"],
                        row["entity_slug"],
                        row["text"],
                        int(row["token_count"]),
                        list(row["vector"]),
                    ),
                )
            cur.execute(f"CREATE INDEX IF NOT EXISTS {table}_vec_idx ON {table} USING ivfflat (vector vector_cosine_ops);")
        conn.commit()
    logger.info("pgvector: upserted %d chunks", len(df))
    return len(df)


app = typer.Typer(no_args_is_help=False)


@app.command()
def main(
    parquet: Path = typer.Option(Path("data/embeddings/wikipedia.parquet")),
    table: str = typer.Option("broadcast_knowledge"),
    dsn: str | None = typer.Option(None),
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    n = upload(parquet, dsn=dsn, table=table)
    typer.echo(f"pgvector upsert: {n}")


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
