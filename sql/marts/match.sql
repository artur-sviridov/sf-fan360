-- Canonical match table unifying OpenFootball results spine with
-- Understat xG (where seasons overlap). One row per fixture.
--
-- Foreign keys downstream:
--   season             -- e.g. "2018-19"
--   match_key          -- season || date || home_team_norm || away_team_norm
--
-- Team-name normalization is intentionally minimal here; full canonical
-- mapping happens in Salesforce Data Cloud Identity Resolution (Phase 3).

CREATE OR REPLACE TABLE `sf-fan360.sf_fan360_marts.match` AS
WITH base AS (
  SELECT
    season,
    matchday,
    CAST(date AS DATE) AS match_date,
    home_team,
    away_team,
    home_score,
    away_score,
    home_score_ht,
    away_score_ht,
    'openfootball' AS source
  FROM `sf-fan360.sf_fan360_raw.openfootball_matches`
  WHERE home_team IS NOT NULL AND away_team IS NOT NULL
),
xg AS (
  SELECT
    season,
    DATE(datetime) AS match_date,
    home_team,
    away_team,
    home_xg,
    away_xg
  FROM `sf-fan360.sf_fan360_raw.understat_matches`
)
SELECT
  CONCAT(
    base.season, '|',
    CAST(base.match_date AS STRING), '|',
    LOWER(REGEXP_REPLACE(base.home_team, r'[^a-zA-Z0-9]', '')), '|',
    LOWER(REGEXP_REPLACE(base.away_team, r'[^a-zA-Z0-9]', ''))
  ) AS match_key,
  base.season,
  base.matchday,
  base.match_date,
  base.home_team,
  base.away_team,
  base.home_score,
  base.away_score,
  base.home_score_ht,
  base.away_score_ht,
  xg.home_xg,
  xg.away_xg,
  CASE
    WHEN base.home_score IS NULL OR base.away_score IS NULL THEN NULL
    WHEN base.home_score > base.away_score THEN base.home_team
    WHEN base.home_score < base.away_score THEN base.away_team
    ELSE 'draw'
  END AS winner,
  base.source
FROM base
LEFT JOIN xg
  USING (season, match_date, home_team, away_team);
