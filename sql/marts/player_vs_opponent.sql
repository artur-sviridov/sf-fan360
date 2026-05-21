-- Placeholder mart for Data Cloud federation. Per-player per-opponent aggregates
-- require event-level attribution; this project uses OpenFootball (results) and
-- Understat (xG) instead of StatsBomb open data.

CREATE OR REPLACE TABLE `sf-fan360.sf_fan360_marts.player_vs_opponent` AS
SELECT
  CAST(NULL AS STRING) AS season_id,
  CAST(NULL AS STRING) AS player,
  CAST(NULL AS STRING) AS team,
  CAST(NULL AS STRING) AS opponent,
  CAST(NULL AS INT64) AS goals,
  CAST(NULL AS FLOAT64) AS xg_total,
  CAST(NULL AS INT64) AS shots,
  CAST(NULL AS INT64) AS matches_played
LIMIT 0;
