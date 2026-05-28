"""Upload chunked Wikipedia content as Salesforce Knowledge articles.

Default: one article per chunk (production / full org storage).
``--granularity entity``: one article per Wikipedia entity (~80 rows) for
Developer Edition orgs with tight data storage (e.g. 5 MB).

Uses `simple_salesforce` and the local `sf` CLI session.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

import orjson
import typer

from etl.config import settings

logger = logging.getLogger(__name__)

KNOWLEDGE_RECORD_TYPE = "BroadcastKnowledge"

OnDuplicate = Literal["skip", "update", "fail"]
Granularity = Literal["chunk", "entity"]

# Optional dependency; keep import at module level for ruff/isort.
try:
    from simple_salesforce.exceptions import (  # type: ignore[import-not-found]
        SalesforceMalformedRequest,
    )
except ImportError:  # pragma: no cover
    SalesforceMalformedRequest = None  # type: ignore[assignment]

# Knowledge Body__c LongTextArea length in metadata
_MAX_BODY_CHARS = 32_000

_URL_NAME_RE = re.compile(r"[^a-zA-Z0-9\-]+")


def _url_name(chunk_id: str) -> str:
    """Knowledge UrlName: letters, digits, hyphens only; no leading/trailing hyphen."""
    name = _URL_NAME_RE.sub("-", chunk_id.replace("_", "-"))
    name = re.sub(r"-+", "-", name).strip("-")
    return (name[:240] if name else "chunk")


def _resolve_sf_cli() -> str:
    """Return a path to the Salesforce CLI executable.

    On Windows, ``subprocess`` cannot spawn bare ``sf`` (only ``sf.cmd`` is on
  PATH); ``shutil.which`` returns the full path.
    """
    for name in ("sf", "sf.cmd", "sf.exe"):
        if path := shutil.which(name):
            return path
    raise RuntimeError(
        "Salesforce CLI (`sf`) not found on PATH. Install from "
        "https://developer.salesforce.com/tools/salesforcecli "
        f"and run: sf org login web -a {settings.sf_org_alias}"
    )


def _sf_org() -> tuple[str, str]:
    """Get instance URL and access token from env or `sf org display`."""
    if settings.sf_instance_url and settings.sf_access_token:
        return settings.sf_instance_url, settings.sf_access_token

    sf = _resolve_sf_cli()
    result = subprocess.run(
        [sf, "org", "display", "-o", settings.sf_org_alias, "--json"],
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


def _existing_by_url_name(sf: Any) -> dict[str, str]:
    """Map UrlName -> Knowledge__kav Id for resume / idempotent uploads."""
    by_url: dict[str, str] = {}
    result = sf.query_all("SELECT Id, UrlName FROM Knowledge__kav WHERE UrlName != null")
    for rec in result.get("records", []):
        url = rec.get("UrlName")
        if url and url not in by_url:
            by_url[url] = rec["Id"]
    logger.info("found %d existing Knowledge articles by UrlName", len(by_url))
    return by_url


def _sf_error_code(exc: BaseException, code: str) -> bool:
    if SalesforceMalformedRequest is None or not isinstance(exc, SalesforceMalformedRequest):
        return False
    content = getattr(exc, "content", None) or []
    if isinstance(content, list):
        return any(err.get("errorCode") == code for err in content if isinstance(err, dict))
    return code in str(content)


def _iter_articles(jsonl: Path, granularity: Granularity):
    if granularity == "chunk":
        with jsonl.open("rb") as fh:
            for line in fh:
                if line.strip():
                    yield _build_article(orjson.loads(line))
        return

    by_entity: dict[str, list[dict[str, Any]]] = {}
    with jsonl.open("rb") as fh:
        for line in fh:
            if not line.strip():
                continue
            chunk = orjson.loads(line)
            by_entity.setdefault(chunk["entity_slug"], []).append(chunk)
    for slug in sorted(by_entity):
        yield _build_entity_article(by_entity[slug])


def upload_chunks(
    jsonl: Path,
    *,
    dry_run: bool = False,
    on_duplicate: OnDuplicate = "skip",
    granularity: Granularity = "chunk",
    max_articles: int | None = None,
) -> dict[str, int]:
    stats: dict[str, int] = {"created": 0, "skipped": 0, "updated": 0, "stopped_storage": 0}
    sf = None if dry_run else _simple_salesforce()
    existing: dict[str, str] = {} if dry_run else _existing_by_url_name(sf)

    for article in _iter_articles(jsonl, granularity):
        url_name = article["UrlName"]

        if dry_run:
            logger.info("DRY: would create %s", article["Title"])
            stats["created"] += 1
            if max_articles is not None and stats["created"] >= max_articles:
                break
            continue

        record_id = existing.get(url_name)
        if record_id:
            if on_duplicate == "skip":
                stats["skipped"] += 1
                continue
            if on_duplicate == "update":
                payload = {k: v for k, v in article.items() if k != "UrlName"}
                sf.Knowledge__kav.update(record_id, payload)  # type: ignore[union-attr]
                stats["updated"] += 1
                _log_progress(stats)
                continue

        try:
            result = sf.Knowledge__kav.create(article)  # type: ignore[union-attr]
        except Exception as exc:
            if on_duplicate == "skip" and _sf_error_code(exc, "DUPLICATE_VALUE"):
                logger.warning("skip duplicate UrlName (not in prefetch): %s", url_name)
                stats["skipped"] += 1
                continue
            if _sf_error_code(exc, "STORAGE_LIMIT_EXCEEDED"):
                stats["stopped_storage"] = 1
                logger.error(
                    "Org data storage limit reached (Article limit exceeded). "
                    "Use --granularity entity (~80 articles), --max-articles N, "
                    "delete draft Knowledge in Setup, or use a org with more storage. "
                    "created=%d skipped=%d",
                    stats["created"],
                    stats["skipped"],
                )
                break
            raise

        existing[url_name] = result["id"]
        stats["created"] += 1
        _log_progress(stats)

        if max_articles is not None and stats["created"] >= max_articles:
            logger.info("reached --max-articles %d", max_articles)
            break

    return stats


def _log_progress(stats: dict[str, int]) -> None:
    total = stats["created"] + stats["updated"]
    if total and total % 25 == 0:
        logger.info(
            "progress: %d created, %d updated, %d skipped",
            stats["created"],
            stats["updated"],
            stats["skipped"],
        )


def _build_entity_article(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """One Knowledge article per entity (all chunks concatenated)."""
    chunks.sort(key=lambda c: c.get("chunk_id", ""))
    first = chunks[0]
    parts = [c["text"] for c in chunks]
    body = "\n\n---\n\n".join(parts)
    if len(body) > _MAX_BODY_CHARS:
        body = body[: _MAX_BODY_CHARS - 20] + "\n\n[truncated]"

    article: dict[str, Any] = {
        "Title": first["title"],
        "UrlName": _url_name(first["entity_slug"]),
        "Summary": first["text"][:1000],
        "Body__c": body,
        "EntityType__c": first["entity_type"],
        "EntitySlug__c": first["entity_slug"],
        "Language": "en_US",
    }
    if source := first.get("source_url"):
        article["SourceUrl__c"] = source
    return article


def _build_article(chunk: dict[str, Any]) -> dict[str, Any]:
    """Build a Knowledge__kav row from a chunk JSON line.

    Uses standard ``Summary`` plus custom ``Body__c``, ``SourceUrl__c``,
    ``EntityType__c``, ``EntitySlug__c``. ``ExternalUrl`` / ``IsExternalData``
    are not available on all Knowledge editions (e.g. Developer Edition).
    """
    article: dict[str, Any] = {
        "Title": f"{chunk['title']} - chunk {chunk['chunk_id'].split('-')[-1]}",
        "UrlName": _url_name(chunk["chunk_id"]),
        "Summary": chunk["text"][:1000],
        "Body__c": chunk["text"],
        "EntityType__c": chunk["entity_type"],
        "EntitySlug__c": chunk["entity_slug"],
        "Language": "en_US",
    }
    if source := chunk.get("source_url"):
        article["SourceUrl__c"] = source
    return article


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(no_args_is_help=False)


@app.command()
def main(
    jsonl: Path = typer.Option(Path("data/chunks/wikipedia.jsonl")),
    dry_run: bool = typer.Option(False, "--dry-run"),
    granularity: Granularity = typer.Option(
        "chunk",
        "--granularity",
        help="chunk: one article per JSONL line (~4k). entity: one per Wikipedia entity (~80).",
    ),
    max_articles: int | None = typer.Option(
        None,
        "--max-articles",
        help="Stop after creating this many new articles (dev / storage caps).",
    ),
    on_duplicate: OnDuplicate = typer.Option(
        "skip",
        "--on-duplicate",
        help="skip: leave existing articles; update: overwrite; fail: stop on duplicate UrlName",
    ),
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stats = upload_chunks(
        jsonl,
        dry_run=dry_run,
        on_duplicate=on_duplicate,
        granularity=granularity,
        max_articles=max_articles,
    )
    msg = (
        f"created {stats['created']}, updated {stats['updated']}, skipped {stats['skipped']}"
    )
    if stats.get("stopped_storage"):
        msg += " (stopped: org storage limit)"
    typer.echo(msg)
    if stats.get("stopped_storage"):
        raise typer.Exit(code=2)


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
