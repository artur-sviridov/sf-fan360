# Phase 7 - Public Experience Cloud second-screen site

**Goal.** A public, branded Experience Cloud site at a stable URL with the
`secondScreenChat` LWC rendering the live score strip, agent chat, and
trending prompts. Guest users can ask any of the three reference queries
without logging in.

**Time budget.** ~2 hours.

**Prerequisites.** Phase 6 exit gate.

---

## Step 1. Deploy the LWC + Apex controller + Platform Event

```powershell
sf project deploy start -o s7dev `
    -d force-app/main/default/lwc/secondScreenChat `
    -d force-app/main/default/classes/SecondScreenChatController.cls `
    -d force-app/main/default/classes/SecondScreenChatControllerTest.cls `
    -d force-app/main/default/objects/LiveMatchEvent__e

sf apex run test -o s7dev `
    -n SecondScreenChatControllerTest `
    -r human -w 10
```

All four assertions must pass.

---

## Step 2. Create the Experience Cloud site

> SF: Setup -> Digital Experiences -> All Sites -> New.

- Template: LWR (Build Your Own).
- Name: `Second Screen`.
- URL suffix: `secondscreen`.

Wait for the site to provision (~2 min). Open the Experience Builder.

In the Builder:

1. Drag the `secondScreenChat` LWC onto the home page (it appears under
   "Components" because the `<targets>` in
   [`secondScreenChat.js-meta.xml`](../../force-app/main/default/lwc/secondScreenChat/secondScreenChat.js-meta.xml)
   include `lightningCommunity__Default`).
2. Set the `favoriteTeam` property to your default (optional).
3. Publish the site.

**EVIDENCE.** Screenshot the rendered second-screen page ->
`docs/trust-layer-evidence/07-experience-cloud.png`.

---

## Step 3. Enable Guest User access

> SF: Setup -> Digital Experiences -> All Sites -> Second Screen ->
> Workspaces -> Administration -> Login & Registration.

1. Allow guest user access (check the box).
2. Public link: copy the URL (e.g. `https://<domain>.my.site.com/secondscreen`).
3. Set the guest user profile to a custom profile (`Second Screen Guest`)
   if you want fine-grained control. Default is fine for the demo.

Open the URL in an Incognito window:

- Verify the page loads without login.
- Verify the trending prompts render.
- Click one; verify the chat exchanges a question + answer.

---

## Step 4. Wire the Platform Event publisher

The Cloud Run `live-ingest` service publishes
`LiveMatchEvent__e` whenever a goal/card/sub event arrives. Add a
publisher call to the FPL / API-Football webhook handlers after each successful
BigQuery write:

```python
# Pseudo-snippet to add to live-ingest:
from app.platform_event_sink import publish_platform_event
for ev in batch:
    publish_platform_event(ev)
```

The `platform_event_sink.py` module uses the same Data Cloud Ingestion
API connected app's access token to call
`/services/data/v60.0/sobjects/LiveMatchEvent__e/`.

Implementation in [`cloud-run/live-ingest/app/data_cloud_sink.py`](../../cloud-run/live-ingest/app/data_cloud_sink.py)
covers the JWT-bearer auth flow; extend it to call the Platform Event
endpoint when you reach this step.

Verify in Incognito:

- Trigger an FPL poll (`POST /webhook/fpl` with `{"gw": N}`) during a match window.
- The score strip updates within 5 seconds.

---

## Step 5. Firestore session state (optional but in plan)

> GCP: Firestore -> Create Database -> Native mode, region `eur3`.

Create a single collection `sessions` with documents keyed by a UUID
cookie that the LWC sets on first visit:

```
sessions/{uuid}
    favorite_team: string
    last_3_questions: array<string>
    updated_at: timestamp
```

Wire reads/writes via an External Service (re-use the same
`Cloud_Run_Shim` Named Credential pattern - add a `/session/{uuid}`
endpoint on the shim or a dedicated thin service).

If short on time, skip this step - the agent variables already cover the
basics. Note the skip in your local ADLC journal if you use one.

---

## EXIT GATE

- Public URL serves the page in Incognito without login.
- All three reference queries return cited answers in <3 seconds.
- Live score strip updates when live events arrive from FPL polling.

Proceed to [phase8-portfolio.md](phase8-portfolio.md).
