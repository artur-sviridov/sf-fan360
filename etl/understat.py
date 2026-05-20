"""Understat scraper.

Uses the `understatapi` package, which scrapes understat.com without an API
key. We throttle to <=1 req/s as a courtesy and cache responses to disk.

Pulls match-level xG summaries for the EPL from 2014/15 onward.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import typer

from etl.config import settings
from etl.utils.io import write_parquet
from etl.utils.throttle import throttled

logger = logging.getLogger(__name__)

EPL_LEAGUE = "EPL"
DEFAULT_FIRST_SEASON = 2014  # Understat's earliest EPL season.


def _understat():
    try:
        from understatapi import UnderstatClient  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "understatapi not installed. `pip install -e \".[dev]\"` first."
        ) from exc
    return UnderstatClient


@throttled(rate_per_sec=1.0)
def _fetch_season_matches(season: int) -> list[dict]:
    """Pull the per-fixture results for one season."""
    UnderstatClient = _understat()
    with UnderstatClient() as client:
        data = client.league(league=EPL_LEAGUE).get_match_data(season=str(season))
    if not isinstance(data, list):
        # understatapi returns either a list of dicts or, for some versions,
        # a dict keyed by match id; normalize to a list.
        data = list(data.values()) if isinstance(data, dict) else []
    for row in data:
        row["season"] = f"{season}-{str(season + 1)[2:]}"
    return data


def fetch(
    *,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Pull EPL match xG data across seasons.

    Caches per-season parquet inside `etl/.cache/understat/` so reruns are
    cheap and resilient to flaky scraping.
    """
    last_season = last_season or _current_season()
    frames: list[pd.DataFrame] = []

    cache_dir = settings.cache_path("understat")
    for season in range(first_season, last_season + 1):
        cache_path = Path(cache_dir) / f"matches-{season}.parquet"
        if use_cache and cache_path.exists():
            logger.info("understat: %s from cache", season)
            frames.append(pd.read_parquet(cache_path))
            continue
        try:
            rows = _fetch_season_matches(season)
        except Exception as exc:  # noqa: BLE001
            logger.warning("understat: season %s failed: %s", season, exc)
            continue
        df = pd.DataFrame(rows)
        df = _normalize(df)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info("understat: %s -> %d rows (cached)", season, len(df))
        frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten understat's nested h/a structures into flat columns."""
    if df.empty:
        return df

    def _team(col: str, side: str) -> pd.Series:
        return df[col].apply(lambda d: (d or {}).get(side) if isinstance(d, dict) else None)

    out = pd.DataFrame(
        {
            "season": df.get("season"),
            "match_id": df.get("id"),
            "datetime": pd.to_datetime(df.get("datetime"), errors="coerce"),
            "home_team": _team("h", "title"),
            "away_team": _team("a", "title"),
            "home_xg": pd.to_numeric(_team("xG", "h"), errors="coerce"),
            "away_xg": pd.to_numeric(_team("xG", "a"), errors="coerce"),
            "home_goals": pd.to_numeric(_team("goals", "h"), errors="coerce"),
            "away_goals": pd.to_numeric(_team("goals", "a"), errors="coerce"),
            "forecast_w": pd.to_numeric(_team("forecast", "w"), errors="coerce"),
            "forecast_d": pd.to_numeric(_team("forecast", "d"), errors="coerce"),
            "forecast_l": pd.to_numeric(_team("forecast", "l"), errors="coerce"),
        }
    )
    out["source"] = "understat"
    return out


def _current_season() -> int:
    today = pd.Timestamp.utcnow()
    # EPL season label uses the starting year. July onward = new season.
    return today.year if today.month >= 7 else today.year - 1


def to_parquet(df: pd.DataFrame | None = None) -> str:
    df = df if df is not None else fetch()
    target = settings.parquet_target("understat", "matches")
    write_parquet(df, target, partition_cols=["season"] if "season" in df.columns else None)
    logger.info("understat: wrote %d rows to %s", len(df), target)
    return target


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(no_args_is_help=True, help="Understat xG loader.")


@app.command("run")
def cli_run(
    first_season: int = typer.Option(DEFAULT_FIRST_SEASON),
    last_season: int | None = typer.Option(None),
    no_cache: bool = typer.Option(False, "--no-cache"),
    log_level: str = typer.Option("INFO"),
) -> None:
    logging.basicConfig(level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    df = fetch(first_season=first_season, last_season=last_season, use_cache=not no_cache)
    target = to_parquet(df)
    typer.echo(f"understat: {len(df)} rows -> {target}")


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
