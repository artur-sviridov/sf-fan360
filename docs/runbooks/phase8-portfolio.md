# Phase 8 - Portfolio packaging + brand surface

**Goal.** Public repo, 90-second Loom recorded and linked, three LinkedIn
posts shipped, one community-event CFP submitted.

**Time budget.** ~3 hours.

**Prerequisites.** Phase 7 exit gate.

---

## Step 1. Public GitHub repo

```powershell
# From the repo root.
git status
git add -A
git commit -m "Initial public push: scenario 7 second-screen agent"

# Replace with your real org/repo.
git remote add origin git@github.com:<yourhandle>/fan360-labs-second-screen.git
git push -u origin main
```

Verify in your browser:

- README renders the architecture diagram.
- `docs/runbooks/` is present.
- `.secrets/` contains only the `.gitkeep`.
- Run a fresh checkout in a temp dir to confirm nothing was committed that
  shouldn't have been (`git clone` then `Get-ChildItem -Recurse .secrets`).

If you find a leaked credential, **rotate it immediately** in GCP / SF and
remove from history with `git filter-repo`. Do not push the fix until the
secret has been rotated upstream.

---

## Step 2. Record the 90-second Loom

Use [`docs/loom-script.md`](../loom-script.md). Three takes. Ship the
cleanest.

Embed in:

- README top (badge + link).
- LinkedIn header.
- CV "Selected projects".

---

## Step 3. LinkedIn posts

Schedule a two-week cadence (keep drafts outside the repo):

- Week 0: architecture overview (README diagram + $0 cost story).
- Week 2: Data Cloud Zero Copy + OIDC handshake (see
  [phase3-zero-copy-setup.md](phase3-zero-copy-setup.md)).
- Week 4: BYO LLM shim recipe (Gemini via Cloud Run shim vs optional Vertex overlay for Model Builder screenshots).

Before posting each:

- Replace `<github-url>` placeholders with the real URL.
- Attach the hook image suggested in the post header.
- Tag relevant Salesforce + GCP community accounts (avoid mass-tagging).
- Respond to every comment within 24 h for the first week.

---

## Step 4. Community CFP submission

Use [`docs/cfp-template.md`](../cfp-template.md). Submit to one event in
your region. Track in the same file's submission checklist.

---

## Step 5. CV + portfolio surface updates

- LinkedIn About: one sentence on the project + Loom link.
- CV: one line in the "Selected projects" section. Include the repo URL.
- Personal site / Notion: full case-study page with the architecture
  diagram from the README and a paragraph on each phase.

---

## EXIT GATE

- Public repo URL works, no leaked secrets confirmed via fresh-clone test.
- Loom URL pinned in CV + LinkedIn header.
- At least one LinkedIn post published.
- One CFP submitted (acceptance not required for gate).
- Final commit tagged `v0.1.0` for the public launch.

---

## After-launch maintenance

- **Once a quarter.** Refresh `ATTRIBUTIONS.md` if new sources added.
  Re-run ETL to keep BigQuery marts current.
- **When Gemini quotas shift.** Update your local LLM operator notes and post a follow-up on LinkedIn if quotas change materially.
- **Weekly.** Hit the agent's `keep-alive` endpoint (a scheduled Apex job)
  so the DE org does not get auto-deactivated for inactivity.
- **When an interviewer asks about the build.** Open the repo, walk
  through `README.md` -> a phase runbook (e.g. phase 3 Zero Copy) -> `cloud-run/llm-shim/`.
  Code plus one runbook cover most of the architecture conversation.
