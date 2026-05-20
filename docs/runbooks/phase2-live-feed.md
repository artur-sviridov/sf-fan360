# Phase 2 - Live event feed

**Goal.** End this phase with a Cloud Run service `live-ingest` deployed, streaming live FPL events into BigQuery during real matchdays.

**Time budget.** ~2 hours.

**Prerequisites.**

- Phase 1 exit gate holds.
- You have decided to enable GCP billing now. This is the only forced billing point in the build (Cloud Run, GCS, Scheduler need an attached billing account even on free tier).

---

## Step 1. Enable billing and the budget kill-switch (one-time, blocking)

> GCP: Billing -> Link a billing account.

1. Add a payment method. Google enrolls the account in the 90-day / $300 Free Trial automatically. Note the trial expiry date - put it in your calendar.
2. Apply your budget kill-switch (local checklist): set budget **$5/month**, deploy the Pub/Sub-triggered Cloud Function that disables billing at 100%, send a test event into the topic, confirm billing flips off, then re-enable billing after the test.
3. Re-enable billing after the test.

**Verify** billing is on:

```powershell
gcloud beta billing projects describe sf-fan360
# Look for billingEnabled: true
```

---

## Step 2. Enable billing-required APIs and switch ETL to GCS mode

```powershell
.\scripts\gcp-setup.ps1 -ProjectId sf-fan360 -EnableBilling
```

This enables Cloud Run, Firestore, Cloud Scheduler, Pub/Sub, Vertex AI APIs (Vertex needed for Phase 6).

Now flip the ETL to GCS mode:

```
ETL_LOCAL_ONLY=0
```

Re-run the ETL to push Parquet to GCS:

```powershell
# Create the raw bucket first (idempotent).
gcloud storage buckets create gs://sf-fan360-raw `
    --location=EU --uniform-bucket-level-access

python -m etl.run_full
```

The orchestrator now creates BigQuery external tables over the GCS folders instead of native loads. The marts SQL re-runs without changes.

---

## Step 3. Build and deploy `live-ingest`

### 3a. Create the Artifact Registry repo (one-time)

```powershell
gcloud artifacts repositories create live-ingest `
    --repository-format=docker `
    --location=europe-west1 `
    --description="sf-fan360 live-ingest images"
```

### 3b. Store API keys in Secret Manager

```powershell
gcloud secrets create football-data-key --replication-policy=automatic
gcloud secrets versions add football-data-key --data-file=- <<< "$env:FOOTBALL_DATA_API_KEY"

gcloud secrets create api-football-key --replication-policy=automatic
gcloud secrets versions add api-football-key --data-file=- <<< "$env:API_FOOTBALL_KEY"
```

(PowerShell here-string syntax differs from bash; consult Microsoft docs if the above does not parse on your shell.)

### 3c. Submit the Cloud Build pipeline

```powershell
gcloud builds submit cloud-run/live-ingest `
    --config cloud-run/live-ingest/cloudbuild.yaml
```

Wait ~3 minutes. The build pipeline:

1. Builds the Docker image.
2. Pushes to Artifact Registry.
3. Deploys to Cloud Run as the `live-ingest` service in `europe-central2`.

**Validate** the service is up:

```powershell
$URL = gcloud run services describe live-ingest `
    --region europe-central2 --format='value(status.url)'

# Health check.
gcloud auth print-identity-token | `
    Invoke-RestMethod -Uri "$URL/health" -Method GET -Headers @{ Authorization = "Bearer $((gcloud auth print-identity-token))" }
```

The response must be `{"status":"ok","version":"0.1.0"}`.

---

## Step 4. Cloud Scheduler jobs for live polling

> GCP: Cloud Scheduler -> Create job.

Create a job for the next upcoming gameweek's match window:

- Name: `fpl-poll-gw-XX` (one per gameweek you want covered).
- Frequency: `*/1 * * * *` (every minute).
- Region: `europe-central2`.
- Target: HTTP.
- URL: `$URL/webhook/fpl`.
- HTTP method: POST.
- Body: `{"gw": XX}`.
- Auth header: OIDC token, service account `s7-live-ingest@...`.
- Time zone: `Europe/London`.

Pause it outside the match window. Free tier covers 3 jobs total; create one per gameweek and pause when done.

Calendar of upcoming fixtures comes from the service itself:

```powershell
Invoke-RestMethod -Uri "$URL/fixtures/upcoming" -Method GET `
  -Headers @{ Authorization = "Bearer $((gcloud auth print-identity-token))" }
```

---

## EXIT GATE

- `gcloud beta billing projects describe sf-fan360` shows `billingEnabled: true`, and the budget kill-switch Pub/Sub test passed (re-enable billing afterward).
- `live-ingest` Cloud Run service is deployed and `/health` returns 200.
- At least one Cloud Scheduler job exists targeting `/webhook/fpl`.
- During a match window, `SELECT COUNT(*) FROM sf_fan360_raw.live_events` grows after FPL polls run.

Proceed to [phase3-zero-copy-setup.md](phase3-zero-copy-setup.md).