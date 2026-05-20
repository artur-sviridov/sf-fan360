"""Generate embeddings for chunked Wikipedia content using free Gemini API.

Reads the JSONL produced by `etl.embed.chunker`, calls
`text-embedding-004` via the Gemini Developer API (no Vertex billing), and
writes a Parquet with one row per chunk plus a `vector` column.

Output is consumed by:
- `etl.embed.upload_to_pgvector` (fallback path).
- The Phase 4 runbook's Data Cloud Vector DB upload (primary path).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx
import orjson
import pandas as pd
import typer
from tenacity import retry, stop_after_attempt, wait_exponential

from etl.config import settings

logger = logging.getLogger(__name__)

EMBED_ENDPOINT_TPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=20))
def embed_one(text: str, *, model: str | None = None) -> list[float]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    model = model or settings.gemini_embed_model
    url = EMBED_ENDPOINT_TPL.format(model=model)
    r = httpx.post(
        url,
        params={"key": settings.gemini_api_key},
        json={
            "model": f"models/{model}",
            "content": {"parts": [{"text": text}]},
        },
        timeout=30,
    )
    if r.status_code >= 400:
        logger.warning("embed_one: status=%s body=%s", r.status_code, r.text[:200])
    r.raise_for_status()
    body = r.json()
    return body["embedding"]["values"]


def embed_chunks(chunks: list[dict[str, Any]], *, sleep: float = 0.2) -> pd.DataFrame:
    """Embed every chunk. Returns DataFrame with original columns + `vector`."""
    out: list[dict[str, Any]] = []
    for i, c in enumerate(chunks):
        try:
            vec = embed_one(c["text"])
        except Exception as exc:  # noqa: BLE001
            logger.error("embed: chunk %s failed: %s", c.get("chunk_id"), exc)
            continue
        row = dict(c)
        row["vector"] = vec
        out.append(row)
        if (i + 1) % 50 == 0:
            logger.info("embed: %d/%d", i + 1, len(chunks))
        time.sleep(sleep)
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(no_args_is_help=False)


@app.command()
def main(
    jsonl: Path = typer.Option(Path("data/chunks/wikipedia.jsonl")),
    out: Path = typer.Option(Path("data/embeddings/wikipedia.parquet")),
    sleep_seconds: float = typer.Option(0.2),
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    chunks = [orjson.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    df = embed_chunks(chunks, sleep=sleep_seconds)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    typer.echo(f"embed: {len(df)} vectors -> {out}")


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
