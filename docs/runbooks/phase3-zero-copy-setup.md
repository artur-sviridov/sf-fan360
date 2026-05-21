# Phase 3 - Data Cloud Zero Copy + Ingestion API

**Goal.** Surface every BigQuery `sf_fan360_marts` table as a Data Cloud DMO via Zero Copy federation, plus wire a streaming Ingestion API path for the live events table. End-state: the agent can query every OpenFootball EPL season loaded in Phase 1 (2010/11 onward) without copying a byte into Salesforce storage.

**Time budget.** ~4 hours. Step 2 (OIDC handshake) is the single hardest hour of the entire build; the rest is mechanical.

**Prerequisites.** Phase 2 exit gate holds. Cloud Scheduler jobs for live polling are configured.

---

## Step 1. Confirm Data Cloud is provisioned

> SF: Setup -> Quick Find "Data Cloud Setup" -> verify status = Provisioned.

If "Provisioning", wait. New DE orgs can take up to 24 h.

Open the Data Cloud app from the app launcher. You should land on the Data Cloud Home tab with at least one Data Space (default `default`).

---

## Step 2. OIDC Workload Identity Federation handshake (GCP side)

Salesforce Data Cloud authenticates to GCP with **Identity Provider Based** auth: short-lived OIDC tokens from   
`{My Domain}/services/connectors`. No service-account JSON keys in Salesforce.

Official reference: [Set Up a Google BigQuery Data Federation Connection](https://developer.salesforce.com/docs/data/data-cloud-int/guide/c360-a-set-up-bigquery-connection.html).

### 2a. Collect Salesforce values (before GCP is finished)

> SF: Setup -> Quick Find **My Domain** -> copy the **My Domain URL** (no trailing slash).

Example: `https://<org>-dev-ed.develop.my.salesforce.com`

Keep two derived values:


| Purpose                         | Value                                  |
| ------------------------------- | -------------------------------------- |
| GCP **issuer** (`--issuer-uri`) | `{My Domain}/services/connectors`      |
| GCP **allowed audience**        | My Domain URL only (root URL, no path) |


> SF: Setup -> Quick Find **Data Cloud Setup** -> **Configuration** -> **More Connectors** -> **New** -> **Google BigQuery** -> **Next**.

On **New Google Big Query Source**:

- Authentication: **Identity Provider Based**
- Enter **Connection Name** (e.g. `Fan360 BigQuery Federation`) and **Connection API Name**
- Copy **External ID** (e.g. `appID1809C7E-D33E696`) — you will bind this as the **subject** principal in GCP

Leave **OIDC Client Config**, **Service Account Email**, and **Project ID** empty until §2c–2d. Do not save yet.

### 2b. Create the Workload Identity Pool in GCP

Project: `sf-fan360` (or your `GCP_PROJECT_ID` from `.env`).

```powershell
gcloud config set project sf-fan360

gcloud iam workload-identity-pools create salesforce-pool `
    --location=global `
    --display-name="Salesforce Data Cloud Pool"

# OIDC provider that trusts the My Domain issuer.
gcloud iam workload-identity-pools providers create-oidc salesforce-provider `
    --location=global `
    --workload-identity-pool=salesforce-pool `
    --display-name="Salesforce OIDC" `
    --issuer-uri="https://<org>-dev-ed.develop.my.salesforce.com/services/connectors" `
    --allowed-audiences="https://<org>-dev-ed.develop.my.salesforce.com" `
    --attribute-mapping="google.subject=assertion.sub,attribute.aud=assertion.aud"
```

Console equivalent: **IAM & Admin -> Workload Identity Federation** -> pool **salesforce-pool** -> **Add provider** -> Issuer = `{My Domain}/services/connectors`, Allowed audience = My Domain URL, attribute mappings as above.

### 2c. Create the BigQuery read-only service account + impersonation grants

Use a **dedicated** reader SA (not `etl-service@...`, which owns ETL writes).

```powershell
gcloud iam service-accounts create sf-fan360-datacloud `
    --display-name="Fan 360 Data Cloud Reader"

$SA = "sf-fan360-datacloud@sf-fan360.iam.gserviceaccount.com"

# Roles required by Salesforce for federation (project-level).
foreach ($role in @(
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
    "roles/bigquery.metadataViewer",
    "roles/bigquery.readSessionUser"
)) {
    gcloud projects add-iam-policy-binding sf-fan360 `
        --member="serviceAccount:$SA" `
        --role=$role
}

$PROJECT_NUMBER = gcloud projects describe sf-fan360 --format="value(projectNumber)"
$POOL = "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/salesforce-pool"
$MY_DOMAIN = "https://<org>-dev-ed.develop.my.salesforce.com"
$EXTERNAL_ID = "appID1809C7E-D33E696"   # from Salesforce External ID field in §2a

# Audience grant: principal = My Domain URL (URL-encode https:// as https%3A%2F%2F in the member string).
$AUDIENCE_ENC = [uri]::EscapeDataString($MY_DOMAIN)
gcloud iam service-accounts add-iam-policy-binding $SA `
    --role="roles/iam.workloadIdentityUser" `
    --member="principalSet://iam.googleapis.com/${POOL}/attribute.aud/${AUDIENCE_ENC}"

# Subject grant: use principal://
$SUBJECT_ENC = [uri]::EscapeDataString($EXTERNAL_ID)
gcloud iam service-accounts add-iam-policy-binding $SA `
    --role="roles/iam.workloadIdentityUser" `
    --member="principal://iam.googleapis.com/${POOL}/subject/${SUBJECT_ENC}"
```

Console equivalent (matches Salesforce doc): on provider **salesforce-provider** -> **Grant access** -> **Grant access using service account impersonation** twice — (1) attribute **aud** = My Domain URL, (2) attribute **subject** = External ID from §2a.

#### Download the OIDC client config JSON (for Salesforce **OIDC Client Config**)

1. Open [Workload Identity Pools](https://console.cloud.google.com/iam-admin/workload-identity-pools?project=sf-fan360) for project **sf-fan360**.
2. Click pool **salesforce-pool** (not the provider row underneath).
3. Click **Grant access** (top of the pool detail page).
4. Choose **Grant access using federated identities (Recommended)** .
5. In **Configure your application**:
   - **Provider**: `salesforce-provider`
   - **OIDC token path**: any placeholder path, e.g. `/var/run/secrets/salesforce/token` — Salesforce never reads this file; GCP requires a value to enable download.
   - **Format type**: leave default (**JSON** / credential configuration).
6. Click **Download configuration**. Save the file (e.g. `salesforce-wif-config.json` on your machine).
7. Open the file in a text editor. It should look roughly like:

```json
{
  "universe_domain": "googleapis.com",
  "type": "external_account",
  "audience": "//iam.googleapis.com/projects/1076649643321/locations/global/workloadIdentityPools/salesforce-pool/providers/salesforce-provider",
  "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
  "token_url": "https://sts.googleapis.com/v1/token",
  "credential_source": { ... }
}
```

8. Select **all** JSON (Ctrl+A) and copy. You will paste it into Salesforce in §2d.

### 2d. Finish the connection in Salesforce

> SF: return to the **New Google Big Query Source** screen from §2a.


| Field                       | Value                                                         |
| --------------------------- | ------------------------------------------------------------- |
| **Service Account Email**   | `sf-fan360-datacloud@sf-fan360.iam.gserviceaccount.com`       |
| **OIDC Client Config**      | Paste the **entire** JSON from §2c step 7–8 (multi-line; not a file upload on this screen) |
| **Project ID**              | `sf-fan360`                                                   |
| **Use Unload**              | Inactive (Phase 3 portfolio; no GCS bucket required)          |
| **Enable Large Result Set** | Unchecked unless you add `sf_temp_dataset` per Salesforce doc |


Click **Test Connection**, then **Save**.

Common failure modes:

- **401 unauthorized**: `--allowed-audiences` must be My Domain root only (not `/services/connectors`, no trailing slash).
- **403 forbidden**: missing `workloadIdentityUser` on the SA for **both** audience (My Domain) and subject (External ID); or missing BigQuery roles.
- **issuer URL mismatch**: `--issuer-uri` must include `/services/connectors`; do not use My Domain alone.

**EVIDENCE.** Screenshot the green "Connected" state -> `docs/trust-layer-evidence/03-zero-copy-connected.png`.

---

## Step 3. Create Data Streams + DLOs

> SF: Data Cloud -> Data Streams -> New -> BigQuery (Federation).

Create one Data Stream per mart table:


| BigQuery source                                          | Data Stream name         | Target DLO              |
| -------------------------------------------------------- | ------------------------ | ----------------------- |
| `sf_fan360_marts.match`                                  | `MatchStream`            | `Match__dll`            |
| `sf_fan360_marts.team_season_stats`                      | `TeamSeasonStream`       | `TeamSeasonStats__dll`  |
| `sf_fan360_marts.head_to_head`                           | `HeadToHeadStream`       | `HeadToHead__dll`       |
| `sf_fan360_marts.player_vs_opponent` (empty placeholder) | `PlayerVsOpponentStream` | `PlayerVsOpponent__dll` |
| `sf_fan360_raw.live_events`                              | `LiveEventsStream`       | `LiveEvents__dlm`       |


For each:

1. Select the BigQuery table.
2. Set Refresh Mode = "Full Refresh" weekly (free tier).
3. Map columns to the DLO. Accept default types except:
  - `season` column = Text(10).
  - `match_date` = Date.
  - All `_xg` columns = Number(10,4).

The deployable metadata for these objects lives at:

- `force-app/main/default/mlDataLakeObjects/` (manually adjusted after the wizard runs - the wizard creates the DLOs in the org; SFDX retrieve pulls the metadata into source control).

After running the wizard, retrieve into source:

```powershell
sf project retrieve start -o s7dev `
    -m "MktDataLakeObject:Match__dll,MktDataLakeObject:PlayerSeasonStats__dll,..."
```

---

## Step 4. Create unified DMOs and Identity Resolution

> SF: Data Cloud -> Data Model -> New DMO.

Create:

- `UnifiedPlayer__dlm` keyed on `(name_normalized, dob)`.
- `UnifiedTeam__dlm` keyed on `canonical_team_id` (sourced from the team-mapping CSV).

Upload `data/team_mapping.csv` (see `[docs/team-mapping.csv](../team-mapping.csv)` for the seed file). Maps every team-name variant to one canonical id.

> SF: Data Cloud -> Identity Resolution -> New Ruleset.

Ruleset for players:

- Source: `PlayerSeasonStats__dll`, `PlayerVsOpponent__dll`, `MatchEvent__dlm`.
- Match rule: exact-match on normalized name.
- Reconciliation: most-recent-source-wins.

Ruleset for teams: exact-match on canonical id from the mapping table.

Save and run the ruleset. Wait ~5 minutes for first execution.

**EVIDENCE.** Screenshot the IDR run results -> `docs/trust-layer-evidence/03-identity-resolution.png`.

---

## Step 5. Calculated Insights

> SF: Data Cloud -> Calculated Insights -> New.

Build three CIs. The SQL is in `[force-app/main/default/calculatedInsights/](../../force-app/main/default/calculatedInsights/)`.

### 5a. `PlayerVsOpponent__cio`

Sources `PlayerVsOpponent__dll`. Aggregates goals, assists, xg per `(unified_player_id, opponent_canonical_id)` across all seasons. **This is the engine for the reference query.**

### 5b. `TopScorerBySeason__cio`

Sources `PlayerSeasonStats__dll`. Returns the top 50 scorers per season, keyed on season + rank.

### 5c. `LiveMatchSnapshot__cio`

Sources the `LiveEvents__dlm` (from Step 6). Tumbling 60-second window showing current xG, possession, shots-on-target per match.

Schedule each CI:

- `PlayerVsOpponent__cio`: daily (data only changes on ETL refresh).
- `TopScorerBySeason__cio`: daily.
- `LiveMatchSnapshot__cio`: every 5 minutes during a configured match window.

---

## Step 6. Streaming Ingestion API for live events

> SF: Setup -> App Manager -> New Connected App.

- Name: `IngestionApiClient`.
- API Name: `IngestionApiClient`.
- Contact email: yours.
- Enable OAuth Settings: yes.
- Callback URL: `https://login.salesforce.com/oauth2/callback` (placeholder).
- Selected OAuth Scopes: `cdp_ingest_api`, `api`, `refresh_token,offline_access`.
- Use digital signatures: **yes**. Upload `cert.pem` generated below.

Generate the keypair (one-time):

```powershell
openssl req -x509 -nodes -newkey rsa:2048 `
    -keyout .secrets/sf-ingest-private.key `
    -out .secrets/sf-ingest-cert.pem `
    -days 3650 `
    -subj "/CN=fan360-labs ingest"
```

Upload `.secrets/sf-ingest-cert.pem` to the connected app.

After the app is created, note the **Consumer Key** -> set `SF_INGEST_CLIENT_ID` in `.env`.

> SF: Data Cloud -> Ingestion API -> New Source.

- Source name: `LiveEvents`.
- Schema: upload `[docs/openapi/live-events-ingestion.json](../openapi/live-events-ingestion.json)`.
- Object name: `LiveEvents__dll`.

> SF: Data Cloud -> Data Streams -> New -> Ingestion API.

Pick the `LiveEvents` source, accept the default mapping, deploy.

### 6b. Update Cloud Run live-ingest to double-publish

Add two new secrets to GCP Secret Manager:

```powershell
gcloud secrets create sf-ingest-client-id --replication-policy=automatic
gcloud secrets versions add sf-ingest-client-id --data-file=- <<< "$env:SF_INGEST_CLIENT_ID"

gcloud secrets create sf-ingest-private-key --replication-policy=automatic
gcloud secrets versions add sf-ingest-private-key --data-file=- < .secrets/sf-ingest-private.key
```

Redeploy `live-ingest` with the new env vars (see updated `[cloudbuild.yaml](../../cloud-run/live-ingest/cloudbuild.yaml)` - add the two secrets to `--set-secrets`).

The service's `data_cloud_sink.py` module handles JWT minting + ingestion.

---

## EXIT GATE

In Data Cloud Query Editor:

```sql
SELECT player_name__c, opponent_name__c, SUM(goals__c) g
FROM PlayerVsOpponent__cio
WHERE opponent_name__c = 'Manchester United'
GROUP BY 1, 2
ORDER BY g DESC
LIMIT 10;
```

returns the same answer as the BigQuery validation query from Phase 1.

Live events from FPL polling surface in `LiveEvents__dlm` within ~60 seconds of being written to BigQuery.

Proceed to [phase4-vector-rag.md](phase4-vector-rag.md).