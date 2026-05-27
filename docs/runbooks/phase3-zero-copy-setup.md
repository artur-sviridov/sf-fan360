# Phase 3 — Data Cloud Zero Copy + Ingestion API

**Goal.** Federate BigQuery marts into Data Cloud without copying data, publish Calculated Insights for the agent, and stream live match events through the Ingestion API into `Fan360LiveEvents__dlm`.

**Prerequisites.** Phase 2 exit gate (`live-ingest` deployed, `sf_fan360_raw.live_events` in BigQuery). Salesforce org alias `football_agent`. GCP project `sf-fan360`, region `europe-central2`.

**Time budget.** ~4 hours.

**Reference metadata.** SQL and CI definitions live in `[force-app/main/default/calculatedInsights/](../../force-app/main/default/calculatedInsights/)`.

---

## How the data model fits together


| Layer                    | Naming                                           | Role                                  |
| ------------------------ | ------------------------------------------------ | ------------------------------------- |
| BigQuery table           | `sf_fan360_marts.*`, `sf_fan360_raw.live_events` | Source of truth                       |
| Data stream              | Wizard name (e.g. `PlayerVsOpponent`)            | Federation or Ingestion API connector |
| Data Lake Object (DLO)   | `*__dll`                                         | Stream landing schema in Data Cloud   |
| Data Model Object (DMO)  | `Fan360*__dlm`                                   | Mapped model the agent and CIs query  |
| Calculated Insight (CIO) | `*__cio`                                         | Aggregated SQL over DMOs              |


Use the `**Fan360`** prefix on custom DMOs (Profile / Other / Engagement). Map streams from **Data Streams → [stream] → Map to Data Model**.

One stream can feed **multiple DMOs**. For `player_vs_opponent`, create both `Fan360Player__dlm` (identity) and `Fan360PlayerVsOpponent__dlm` (metrics).

---

## Step 1. Confirm Data Cloud is provisioned

1. **Setup** → Quick Find **Data Cloud Setup** → status **Provisioned**.
2. Open the **Data Cloud** app.
3. Confirm data space `**default`** exists. Use `**default**` for every stream, DMO, and Calculated Insight in this project.

---

## Step 2. BigQuery federation (Identity Provider Based)

Official guide: [Set Up a Google BigQuery Data Federation Connection](https://developer.salesforce.com/docs/data/data-cloud-int/guide/c360-a-set-up-bigquery-connection.html).

### 2a. Salesforce connector

1. **Setup** → **My Domain** → copy the **My Domain URL** (root URL, no trailing slash). Example shape: `https://<org>-dev-ed.develop.my.salesforce.com`.
2. **Data Cloud Setup** → **More Connectors** → **New** → **Google BigQuery**.
3. Connection name: `**Fan360 BigQuery Federation`**.
4. Authentication: **Identity Provider Based**.
5. Copy **External ID** from the wizard and keep the tab open until GCP grants are saved.

### 2b. GCP service account

```powershell
gcloud config set project sf-fan360

gcloud iam service-accounts create sf-fan360-datacloud `
  --display-name="Fan 360 Data Cloud Reader"

$SA = "sf-fan360-datacloud@sf-fan360.iam.gserviceaccount.com"
foreach ($role in @(
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
    "roles/bigquery.metadataViewer",
    "roles/bigquery.readSessionUser")) {
  gcloud projects add-iam-policy-binding sf-fan360 `
    --member="serviceAccount:$SA" --role=$role
}
```

### 2c. Workload Identity Federation

**GCP Console** → **IAM & Admin** → **Workload Identity Federation** → your pool → **Add provider** → **OpenID Connect (OIDC)**:


| Setting            | Value                                                                   |
| ------------------ | ----------------------------------------------------------------------- |
| Issuer (URL)       | `{My Domain}/services/connectors`                                       |
| Allowed audiences  | My Domain root URL (no path, no trailing slash)                         |
| Attribute mappings | `attribute.audi` = `assertion.aud` ; `google.subject` = `assertion.sub` |


On the provider, add **two** grants under **Grant access using service account impersonation**:


| Grant type | Attribute | Value                                                       |
| ---------- | --------- | ----------------------------------------------------------- |
| Audience   | `audi`    | My Domain root URL                                          |
| Subject    | `subject` | External ID from §2a (paste exactly as shown in Salesforce) |


Service account for both grants: `**sf-fan360-datacloud@sf-fan360.iam.gserviceaccount.com`**.

### 2d. Finish the Salesforce connection

1. On the WIF provider, download the **OIDC client configuration JSON**.
2. Save a local backup as `**.secrets/sf-fan360-datacloud-wif-oidc.json`** (gitignored).
3. In Salesforce, paste the full JSON into **OIDC Client Config**.
4. Set **Service Account Email** to `sf-fan360-datacloud@sf-fan360.iam.gserviceaccount.com` and **Project ID** to `sf-fan360`.
5. **Test Connection** → **Save**.

**Evidence.** Screenshot → `docs/trust-layer-evidence/03-zero-copy-connected.png`.

---

## Step 3. BigQuery data streams (Zero Copy)

**Data Cloud** → **Data Streams** → **New** → **BigQuery (Federation)** → select **Fan360 BigQuery Federation**.

Create one stream per table. **Data space:** `default`. **Refresh:** Full Refresh, weekly.


| BigQuery table                       | Stream name          | Category   | Primary key                                    | Event time    |
| ------------------------------------ | -------------------- | ---------- | ---------------------------------------------- | ------------- |
| `sf_fan360_marts.match`              | `Match`              | Other      | `match_key`                                    | —             |
| `sf_fan360_marts.team_season_stats`  | `Team Season Stats`  | Other      | Composite: `season` + `team`                   | —             |
| `sf_fan360_marts.head_to_head`       | `Head to Head`       | Other      | Composite: `team_a` + `team_b`                 | —             |
| `sf_fan360_marts.player_vs_opponent` | `Player vs Opponent` | Other      | Composite: `season_id` + `player` + `opponent` | —             |
| `sf_fan360_raw.live_events`          | `Live Events`        | Engagement | `event_id`                                     | `received_at` |


On the field-mapping step, set types to match BigQuery: dimensions such as `season`, `team`, `player` as **Text**; metrics as **Number**; dates as **Date**; `received_at` as **DateTime**.

Deploy each stream. Resulting DLOs use the `__dll` suffix (for example `PlayerVsOpponent__dll`).

The `player_vs_opponent` mart is currently a schema-only placeholder (`LIMIT 0` in BigQuery). The stream and CIs still deploy; rows appear when the mart is populated later.

### Optional: retrieve stream metadata into the repo

```powershell
sf project retrieve start -o football_agent `
  --target-metadata-dir .retrieve-tmp --unzip `
  --metadata "DataStreamDefinition:Match" `
  --metadata "DataStreamDefinition:HeadToHead" `
  --metadata "DataStreamDefinition:TeamSeasonStats" `
  --metadata "DataStreamDefinition:PlayerVsOpponent" `
  --metadata "DataStreamDefinition:LiveEvents" `
  --metadata "MktDataTranObject:Match" `
  --metadata "MktDataTranObject:HeadToHead" `
  --metadata "MktDataTranObject:TeamSeasonStats" `
  --metadata "MktDataTranObject:PlayerVsOpponent" `
  --metadata "MktDataTranObject:LiveEvents"
```

Copy retrieved files into `force-app/main/default/dataStreamDefinitions/` and `mktDataTranObjects/`. Wizard object names have no `__dll` suffix.

---

## Step 4. Data model objects and stream mappings

Create each DMO under **Data Cloud** → **Data Model** → **New**. Enter the fields from the tables below (API names and types must match before you map streams).

Map every stream from **Data Streams → [stream] → Map to Data Model** (pick target DMO, map fields, save). Repeat for each target DMO on the same stream.

DLO fields appear with a `__c` suffix in mapping (for example `goals__c`, `player__c`).

### 4a. Profile and dimension DMOs

**Fan360 Player** — `Fan360Player__dlm`, category **Profile**, primary key `unified_player_id`:


| Label              | API name             | Type      |
| ------------------ | -------------------- | --------- |
| Unified Player Id  | `unified_player_id`  | Text (PK) |
| Player Name        | `player_name`        | Text      |
| Source Player Name | `source_player_name` | Text      |
| Name Normalized    | `name_normalized`    | Text      |
| Date of Birth      | `date_of_birth`      | Date      |


**Fan360 Team** — `Fan360Team__dlm`, category **Other**, primary key `canonical_team_id`:


| Label             | API name            | Type      |
| ----------------- | ------------------- | --------- |
| Canonical Team Id | `canonical_team_id` | Text (PK) |
| Team Name         | `team_name`         | Text      |
| Source Team Name  | `source_team_name`  | Text      |


**Team name lookup.** Upload `[docs/team-mapping.csv](../team-mapping.csv)` via a **File Upload** stream → `TeamMapping__dll`. Use it for alias resolution in the agent; do not map that file onto `Fan360Team__dlm`.

### 4b. Fact DMOs

**Fan360 Player Vs Opponent** — `Fan360PlayerVsOpponent__dlm`, category **Other**:


| Label          | API name         | Type      |
| -------------- | ---------------- | --------- |
| Season Id      | `season_id`      | Text (PK) |
| Player         | `player`         | Text      |
| Team           | `team`           | Text      |
| Opponent       | `opponent`       | Text      |
| Goals          | `goals`          | Number    |
| XG Total       | `xg_total`       | Number    |
| Shots          | `shots`          | Number    |
| Matches Played | `matches_played` | Number    |


**Fan360 Team Season Stats** — `Fan360TeamSeasonStats__dlm`, category **Other** (team-level mart; there is no player-season mart in BigQuery):


| Label           | API name          | Type      |
| --------------- | ----------------- | --------- |
| Season          | `season`          | Text (PK) |
| Team            | `team`            | Text      |
| Played          | `played`          | Number    |
| Wins            | `wins`            | Number    |
| Draws           | `draws`           | Number    |
| Losses          | `losses`          | Number    |
| Goals For       | `goals_for`       | Number    |
| Goals Against   | `goals_against`   | Number    |
| Goal Difference | `goal_difference` | Number    |
| Points          | `points`          | Number    |
| XG For          | `xg_for`          | Number    |
| XG Against      | `xg_against`      | Number    |


**Fan360 Live Events** — `Fan360LiveEvents__dlm`, category **Engagement**, primary key `event_id`, event time `received_at`:


| Label         | API name        | Type      |
| ------------- | --------------- | --------- |
| Event Id      | `event_id`      | Text (PK) |
| Source        | `source`        | Text      |
| Mode          | `mode`          | Text      |
| Match Id      | `match_id`      | Text      |
| Fixture Label | `fixture_label` | Text      |
| Minute        | `minute`        | Number    |
| Second        | `second`        | Number    |
| Period        | `period`        | Number    |
| Event Type    | `event_type`    | Text      |
| Team          | `team`          | Text      |
| Player        | `player`        | Text      |
| Detail        | `detail`        | Text      |
| Received At   | `received_at`   | DateTime  |


### 4c. Stream → DMO mapping matrix


| Stream                   | Target DMO               | What to map                                                       |
| ------------------------ | ------------------------ | ----------------------------------------------------------------- |
| `PlayerVsOpponent`       | `Fan360Player`           | `player__c` → Source Player Name (and PK / name fields)           |
| `PlayerVsOpponent`       | `Fan360PlayerVsOpponent` | All eight business columns (`season_id__c` … `matches_played__c`) |
| `PlayerVsOpponent`       | `Fan360Team`             | `opponent__c` → Source Team Name (+ PK)                           |
| `TeamSeasonStats`        | `Fan360Team`             | `team__c` → Source Team Name (+ PK)                               |
| `TeamSeasonStats`        | `Fan360TeamSeasonStats`  | All mart columns                                                  |
| `HeadToHead`             | `Fan360Team`             | `team_a__c` → Source Team Name (+ PK)                             |
| `Match`                  | `Fan360Team`             | `home_team__c` → Source Team Name (+ PK)                          |
| `Live Events` (BigQuery) | `Fan360LiveEvents`       | All thirteen fields                                               |


Map each DLO primary key column to the DMO primary key field before saving.

---

## Step 5. Calculated Insights

**Data Cloud** → **Calculated Insights** → **New** → **SQL**. Data space `**default`**.

For each insight below:

1. Add every source DMO listed as a **dependency** before entering SQL.
2. Qualify every column as `TableName__dlm.field__c`.
3. Use `GROUP BY` for dimensions and `SUM()` / `COUNT()` for measures.
4. On the schedule step: set start time, leave **end date** empty, click **Enable**.

Repo copies: `[PlayerVsOpponent.calculatedInsight-meta.xml](../../force-app/main/default/calculatedInsights/PlayerVsOpponent.calculatedInsight-meta.xml)`, `[TopScorerBySeason.calculatedInsight-meta.xml](../../force-app/main/default/calculatedInsights/TopScorerBySeason.calculatedInsight-meta.xml)` (team leaderboard), `[LiveMatchSnapshot.calculatedInsight-meta.xml](../../force-app/main/default/calculatedInsights/LiveMatchSnapshot.calculatedInsight-meta.xml)`.

### 5a. Player vs Opponent (`PlayerVsOpponent__cio`)

**Dependencies:** `Fan360PlayerVsOpponent__dlm`, `Fan360Player__dlm`, `Fan360Team__dlm`.

**Schedule:** Every 24 Hours.

```sql
SELECT
    Fan360Player__dlm.unified_player_id__c AS unified_player_id__c,
    Fan360Player__dlm.player_name__c AS player_name__c,
    Fan360Team__dlm.canonical_team_id__c AS opponent_id__c,
    Fan360Team__dlm.team_name__c AS opponent_name__c,
    SUM(Fan360PlayerVsOpponent__dlm.goals__c) AS goals__c,
    SUM(Fan360PlayerVsOpponent__dlm.xg_total__c) AS xg_total__c,
    SUM(Fan360PlayerVsOpponent__dlm.shots__c) AS shots__c,
    SUM(Fan360PlayerVsOpponent__dlm.matches_played__c) AS matches_played__c
FROM Fan360PlayerVsOpponent__dlm
JOIN Fan360Player__dlm
  ON Fan360Player__dlm.source_player_name__c = Fan360PlayerVsOpponent__dlm.player__c
JOIN Fan360Team__dlm
  ON Fan360Team__dlm.source_team_name__c = Fan360PlayerVsOpponent__dlm.opponent__c
GROUP BY unified_player_id__c, player_name__c, opponent_id__c, opponent_name__c
```

### 5b. Top Teams By Season (`TopScorerBySeason__cio` in metadata)

Team leaderboard from `team_season_stats` (not player goal scorers).

**Dependencies:** `Fan360TeamSeasonStats__dlm`, `Fan360Team__dlm`.

**Schedule:** Every 24 Hours.

```sql
SELECT
    Fan360TeamSeasonStats__dlm.season__c AS season__c,
    Fan360Team__dlm.canonical_team_id__c AS canonical_team_id__c,
    Fan360Team__dlm.team_name__c AS team_name__c,
    SUM(Fan360TeamSeasonStats__dlm.goals_for__c) AS goals_for__c,
    SUM(Fan360TeamSeasonStats__dlm.xg_for__c) AS xg_for__c,
    SUM(Fan360TeamSeasonStats__dlm.points__c) AS points__c
FROM Fan360TeamSeasonStats__dlm
JOIN Fan360Team__dlm
  ON Fan360Team__dlm.source_team_name__c = Fan360TeamSeasonStats__dlm.team__c
GROUP BY season__c, canonical_team_id__c, team_name__c
```

Example query after publish:

```sql
SELECT team_name__c, goals_for__c, points__c
FROM TopScorerBySeason__cio
WHERE season__c = '2024/25'
ORDER BY goals_for__c DESC
LIMIT 20;
```

### 5c. Live Match Snapshot (`LiveMatchSnapshot__cio`)

Batch Calculated Insight over `Fan360LiveEvents__dlm`.

**Dependencies:** `Fan360LiveEvents__dlm`.

**Schedule:** Every 1 Hour (minimum interval in Developer Edition).

```sql
SELECT
    Fan360LiveEvents__dlm.match_id__c AS match_id__c,
    Fan360LiveEvents__dlm.fixture_label__c AS fixture_label__c,
    COUNT(*) AS events__c,
    SUM(CASE WHEN Fan360LiveEvents__dlm.event_type__c = 'Shot' THEN 1 ELSE 0 END) AS shots__c,
    SUM(CASE WHEN Fan360LiveEvents__dlm.event_type__c = 'Goal' THEN 1 ELSE 0 END) AS goals__c,
    SUM(CASE WHEN Fan360LiveEvents__dlm.event_type__c = 'Yellow Card' THEN 1 ELSE 0 END) AS yellow_cards__c,
    MAX(Fan360LiveEvents__dlm.received_at__c) AS last_event_at__c
FROM Fan360LiveEvents__dlm
GROUP BY match_id__c, fixture_label__c
```

Live freshness for the agent comes from the Ingestion API (Step 6) writing to `Fan360LiveEvents__dlm`; this CIO refreshes on the hourly schedule.

---

## Step 6. Ingestion API and Cloud Run

### 6a. JWT certificate

From repo root (Windows with Git for Windows):

```powershell
New-Item -ItemType Directory -Force -Path .secrets | Out-Null

& "C:\Program Files\Git\usr\bin\openssl.exe" req -x509 -nodes -newkey rsa:2048 `
    -keyout .secrets/sf-ingest-private.key `
    -out .secrets/sf-ingest-cert.pem `
    -days 3650 `
    -subj "/CN=fan360-labs ingest"
```

Linux / macOS:

```bash
mkdir -p .secrets
openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout .secrets/sf-ingest-private.key \
    -out .secrets/sf-ingest-cert.pem \
    -days 3650 \
    -subj "/CN=fan360-labs ingest"
```

### 6b. External Client App

**Setup** → **App Manager** → **New External Client App**.

**Basic Information**


| Field                    | Value                  |
| ------------------------ | ---------------------- |
| External Client App Name | `Ingestion Api Client` |
| API Name                 | `IngestionApiClient`   |
| Contact Email            | Your email             |
| Distribution State       | Local                  |


**API (Enable OAuth Settings)**


| Setting                | Value                                          |
| ---------------------- | ---------------------------------------------- |
| Enable OAuth           | Yes                                            |
| Callback URL           | `https://login.salesforce.com/oauth2/callback` |
| Enable JWT Bearer Flow | Yes                                            |
| Upload certificate     | `.secrets/sf-ingest-cert.pem`                  |


**OAuth scopes** (move to Selected):


| UI label                             | API name                          |
| ------------------------------------ | --------------------------------- |
| Manage Data Cloud Ingestion API data | `cdp_ingest_api`                  |
| Manage user data via APIs            | `api`                             |
| Perform requests at any time         | `refresh_token`, `offline_access` |


**Save** → copy **Consumer Key**.

`**.env` (local)**

```env
SF_INGEST_CLIENT_ID=<Consumer Key>
SF_INGEST_USERNAME=<Salesforce Username column from Setup → Users>
SF_INGEST_PRIVATE_KEY_PATH=.secrets/sf-ingest-private.key
```

Use your admin username.

**Policies.** **External Client App Manager** → your app → **Policies** → permit the integration user.

### 6c. Ingestion API connector and stream

1. **Data Cloud** → **Ingestion API** → **New** → **Connect an Ingestion API Source**.
2. **Connector Name:** `LiveEvents` → **Save**.
3. Upload `[docs/openapi/live-events-ingestion.json](../openapi/live-events-ingestion.json)`.
4. **Data Streams** → **New** → **Ingestion API** → select connector **LiveEvents**.
5. Object **LiveEvent**:
  - Category: **Engagement**
  - Primary key: `event_id`
  - Event time: `received_at`
  - Map all thirteen fields (Text / Number / DateTime as in §4b).
6. **Map to Data Model** → `**Fan360LiveEvents__dlm`** → deploy.

Cloud Run posts to `/api/v1/ingest/sources/LiveEvents/LiveEvents` (source name `LiveEvents`, object `LiveEvents`).

### 6d. GCP Secret Manager and redeploy

Create secrets once (repo root):

```powershell
gcloud config set project sf-fan360

gcloud secrets create sf-ingest-client-id --replication-policy=automatic 2>$null
$cid = (Get-Content .env | Where-Object { $_ -match '^SF_INGEST_CLIENT_ID=(.+)$' }) -replace '^SF_INGEST_CLIENT_ID=',''
Set-Content -Path $env:TEMP\sf-ingest-client-id.txt -Value $cid.Trim() -NoNewline
gcloud secrets versions add sf-ingest-client-id --data-file=$env:TEMP\sf-ingest-client-id.txt

gcloud secrets create sf-ingest-private-key --replication-policy=automatic 2>$null
gcloud secrets versions add sf-ingest-private-key --data-file=.secrets/sf-ingest-private.key

gcloud secrets create sf-ingest-username --replication-policy=automatic 2>$null
$user = (Get-Content .env | Where-Object { $_ -match '^SF_INGEST_USERNAME=(.+)$' }) -replace '^SF_INGEST_USERNAME=',''
Set-Content -Path $env:TEMP\sf-ingest-username.txt -Value $user.Trim() -NoNewline
gcloud secrets versions add sf-ingest-username --data-file=$env:TEMP\sf-ingest-username.txt
```

Grant the Cloud Run service account access to the secrets:

```powershell
$SA = "live-ingest@sf-fan360.iam.gserviceaccount.com"
foreach ($s in @("sf-ingest-client-id","sf-ingest-private-key","sf-ingest-username")) {
  gcloud secrets add-iam-policy-binding $s `
    --project=sf-fan360 `
    --member="serviceAccount:$SA" `
    --role="roles/secretmanager.secretAccessor"
}
```

Build and deploy (`[cloud-run/live-ingest/cloudbuild.yaml](../../cloud-run/live-ingest/cloudbuild.yaml)`):

```powershell
$INGEST_URL = "https://<your-my-domain>.my.salesforce.com"   # no trailing slash

gcloud builds submit cloud-run/live-ingest `
  --config cloud-run/live-ingest/cloudbuild.yaml `
  --substitutions "_SF_INGEST_URL=$INGEST_URL"
```

Defaults in `cloudbuild.yaml`: region and Artifact Registry `**europe-central2**`, service account `**live-ingest**`, image tag `**$BUILD_ID**`.

Confirm deployment:

```powershell
gcloud run services describe live-ingest `
  --region europe-central2 `
  --format="value(status.url)"
```

After FPL polling runs, Cloud Run logs should include `data-cloud: published N events`.

---

## Exit gate

**Open Query Editor.** **Data Cloud** app → **Data Explorer** → **Query** tab. Data space `**default`**.

**Historical CI (when mart has rows):**

```sql
SELECT player_name__c, opponent_name__c, SUM(goals__c) AS g
FROM PlayerVsOpponent__cio
WHERE opponent_name__c = 'Manchester United'
GROUP BY 1, 2
ORDER BY g DESC
LIMIT 10;
```

**Live ingest:**

```sql
SELECT COUNT(*) FROM Fan360LiveEvents__dlm;
```

Proceed to [phase4-vector-rag.md](phase4-vector-rag.md).

---

## Local secrets reference (`.secrets/`, gitignored)


| File                                | Purpose                                                    |
| ----------------------------------- | ---------------------------------------------------------- |
| `sf-fan360-datacloud-wif-oidc.json` | Backup of GCP OIDC config for BigQuery federation (Step 2) |
| `sf-ingest-private.key`             | JWT signing key for Ingestion API (Step 6)                 |
| `sf-ingest-cert.pem`                | Certificate uploaded to External Client App (Step 6)       |
| `etl-service.json`                  | ETL service account (Phase 0)                              |


