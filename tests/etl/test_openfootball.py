"""Unit tests for the OpenFootball loader.

We avoid network calls: tests feed crafted JSON through `_to_rows` and
verify the normalization invariants the downstream marts depend on.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from etl.openfootball import _extract_matchday, _parse_score, _to_rows


def test_parse_score_full_time():
    assert _parse_score([2, 1]) == (2, 1)


def test_parse_score_missing():
    assert _parse_score(None) == (None, None)
    assert _parse_score({}) == (None, None)


def test_parse_score_invalid_shape():
    assert _parse_score([1]) == (None, None)


def test_extract_matchday_basic():
    assert _extract_matchday("Matchday 7") == 7
    assert _extract_matchday("Round 23") == 23


def test_extract_matchday_no_digits():
    assert _extract_matchday(None) is None
    assert _extract_matchday("Quarter-final") is None


def test_to_rows_string_teams():
    """Current football.json uses plain strings for team1/team2."""
    blob = {
        "matches": [
            {
                "round": "Matchday 1",
                "date": "2010-08-14",
                "team1": "Tottenham Hotspur",
                "team2": "Manchester City",
                "score": {"ft": [0, 0]},
            }
        ]
    }
    rows = list(_to_rows("2010-11", blob))
    assert len(rows) == 1
    r = rows[0]
    assert r.home_team == "Tottenham Hotspur"
    assert r.away_team == "Manchester City"
    assert r.home_score == 0
    assert r.away_score == 0


def test_to_rows_top_level_matches():
    blob = {
        "matches": [
            {
                "round": "Matchday 1",
                "date": "2018-08-10",
                "team1": {"name": "Manchester United FC", "key": "man-united"},
                "team2": {"name": "Leicester City FC", "key": "leicester"},
                "score": {"ft": [2, 1], "ht": [1, 0]},
            }
        ]
    }
    rows = list(_to_rows("2018-19", blob))
    assert len(rows) == 1
    r = rows[0]
    assert r.season == "2018-19"
    assert r.matchday == 1
    assert r.date == date(2018, 8, 10)
    assert r.home_team == "Manchester United FC"
    assert r.away_team == "Leicester City FC"
    assert r.home_score == 2
    assert r.away_score == 1
    assert r.home_score_ht == 1
    assert r.away_score_ht == 0


def test_to_rows_nested_rounds():
    blob = {
        "rounds": [
            {
                "name": "Matchday 2",
                "matches": [
                    {
                        "date": "2024-08-24",
                        "team1": {"name": "Arsenal FC"},
                        "team2": {"name": "Aston Villa FC"},
                        "score": {"ft": [2, 0]},
                    }
                ],
            }
        ]
    }
    rows = list(_to_rows("2024-25", blob))
    assert len(rows) == 1
    r = rows[0]
    assert r.matchday == 2
    assert r.home_team == "Arsenal FC"
    assert r.home_score == 2
    assert r.away_score == 0
    assert r.home_score_ht is None


def test_to_rows_invalid_date():
    blob = {
        "matches": [
            {
                "round": "Matchday 3",
                "date": "not-a-date",
                "team1": {"name": "Liverpool FC"},
                "team2": {"name": "Chelsea FC"},
            }
        ]
    }
    rows = list(_to_rows("2024-25", blob))
    assert rows[0].date is None
    assert rows[0].home_score is None  # score block omitted entirely
