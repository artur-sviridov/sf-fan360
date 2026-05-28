"""Chunk Wikipedia documents into ~500-token spans for vector indexing.

Reads `data/wikipedia/documents/` (or the equivalent GCS prefix), splits
each document with `langchain-text-splitters` using a 500-token target and
50-token overlap, emits a JSONL with one chunk per line.

Each chunk carries `entity_slug` so the agent can scope semantic search by
player / team / manager (prevents a Salah question retrieving Mané context).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import orjson
import pandas as pd
import typer

from etl.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_url: str
    title: str
    entity_type: str
    entity_slug: str
    text: str
    token_count: int


def _splitter():
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("langchain-text-splitters not installed") from exc

    # 500 tokens ~= 2000 chars; 50 tokens ~= 200 chars overlap.
    return RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_documents(docs: Iterable[dict[str, Any]]) -> list[Chunk]:
    splitter = _splitter()
    out: list[Chunk] = []
    for doc in docs:
        slug = doc["slug"]
        chunks = splitter.split_text(doc["text"])
        for i, c in enumerate(chunks):
            out.append(
                Chunk(
                    chunk_id=f"{slug}-{i:04d}",
                    source_url=doc["url"],
                    title=doc["title"],
                    entity_type=doc["entity_type"],
                    entity_slug=slug,
                    text=c,
                    token_count=_approx_tokens(c),
                )
            )
    return out


def _approx_tokens(text: str) -> int:
    # Rough approximation; avoids a tokenizer dependency for the chunker.
    # Real token count happens at embed time.
    return max(1, len(text) // 4)


def load_documents_from_parquet(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the Parquet produced by `etl.wikipedia.to_parquet`."""
    if path is None:
        path = settings.data_dir / "wikipedia" / "documents"
    if not path.exists():
        raise FileNotFoundError(f"wikipedia parquet not at {path}")
    df = pd.read_parquet(path)
    return df.to_dict(orient="records")


def write_jsonl(chunks: list[Chunk], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as fh:
        for c in chunks:
            fh.write(orjson.dumps(asdict(c)))
            fh.write(b"\n")
    logger.info("chunker: wrote %d chunks to %s", len(chunks), out_path)
    return len(chunks)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(no_args_is_help=False, help="Chunk Wikipedia documents.")


DEFAULT_OUT = Path("data/chunks/wikipedia.jsonl")


@app.command()
def main(
    parquet: Path | None = typer.Option(None, help="Override input Parquet folder."),
    out: Path = typer.Option(DEFAULT_OUT, help="Output JSONL."),
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(
        level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    docs = load_documents_from_parquet(parquet)
    chunks = chunk_documents(docs)
    write_jsonl(chunks, out)
    typer.echo(f"chunker: {len(docs)} docs -> {len(chunks)} chunks -> {out}")


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
