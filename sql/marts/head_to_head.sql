-- Pairwise team-vs-team summary across every season.
-- Symmetric: each team-pair appears in both (A,B) and (B,A) directions so
-- the agent's lookup does not need a sort step.

CREATE OR REPLACE TABLE `sf-fan360.sf_fan360_marts.head_to_head` AS
WITH oriented AS (
  SELECT
    home_team AS team_a,
    away_team AS team_b,
    home_score AS goals_a,
    away_score AS goals_b,
    home_xg AS xg_a,
    away_xg AS xg_b,
    season,
    match_date
  FROM `sf-fan360.sf_fan360_marts.match`
  UNION ALL
  SELECT
    away_team,
    home_team,
    away_score,
    home_score,
    away_xg,
    home_xg,
    season,
    match_date
  FROM `sf-fan360.sf_fan360_marts.match`
)
SELECT
  team_a,
  team_b,
  COUNT(*) AS played,
  SUM(IF(goals_a > goals_b, 1, 0)) AS wins,
  SUM(IF(goals_a = goals_b, 1, 0)) AS draws,
  SUM(IF(goals_a < goals_b, 1, 0)) AS losses,
  SUM(goals_a) AS goals_for,
  SUM(goals_b) AS goals_against,
  SUM(xg_a) AS xg_for,
  SUM(xg_b) AS xg_against,
  MIN(match_date) AS first_meeting,
  MAX(match_date) AS last_meeting
FROM oriented
WHERE team_a IS NOT NULL AND team_b IS NOT NULL
GROUP BY team_a, team_b;
