-- Per-team per-season aggregates derived from the canonical match table.
-- Works across all OpenFootball seasons (2010/11-present) because it does not require
-- event-level data.

CREATE OR REPLACE TABLE `sf-fan360.sf_fan360_marts.team_season_stats` AS
WITH unioned AS (
  SELECT
    season,
    home_team AS team,
    away_team AS opponent,
    home_score AS goals_for,
    away_score AS goals_against,
    home_xg AS xg_for,
    away_xg AS xg_against,
    CASE
      WHEN home_score > away_score THEN 3
      WHEN home_score = away_score THEN 1
      ELSE 0
    END AS points
  FROM `sf-fan360.sf_fan360_marts.match`
  UNION ALL
  SELECT
    season,
    away_team AS team,
    home_team AS opponent,
    away_score,
    home_score,
    away_xg,
    home_xg,
    CASE
      WHEN away_score > home_score THEN 3
      WHEN away_score = home_score THEN 1
      ELSE 0
    END AS points
  FROM `sf-fan360.sf_fan360_marts.match`
)
SELECT
  season,
  team,
  COUNT(*) AS played,
  SUM(IF(points = 3, 1, 0)) AS wins,
  SUM(IF(points = 1, 1, 0)) AS draws,
  SUM(IF(points = 0, 1, 0)) AS losses,
  SUM(goals_for) AS goals_for,
  SUM(goals_against) AS goals_against,
  SUM(goals_for) - SUM(goals_against) AS goal_difference,
  SUM(points) AS points,
  SUM(xg_for) AS xg_for,
  SUM(xg_against) AS xg_against
FROM unioned
WHERE team IS NOT NULL
GROUP BY season, team
ORDER BY season DESC, points DESC, goal_difference DESC;
