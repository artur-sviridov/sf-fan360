"""OpenFootball / football.json loader.

Public-domain (CC0) JSON files at github.com/openfootball/football.json.
Loads every `YYYY-YY/en.1.json` EPL season in upstream football.json (2010-11
through current as of the cloned repo; grows when OpenFootball adds folders).

We clone the repo into the local cache, iterate every `*/en.1.json`, flatten
to one row per match, and write Parquet partitioned by season.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime
from pathlib import Path

import pandas as pd
import typer

from etl.config import settings
from etl.utils.io import write_parquet

logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/openfootball/football.json.git"
SEASON_DIR_RE = re.compile(r"^(\d{4})-(\d{2})$")
EN_PREMIER_FILE = "en.1.json"


@dataclass(frozen=True)
class MatchRow:
    season: str
    matchday: int | None
    date: date_type | None
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    home_score_ht: int | None
    away_score_ht: int | None
    source: str = "openfootball"


def _clone_or_pull(cache_dir: Path) -> Path:
    repo_dir = cache_dir / "football.json"
    if repo_dir.exists():
        logger.info("openfootball: pulling latest into %s", repo_dir)
        subprocess.run(
            ["git", "-C", str(repo_dir), "pull", "--quiet", "--ff-only"],
            check=True,
        )
    else:
        cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("openfootball: cloning %s into %s", REPO_URL, repo_dir)
        subprocess.run(
            ["git", "clone", "--depth=1", "--quiet", REPO_URL, str(repo_dir)],
            check=True,
        )
    return repo_dir


def _iter_season_files(repo_dir: Path) -> Iterable[tuple[str, Path]]:
    for child in sorted(repo_dir.iterdir()):
        if not child.is_dir():
            continue
        if not SEASON_DIR_RE.match(child.name):
            continue
        candidate = child / EN_PREMIER_FILE
        if candidate.exists():
            yield child.name, candidate


def _parse_score(raw: dict | list | None) -> tuple[int | None, int | None]:
    """Score may live under `score.ft` (list of two ints) or be missing."""
    if not raw:
        return None, None
    if isinstance(raw, list) and len(raw) == 2:
        return int(raw[0]), int(raw[1])
    return None, None


def _team_label(team: object) -> str:
    if isinstance(team, str):
        return team
    if isinstance(team, dict):
        return str(team.get("name") or team.get("key") or "")
    return ""


def _to_rows(season: str, blob: dict) -> Iterable[MatchRow]:
    matches = blob.get("matches") or []
    rounds = blob.get("rounds") or []
    # Some season files use `rounds[].matches`; others use top-level `matches`.
    if rounds and not matches:
        for r in rounds:
            for m in r.get("matches", []):
                yield from _row_from_match(season, m, round_label=r.get("name"))
    else:
        for m in matches:
            yield from _row_from_match(season, m, round_label=m.get("round"))


def _row_from_match(season: str, m: dict, *, round_label: str | None) -> Iterable[MatchRow]:
    score = m.get("score") or {}
    ft = score.get("ft")
    ht = score.get("ht")
    date_raw = m.get("date")
    parsed_date: date_type | None = None
    if isinstance(date_raw, str):
        try:
            parsed_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None

    matchday = _extract_matchday(round_label)

    ft_home, ft_away = _parse_score(ft)
    ht_home, ht_away = _parse_score(ht)

    yield MatchRow(
        season=season,
        matchday=matchday,
        date=parsed_date,
        home_team=_team_label(m.get("team1")),
        away_team=_team_label(m.get("team2")),
        home_score=ft_home,
        away_score=ft_away,
        home_score_ht=ht_home,
        away_score_ht=ht_away,
    )


def _extract_matchday(label: str | None) -> int | None:
    if not label:
        return None
    match = re.search(r"(\d+)", label)
    return int(match.group(1)) if match else None


def fetch(*, cache_dir: Path | None = None) -> pd.DataFrame:
    """Pull every EPL season from OpenFootball, return a long DataFrame."""
    cache_dir = cache_dir or settings.cache_path("openfootball")
    repo_dir = _clone_or_pull(cache_dir)

    rows: list[MatchRow] = []
    for season, json_path in _iter_season_files(repo_dir):
        try:
            blob = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("openfootball: skipping %s due to JSON error: %s", json_path, exc)
            continue
        season_rows = list(_to_rows(season, blob))
        rows.extend(season_rows)
        logger.info("openfootball: %s -> %d matches", season, len(season_rows))

    df = pd.DataFrame([r.__dict__ for r in rows])
    if not df.empty:
        df = df.sort_values(["season", "date", "home_team"]).reset_index(drop=True)
    return df


def to_parquet(df: pd.DataFrame | None = None, *, target: str | None = None) -> str:
    df = df if df is not None else fetch()
    target = target or settings.parquet_target("openfootball", "matches")
    write_parquet(df, target, partition_cols=["season"])
    logger.info("openfootball: wrote %d rows to %s", len(df), target)
    return target


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(no_args_is_help=True, help="OpenFootball loader.")


@app.command("run")
def cli_run(
    target: str | None = typer.Option(None, help="Override parquet target path."),
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    df = fetch()
    out = to_parquet(df, target=target)
    typer.echo(f"openfootball: {len(df)} matches -> {out}")


def cli() -> None:
    """Console-script entry."""
    app()


if __name__ == "__main__":
    cli()
