# BigQuery SQL

Declarative SQL kept under version control. The Python ETL applies these
files; no business logic lives inside the loader.

| File | Purpose |
|---|---|
| `marts/match.sql` | Unified canonical match view across OpenFootball + Understat |
| `marts/team_season_stats.sql` | Per-team per-season aggregates |
| `marts/head_to_head.sql` | Pairwise summary for any team pair |
| `marts/player_vs_opponent.sql` | Placeholder schema for Data Cloud (no player-event source in this build) |

All scripts assume datasets `sf_fan360_raw` and `sf_fan360_marts` exist in project
`sf-fan360`. The Python loader sets these via `etl.config.settings`;
edit `.env` if you renamed them.

Naming inside scripts uses `${project}.${dataset}.<table>` placeholders that
the loader substitutes via parameterized queries. See
`etl/bigquery_load.py::run_sql_file` for the substitution.
