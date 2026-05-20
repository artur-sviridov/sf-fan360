# Phase 0 - Account provisioning and local toolchain

**Goal.** End this phase with a Salesforce DE org connected via `sf` CLI, a GCP project ready (billing strategy chosen), API keys registered, and the local Python + SFDX + Node toolchains all working.

**Time budget.** ~4 hours, mostly waiting for verification emails.

**Prerequisites.** A Google account and an email address you can verify. Decide billing timing before you start (recommended: **no payment method until Phase 2** so the $300 trial clock starts later). Use these names consistently from day one: GCP project ID `sf-fan360`, BigQuery datasets `sf_fan360_raw` / `sf_fan360_marts`, GCS bucket `sf-fan360-raw`, Salesforce org alias `football_agent`.

---

## Step 1. Salesforce Developer Edition with Agentforce + Data Cloud

> SF: open [https://developer.salesforce.com/form/developer-signup/?d=pb&bc=HA](https://developer.salesforce.com/form/developer-signup/?d=pb&bc=HA).

1. Fill the form. Use a real email - the verification link expires quickly. Username must be globally unique across all Salesforce orgs forever; use  `<yourhandle>.fan360@<some-domain>.dev` or similar.
2. Check email, click verification link, set password, set security question.
3. Land in Setup. **Bookmark the My Domain URL.** It looks like `https://orgfarm-dfb05cd748-dev-ed.develop.lightning.force.com`. You will need it  for the OIDC handshake in Phase 3.

> SF: Setup -> Quick Find "Einstein Setup" -> enable everything: Einstein Generative AI, Agentforce, Einstein Trust Layer, Prompt Builder, Model Builder, Data Cloud.

Some of these toggles take 5-15 minutes to propagate. Refresh Setup until each one shows "Enabled".

> SF: Setup -> Quick Find "Data Cloud" -> follow the "Get Started" wizard. Accept defaults; do NOT skip the data space creation.

**EVIDENCE.** Screenshot the Einstein Setup page with all toggles green into `docs/trust-layer-evidence/00-setup-einstein.png`.

**EXIT GATE 1.** From a fresh PowerShell:

```powershell
sf org login web -a football_agent    # opens browser; log in with the DE creds
sf org display -o football_agent      # prints the org URL and id
```

`sf org display` must print without error.

---

## Step 2. Google Cloud account decision and project

Two pre-decisions you must have made:

- **Account choice.** Fresh Google account vs. personal account: fresh account preserves a clean $300 Vertex trial; personal account is fine if you set budget alerts, least-privilege IAM, and a billing kill-switch before Phase 2.
- **Billing timing.** Defer billing until Phase 2 (Cloud Run). Phase 1 fits inside the BigQuery Sandbox and runs without billing.

### 2a. Create the GCP project

> GCP: [https://console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate).

- Project ID: `sf-fan360`.
- Project Name (display): `sf-fan360`.
- Organization: No organization (personal account default).

### 2b. Enable APIs

> GCP: APIs & Services -> Library.

Enable each of these one at a time:

- BigQuery API
- Cloud Storage
- Cloud Build (required Billing account)
- Secret Manager (required Billing account)
- Compute Engine API (required Billing account)
- Generative Language API (this is Gemini AI Studio's GCP-side enrollment; the actual API key is issued separately at [https://aistudio.google.com](https://aistudio.google.com))

These will all succeed without billing because they are query-time-billed services with always-free quotas. The next batch (Cloud Run, Firestore) we defer to Phase 2.

### 2c. Install and authenticate gcloud locally

```powershell
# Windows: download installer from https://cloud.google.com/sdk/docs/install
# After install, restart PowerShell.
gcloud --version
gcloud auth login
gcloud config set project sf-fan360
gcloud config set compute/region europe-central2
```

### 2d. Create the ETL service account (no billing required)

```powershell
$SA = "etl-service@sf-fan360.iam.gserviceaccount.com"

gcloud iam service-accounts create etl-service `
    --display-name="ETL"

gcloud projects add-iam-policy-binding sf-fan360 `
    --member="serviceAccount:$SA" `
    --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding sf-fan360 `
    --member="serviceAccount:$SA" `
    --role="roles/bigquery.jobUser"

gcloud projects add-iam-policy-binding sf-fan360 `
    --member="serviceAccount:$SA" `
    --role="roles/storage.objectAdmin"

gcloud iam service-accounts keys create .secrets\etl-service.json `
    --iam-account=$SA
```

The JSON key is now at `.secrets/etl-service.json` and is git-ignored. **If you ever accidentally commit it, rotate immediately via **  
`gcloud iam service-accounts keys delete` **and create a fresh one.**

**EVIDENCE.** Screenshot the IAM page showing the service account with its three roles -> `docs/trust-layer-evidence/00-gcp-iam.png`.

---

## Step 3. API keys for data sources

### 3a. football-data.org

> Browser: [https://www.football-data.org/client/register](https://www.football-data.org/client/register).

Fill the registration form (email + name + intended use). The API key arrives in email within 1 minute. Add it to `.env`:

```
FOOTBALL_DATA_API_KEY=<your-key>
```

### 3b. Gemini AI Studio

> Browser: [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey).

Log in with the Google account that owns the GCP project. Click "Create API key", select the `fan360-labs-XX` project. Copy the key.

```
GEMINI_API_KEY=<your-key>
```

### 3c. API-Football (optional, only if you want live richer events)

> Browser: [https://dashboard.api-football.com/](https://dashboard.api-football.com/).

1. Create an account (or sign in).
2. Open **My Account** / **API** and copy your **API key** (not a RapidAPI key).
3. Confirm you are on the **Free** plan (typically 100 requests/day).

The service uses the direct api-sports endpoint:

- Base URL: `https://v3.football.api-sports.io`
- Auth header: `x-apisports-key: <your-key>`

```
API_FOOTBALL_KEY=<your-key>
```

Store the same value in GCP Secret Manager as `api-football-key` when you deploy `live-ingest` (Phase 2).

## Step 4. Local toolchain

The repo already contains an SFDX scaffold (the Agentforce DX template). We only add the Python side.

### 4a. Python venv

```powershell
# From the repo root.
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Verify:

```powershell
python -c "import understatapi, google.cloud.bigquery; print('ok')"
```

### 4b. Node + sf CLI (already present)

```powershell
node --version    # >= 22
sf --version      # >= 2.x
npm install       # installs Prettier and the Apex/XML plugins
```

### 4c. Configure environment

```powershell
Copy-Item .env.example .env
# Edit .env in your editor of choice. Fill in every variable from steps 2-3.
```

---

## Step 5. Smoke tests

```powershell
# Salesforce reachable
sf org display -o football_agent

# GCP reachable
gcloud config list
gcloud projects describe sf-fan360

# Python ETL package imports
python -c "from etl.config import settings; print(settings.gcp_project_id)"

# Gemini reachable (uses GEMINI_API_KEY from .env)
python -c "
import os, httpx
from dotenv import load_dotenv
load_dotenv()
r = httpx.get(
    'https://generativelanguage.googleapis.com/v1beta/models',
    params={'key': os.environ['GEMINI_API_KEY']},
    timeout=10,
)
print('Gemini status:', r.status_code, r.json().get('models', [{}])[0].get('name'))
"
```

All four commands must succeed.

---

## EXIT GATE

- `sf org display -o football_agent` returns the org URL.
- `gcloud config list` shows `project = sf-fan360`.
- `.secrets/etl-service.json` exists and is **not** tracked by git (`git check-ignore .secrets/etl-service.json` prints the path).
- `.env` contains real values for `FOOTBALL_DATA_API_KEY`, `GEMINI_API_KEY`, `GCP_PROJECT_ID`, `GCP_BQ_LOCATION`, `SF_ORG_ALIAS`.
- The four smoke tests above all pass.

When the gate holds, move to
[phase1-historical-etl.md](phase1-historical-etl.md).