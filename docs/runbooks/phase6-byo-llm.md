# Phase 6 - BYO LLM via Cloud Run shim (+ optional Vertex overlay)

**Goal.** Steady-state LLM path: Cloud Run shim fronting free Gemini AI
Studio, registered in Salesforce Model Builder as a Vertex AI BYO LLM. End
of phase has authentic Model Builder screenshots for both the shim and a
real Vertex endpoint.

**Time budget.** ~3 hours.

**Prerequisites.** Phase 5 exit gate. The shim Cloud Run service code is
already in `cloud-run/llm-shim/`.

---

## Step 1. Deploy the llm-shim service

### 1a. Create secrets

```powershell
$SECRET = & openssl rand -hex 32
gcloud secrets create llm-shim-shared-secret --replication-policy=automatic
gcloud secrets versions add llm-shim-shared-secret --data-file=- <<< $SECRET

gcloud secrets create gemini-api-key --replication-policy=automatic
gcloud secrets versions add gemini-api-key --data-file=- <<< $env:GEMINI_API_KEY

# Only if using pgvector fallback path (Phase 4):
gcloud secrets create pgvector-dsn --replication-policy=automatic
gcloud secrets versions add pgvector-dsn --data-file=- <<< $env:PGVECTOR_DSN
```

Save `$SECRET` value into `.env` as `LLM_SHIM_SHARED_SECRET` so local tests
can re-use it.

### 1b. Artifact Registry repo

```powershell
gcloud artifacts repositories create llm-shim `
    --repository-format=docker --location=europe-west1
```

### 1c. Build and deploy

```powershell
gcloud builds submit cloud-run/llm-shim `
    --config cloud-run/llm-shim/cloudbuild.yaml
```

Capture the deployed URL:

```powershell
$SHIM_URL = gcloud run services describe llm-shim `
    --region europe-west1 --format='value(status.url)'
Write-Host "SHIM URL: $SHIM_URL"
```

Smoke test:

```powershell
$auth = & gcloud auth print-identity-token
$headers = @{
    Authorization = "Bearer $auth"
    "X-Shim-Auth" = $SECRET
    "Content-Type" = "application/json"
}
$body = @{
    instances = @(
        @{
            contents = @(@{ role = "user"; parts = @(@{ text = "ping" }) })
            generationConfig = @{ temperature = 0.1; maxOutputTokens = 16 }
        }
    )
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Uri "$SHIM_URL/v1/projects/test/locations/us/publishers/google/models/gemini-2.5-flash:predict" `
    -Method POST -Headers $headers -Body $body
```

Response must be Vertex-shaped (`predictions` array) with a text candidate.

---

## Step 2. Wire the shim into Salesforce Model Builder

> SF: Setup -> Einstein -> Models -> Add Model -> Bring Your Own.

- Provider: Google Vertex AI.
- Endpoint URL: `$SHIM_URL/v1/projects/<any>/locations/<any>/publishers/google/models/gemini-2.5-flash:predict`.
- Named Credential: `Cloud_Run_Shim`.
- External Credential: `Cloud_Run_Shim_Credential` (the SharedSecret
  AuthParameter you populated already - see
  [`force-app/main/default/externalCredentials/`](../../force-app/main/default/externalCredentials)).

Use the Model Playground to send a test prompt. The response should be a
real Gemini answer, returning in ~1 second.

**EVIDENCE.** Screenshot the Playground response with the shim endpoint
visible in the URL bar -> `docs/trust-layer-evidence/06-model-builder-shim.png`.

> SF: Agent Builder -> Broadcast Metadata Agent -> Model Routing.

Pick:
- `tactical_context` topic -> the BYO LLM you just registered.
- Other topics -> standard Atlas-bundled model.

Save and republish.

---

## Step 3. Vertex overlay (one-time, 1-2 hours)

This step is what generates the "true BYO LLM" portfolio screenshots.
After capture, revert.

### 3a. Activate Vertex AI

> GCP: Vertex AI -> Get Started.

If you have not consumed the $300 trial yet, Google enrolls you now. Your budget kill-switch and $5/month cap (from Phase 2) are your safety net.

### 3b. Issue a Vertex endpoint for Gemini 2.5 Flash

```powershell
gcloud services enable aiplatform.googleapis.com

# Service account used by Salesforce -> Vertex (OIDC federation, no key).
gcloud iam service-accounts create s7-vertex `
    --display-name="Scenario 7 Vertex BYO LLM"
gcloud projects add-iam-policy-binding fan360-labs-XX `
    --member="serviceAccount:s7-vertex@fan360-labs-XX.iam.gserviceaccount.com" `
    --role="roles/aiplatform.user"
gcloud iam service-accounts add-iam-policy-binding `
    s7-vertex@fan360-labs-XX.iam.gserviceaccount.com `
    --role="roles/iam.workloadIdentityUser" `
    --member="principalSet://iam.googleapis.com/projects/$(gcloud config get-value project)/locations/global/workloadIdentityPools/salesforce-pool/*"
```

Reuse the workload identity pool from Phase 3.

### 3c. Update Model Builder to point at real Vertex

> SF: Setup -> Einstein -> Models -> Edit BYO LLM.

- Provider: Google Vertex AI.
- Endpoint: `https://europe-west1-aiplatform.googleapis.com/v1/projects/fan360-labs-XX/locations/europe-west1/publishers/google/models/gemini-2.5-flash:predict`.
- Authentication: OIDC federation to `s7-vertex` SA.

Test in Model Playground.

**EVIDENCE.** Screenshot showing the real Vertex URL in the Model Builder
detail page -> `docs/trust-layer-evidence/06-model-builder-vertex.png`.

Run the three reference queries through the agent. Record the demo here -
this is the version that goes in the Loom.

### 3d. Revert to shim

> SF: Setup -> Einstein -> Models -> Edit BYO LLM -> point endpoint URL
> back at `$SHIM_URL/...`.

Run the same three reference queries again. Confirm identical behaviour.

**EVIDENCE.** Screenshot showing the shim URL restored ->
`docs/trust-layer-evidence/06-model-builder-shim.png` (overwrite the earlier
shim screenshot if needed; both should be timestamped distinctly).

---

## Step 4. Trust Layer evidence capture

> SF: Setup -> Einstein Trust Layer -> Audit Trail.

Find the three reference-query requests from Step 3 and Step 4. For each:

- Confirm the prompt shows `[EMAIL]`, `[PHONE]`, etc. masks if the test
  utterance included PII. (If your utterances did not include any, run a
  fresh test like "My email is foo@bar.com - what was Salah's xG vs
  United?" - the mask should appear and the answer should still resolve.)
- Confirm the response did not leak the masked value back.

Archive into `docs/trust-layer-evidence/06-trust-layer-shim.png` and
`06-trust-layer-vertex.png`.

---

## EXIT GATE

- llm-shim is deployed; `/health` returns 200.
- Salesforce Model Builder has a BYO LLM card pointing at the shim, in
  steady state.
- Two evidence screenshots captured for both shim and Vertex modes.
- Trust Layer audit shows PII masking for at least one round-trip in each
  mode.
- Agent reference queries still pass after revert to shim.

Proceed to [phase7-experience-cloud.md](phase7-experience-cloud.md).
