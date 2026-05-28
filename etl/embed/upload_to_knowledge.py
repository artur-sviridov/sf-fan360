"""Upload chunked Wikipedia content as Salesforce Knowledge articles.

One article per chunk so the agent can cite a precise URL fragment. Uses
`simple_salesforce` against the `s7dev` org, authenticated through the
local `sf` CLI session.

Articles use a custom record type `BroadcastKnowledge` (see
`force-app/main/default/objects/Knowledge__kav/...`).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

import orjson
import typer

from etl.config import settings

logger = logging.getLogger(__name__)

KNOWLEDGE_RECORD_TYPE = "BroadcastKnowledge"


def _sf_org():
    """Get an access token + instance URL by shelling out to `sf org display`."""
    result = subprocess.run(
        ["sf", "org", "display", "-o", settings.sf_org_alias, "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    data = orjson.loads(result.stdout)["result"]
    return data["instanceUrl"], data["accessToken"]


def _simple_salesforce():
    try:
        from simple_salesforce import Salesforce  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "simple-salesforce not installed. `pip install simple-salesforce`."
        ) from exc
    instance, token = _sf_org()
    return Salesforce(instance_url=instance, session_id=token)


def upload_chunks(jsonl: Path, *, dry_run: bool = False) -> int:
    sf = None if dry_run else _simple_salesforce()
    n = 0
    with jsonl.open("rb") as fh:
        for line in fh:
            if not line.strip():
                continue
            chunk = orjson.loads(line)
            article = _build_article(chunk)
            if dry_run:
                logger.info("DRY: would create %s", article["Title"])
            else:
                sf.Knowledge__kav.create(article)  # type: ignore[union-attr]
            n += 1
            if n % 25 == 0:
                logger.info("uploaded %d chunks", n)
    return n


def _build_article(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "Title": f"{chunk['title']} - chunk {chunk['chunk_id'].split('-')[-1]}",
        "UrlName": chunk["chunk_id"].replace("_", "-")[:240],
        "Summary__c": chunk["text"][:255],
        "Body__c": chunk["text"],
        "SourceUrl__c": chunk["source_url"],
        "EntityType__c": chunk["entity_type"],
        "EntitySlug__c": chunk["entity_slug"],
        "Language": "en_US",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(no_args_is_help=False)


@app.command()
def main(
    jsonl: Path = typer.Option(Path("data/chunks/wikipedia.jsonl")),
    dry_run: bool = typer.Option(False, "--dry-run"),
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(
        level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    n = upload_chunks(jsonl, dry_run=dry_run)
    typer.echo(f"uploaded {n} articles")


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
