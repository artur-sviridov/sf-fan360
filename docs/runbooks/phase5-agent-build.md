# Phase 5 - Agentforce Broadcast Metadata Agent

**Goal.** A working agent in the DE org that reasons over structured DMOs +
vector RAG, with Apex, Flow, Prompt Template, and External Service actions
wired. End-state: the three reference queries from the project plan all
succeed with citations.

**Time budget.** ~6 hours. Most of it is the ADLC iteration loop, not the
initial deploy.

**Prerequisites.** Phase 4 exit gate. Cloud Run llm-shim **does not need to
be deployed yet** for this phase - we use the standard models. Phase 6
swaps in the BYO LLM.

---

## Step 1. Deploy the Apex + Flow + metadata

```powershell
sf project deploy start -o s7dev `
    -d force-app/main/default/classes `
    -d force-app/main/default/flows `
    -d force-app/main/default/namedCredentials `
    -d force-app/main/default/externalCredentials `
    -d force-app/main/default/externalServiceRegistrations `
    -d force-app/main/default/genAiPromptTemplates
```

If the External Service deployment fails because the placeholder URL is not
reachable, edit
[`force-app/main/default/externalServiceRegistrations/Semantic_Search_Knowledge.externalServiceRegistration-meta.xml`](../../force-app/main/default/externalServiceRegistrations/Semantic_Search_Knowledge.externalServiceRegistration-meta.xml)
and replace `CLOUD_RUN_SHIM_URL_PLACEHOLDER` with the eventual shim URL,
even if the shim is not deployed yet. Deploy again.

Run the tests:

```powershell
sf apex run test -o s7dev `
    -n GetPlayerVsOpponentStatsTest,LookupCurrentMatchScoreTest `
    -r human -w 10
```

All 8 assertions must pass.

---

## Step 2. Deploy the Agent Script bundle

```powershell
sf project deploy start -o s7dev `
    -d force-app/main/default/aiAuthoringBundles/Broadcast_Metadata_Agent
```

> SF: App Launcher -> Agentforce -> Agents -> "Broadcast Metadata Agent" ->
> Open in Agent Builder.

Before activating:

1. Set `default_agent_user` in the bundle's `.agent` file to a real user
   id. Use a dedicated `Agent_User` with the AFDX_Agent_Perms permission
   set group assigned (already included in the template).
2. Confirm every Topic has its instructions visible in the right pane.
3. Confirm every Action card resolves (no red errors).

---

## Step 3. Wire up Guardrails

> SF: Agent Builder -> Settings -> Guardrails.

Add three guardrails:

- **PII Output Filter** - block any response containing email regex
  `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}` or phone-number regex.
- **No Betting Content** - regex `(?i)\b(odds|accumulator|acca|bet|stake|spread)\b`.
- **Response Length Cap** - max 400 tokens.

**EVIDENCE.** Screenshot the Guardrails page ->
`docs/trust-layer-evidence/05-guardrails.png`.

---

## Step 4. ADLC loop #1 - smoke test

> SF: Agent Builder -> Test.

Feed each topic 10 reference utterances (keep your test matrix locally: structured stats, live match, tactical context, out-of-scope refusals).

Watch the reasoning trace for each:

- Did the router pick the correct subagent?
- Did the right action fire?
- Did the response carry a citation?

Log every failure (mis-routed topic, missing citation, hallucinated fact,
guardrail triggered when it shouldn't have) in your local ADLC journal
(utterance, trace, fix, re-test). Update agent instructions accordingly.

---

## Step 5. ADLC loop #2 - refinement

After your first refinement pass, repeat the 10x5 test set. Look for:

- Routing now correct >= 95% of the time.
- Every response has at least one citation.
- No guardrail false positives.
- Live match topic gracefully handles "no match in progress".

Document the diffs vs loop #1 in the ADLC log.

---

## Step 6. Verify the three reference queries

| Query | Expected route | Expected citation |
|---|---|---|
| "Has anyone scored more goals against Manchester United than Salah?" | player_stats -> GetPlayerVsOpponentStats | `PlayerVsOpponent__cio.goals__c` |
| "Why did Arsenal switch to a back five against Liverpool in 2024?" | tactical_context -> Semantic_Search_Knowledge | Wikipedia URL |
| "Who has the highest xG in the current match?" | live_match -> LookupCurrentMatchScore | `LiveMatchSnapshot__cio` |

**EVIDENCE.** Save a screen recording of these three queries succeeding ->
`docs/trust-layer-evidence/05-three-reference-queries.mp4` (or
`.gif`/`.png` triptych).

---

## EXIT GATE

- `sf apex run test` is green.
- Agent Builder testing console returns correct, cited answers for all
  three reference queries.
- ADLC log contains entries for at least 5 caught reasoning failures with
  the diff that fixed them.
- Guardrails screenshot archived.

Proceed to [phase6-byo-llm.md](phase6-byo-llm.md).
