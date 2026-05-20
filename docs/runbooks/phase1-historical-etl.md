# Phase 1 - Historical data ETL to BigQuery

**Goal.** End this phase with every EPL season shipped in OpenFootball `football.json` (currently **2010/11 through the in-progress season**, one `YYYY-YY/en.1.json` per year, ~380 matches each), Understat xG from 2014/15 onward, and Wikipedia narrative documents ready for chunking in Phase 4.

**Time budget.** ~2 hours of actual sit-at-keyboard. Some of that time is spent waiting for downloads and BigQuery loads.

**Prerequisites.** Phase 0 exit gate holds:

- `.env` is filled in with `GCP_PROJECT_ID`, API keys.
- `.venv` is active.
- BigQuery API enabled on the project (Phase 0 step 2b).

We are still **without billing** at this point (defer until Phase 2). BigQuery Sandbox handles everything in this phase.

---

## Step 1. Force local-only mode

Edit `.env`:

```
ETL_LOCAL_ONLY=1
```

This routes Parquet to `./data/<source>/...` instead of a GCS bucket. When you flip it back to `0` at the start of Phase 2 (after billing is on), the same loaders will write to GCS instead.

---

## Step 2. Pull each source

Each loader is independent and re-runnable. Run them in any order. Total disk footprint after all three: ~100 MB (mostly Understat).

```powershell
# OpenFootball - EPL results 2010/11 onward (~16 seasons, ~6k matches). ~5 MB. ~30 s.
python -m etl.openfootball

# Understat - per-season xG from 2014-15 to current. ~40 MB. Cached per
# season; first full run takes ~5 min.
python -m etl.understat

# Wikipedia - clubs + managers + top 50 players. ~3 MB. Takes ~1 min.
python -m etl.wikipedia
```

If Understat fails intermittently (network / rate-limit), just rerun. The caches in `etl/.cache/` mean nothing is re-fetched.

**Validation.**

```powershell
Get-ChildItem -Recurse data | Measure-Object -Property Length -Sum
# Expect total ~100 MB across openfootball, understat, and wikipedia folders.
```

---

## Step 3. Initialize BigQuery datasets

```powershell
python -m etl.bigquery_load ensure-datasets
```

If BigQuery is in Sandbox mode (no billing), the datasets are created with default 60-day table expiration. That is fine - re-run Phase 1 monthly to refresh.

---

## Step 4. Load Parquet into native BigQuery tables

```powershell
python -m etl.run_full --skip-openfootball --skip-understat --skip-wikipedia
```

This reuses the Parquet on disk and only runs the BigQuery side. Tables created in `sf_fan360_raw`:

- `openfootball_matches`
- `understat_matches`
- `wikipedia_documents`

The same command then executes every `.sql` file in `sql/marts/` in alphabetical order, producing tables in `sf_fan360_marts`.

---

## Step 5. Validate the marts

Open [https://console.cloud.google.com/bigquery](https://console.cloud.google.com/bigquery) and run the validation queries from the plan:

```sql
-- One row per season in sf-fan360_marts.match (~16 seasons from 2010/11 onward; ~380 matches each).
SELECT season, COUNT(*) AS n
FROM `sf-fan360.sf_fan360_marts.match`
GROUP BY 1
ORDER BY 1;

-- Sample xG-enriched fixtures (Understat join on match mart).
SELECT season, home_team, away_team, home_xg, away_xg
FROM `sf-fan360.sf_fan360_marts.match`
WHERE home_xg IS NOT NULL
ORDER BY season DESC, match_date DESC
LIMIT 20;

-- Team head-to-head (OpenFootball results spine).
SELECT team_a, team_b, played, wins
FROM `sf-fan360.sf_fan360_marts.head_to_head`
WHERE team_a = 'Chelsea' OR team_b = 'Chelsea'
ORDER BY played DESC
LIMIT 10;
```

**EVIDENCE.** Screenshot the BigQuery query results into `docs/trust-layer-evidence/01-phase1-marts.png`.

---

## EXIT GATE

- All three Parquet folders under `./data/` exist and contain `.parquet` files.
- BigQuery datasets `sf_360_raw` and `sf_360_marts` exist with the three raw tables and mart tables (`match`, `team_season_stats`, `head_to_head`, etc.) populated.
- The season-coverage query returns ~16 seasons with ~380 matches each.

Then proceed to [phase2-live-feed.md](phase2-live-feed.md).

---

## Notebook

`[notebooks/01_historical_validation.ipynb](../../notebooks/01_historical_validation.ipynb)`  
contains the same validation queries. Open with `jupyter lab` from the activated venv.