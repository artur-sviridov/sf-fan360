"""Wikipedia loader for unstructured RAG content.

Pulls a seed list of EPL clubs, top players, and current managers, strips
wiki-markup, caps each document at 50 KB, and writes one file per entity to
`gs://<bucket>/wikipedia/<entity_type>/<slug>.txt` (or local disk in
ETL_LOCAL_ONLY mode).

Downstream, etl.embed chunks these into 500-token chunks for the vector
index.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd
import typer

from etl.config import settings
from etl.utils.io import safe_filename, write_parquet
from etl.utils.throttle import throttled

logger = logging.getLogger(__name__)

MAX_BYTES = 50 * 1024
USER_AGENT_BASE = "fan360-bot/0.1"

# Seed lists. Easy to grow over time. Slugs follow Wikipedia URL convention.
CLUB_SLUGS = [
    "Arsenal F.C.",
    "Aston Villa F.C.",
    "AFC Bournemouth",
    "Brentford F.C.",
    "Brighton %26 Hove Albion F.C.",
    "Chelsea F.C.",
    "Crystal Palace F.C.",
    "Everton F.C.",
    "Fulham F.C.",
    "Ipswich Town F.C.",
    "Leicester City F.C.",
    "Liverpool F.C.",
    "Manchester City F.C.",
    "Manchester United F.C.",
    "Newcastle United F.C.",
    "Nottingham Forest F.C.",
    "Southampton F.C.",
    "Tottenham Hotspur F.C.",
    "West Ham United F.C.",
    "Wolverhampton Wanderers F.C.",
]

MANAGER_SLUGS = [
    "Pep Guardiola",
    "J%C3%BCrgen Klopp",
    "Mikel Arteta",
    "Erik ten Hag",
    "Ange Postecoglou",
    "Unai Emery",
    "Eddie Howe",
    "Marco Silva",
    "Roberto De Zerbi",
    "Sean Dyche",
]

# Trim to top 50 for the v1 build; expand to 200 later if RAG quality demands.
PLAYER_SLUGS = [
    "Mohamed Salah",
    "Erling Haaland",
    "Harry Kane",
    "Kevin De Bruyne",
    "Bukayo Saka",
    "Bruno Fernandes",
    "Cole Palmer",
    "Son Heung-min",
    "Phil Foden",
    "Declan Rice",
    "Marcus Rashford",
    "Wayne Rooney",
    "Cristiano Ronaldo",
    "Thierry Henry",
    "Alan Shearer",
    "Frank Lampard",
    "Steven Gerrard",
    "Sergio Aguero",
    "Eric Cantona",
    "Ryan Giggs",
    "Paul Scholes",
    "Dennis Bergkamp",
    "Patrick Vieira",
    "Roy Keane",
    "Robin van Persie",
    "Luis Suarez",
    "Vincent Kompany",
    "Yaya Toure",
    "David Silva",
    "Gianfranco Zola",
    "Didier Drogba",
    "Petr Cech",
    "John Terry",
    "Rio Ferdinand",
    "Nemanja Vidic",
    "Ashley Cole",
    "Gary Neville",
    "David Beckham",
    "Eden Hazard",
    "N%27Golo Kant%C3%A9",
    "Sadio Mane",
    "Virgil van Dijk",
    "Andrew Robertson",
    "Trent Alexander-Arnold",
    "Riyad Mahrez",
    "Jamie Vardy",
    "Heung-Min Son",
    "Christian Eriksen",
    "James Maddison",
    "Bernardo Silva",
]


@dataclass(frozen=True)
class WikiDoc:
    entity_type: str
    slug: str
    title: str
    url: str
    text: str
    bytes: int


def _wiki_api():
    try:
        import wikipediaapi  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError('wikipedia-api not installed. `pip install -e ".[dev]"` first.') from exc
    return wikipediaapi.Wikipedia(
        user_agent=f"{USER_AGENT_BASE} ({settings.user_agent})",
        language="en",
    )


@throttled(rate_per_sec=2.0)
def _fetch_one(slug: str, entity_type: str) -> WikiDoc | None:
    wiki = _wiki_api()
    page = wiki.page(
        slug.replace("%26", "&").replace("%27", "'").replace("%C3%BC", "ü").replace("%C3%A9", "é")
    )
    if not page.exists():
        logger.warning("wikipedia: %s/%s not found", entity_type, slug)
        return None
    text = page.text.strip()
    encoded = text.encode("utf-8")[:MAX_BYTES]
    text = encoded.decode("utf-8", errors="ignore")
    return WikiDoc(
        entity_type=entity_type,
        slug=safe_filename(slug),
        title=page.title,
        url=page.fullurl,
        text=text,
        bytes=len(encoded),
    )


def fetch(
    *, include_players: bool = True, include_clubs: bool = True, include_managers: bool = True
) -> list[WikiDoc]:
    docs: list[WikiDoc] = []
    if include_clubs:
        for slug in CLUB_SLUGS:
            doc = _fetch_one(slug, "club")
            if doc:
                docs.append(doc)
    if include_managers:
        for slug in MANAGER_SLUGS:
            doc = _fetch_one(slug, "manager")
            if doc:
                docs.append(doc)
    if include_players:
        for slug in PLAYER_SLUGS:
            doc = _fetch_one(slug, "player")
            if doc:
                docs.append(doc)
    logger.info("wikipedia: fetched %d documents", len(docs))
    return docs


def to_parquet(docs: Iterable[WikiDoc] | None = None) -> str:
    docs = list(docs) if docs is not None else fetch()
    df = pd.DataFrame([d.__dict__ for d in docs])
    target = settings.parquet_target("wikipedia", "documents")
    write_parquet(
        df, target, partition_cols=["entity_type"] if "entity_type" in df.columns else None
    )
    logger.info("wikipedia: wrote %d documents to %s", len(df), target)
    return target


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(no_args_is_help=True, help="Wikipedia narrative loader.")


@app.command("run")
def cli_run(
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(
        level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    docs = fetch()
    target = to_parquet(docs)
    typer.echo(f"wikipedia: {len(docs)} docs -> {target}")


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
