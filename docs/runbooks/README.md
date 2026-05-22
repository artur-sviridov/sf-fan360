# Runbooks

Each phase of the build has a runbook documenting the human-only steps - the parts a coding agent cannot perform: account signups, payment-method entry, browser-UI configuration, OAuth/OIDC handshakes, screenshot capture for portfolio evidence.

Read in order. Each runbook starts from a known state (the previous runbook's exit gate) and ends at a verifiable exit gate.


| #   | Runbook                                                  | Phase                                             | Time |
| --- | -------------------------------------------------------- | ------------------------------------------------- | ---- |
| 0   | [phase0-provisioning.md](phase0-provisioning.md)         | Account + toolchain                               | ~4 h |
| 1   | [phase1-historical-etl.md](phase1-historical-etl.md)     | Historical ETL execution                          | ~2 h |
| 2   | [phase2-live-feed.md](phase2-live-feed.md)               | Cloud Run deploy + fixture-driven scheduler guard | ~2 h |
| 3   | [phase3-zero-copy-setup.md](phase3-zero-copy-setup.md)   | OIDC + Data Cloud UI                              | ~4 h |
| 4   | [phase4-vector-rag.md](phase4-vector-rag.md)             | Knowledge + Vector DB upload                      | ~2 h |
| 5   | [phase5-agent-build.md](phase5-agent-build.md)           | Agent Builder + ADLC loops                        | ~6 h |
| 6   | [phase6-byo-llm.md](phase6-byo-llm.md)                   | Model Builder + Vertex overlay                    | ~3 h |
| 7   | [phase7-experience-cloud.md](phase7-experience-cloud.md) | Site publish + guest user                         | ~2 h |
| 8   | [phase8-portfolio.md](phase8-portfolio.md)               | Loom, LinkedIn, CFP                               | ~3 h |


## Conventions used in these runbooks

- `> SF` prefixes a click-path inside the Salesforce Setup UI.
- `> GCP` prefixes a click-path inside the Google Cloud Console.
- `$` prefixes a shell command (PowerShell on Windows by default).
- **EXIT GATE** at the end of each runbook is what must be true before moving on. If the gate fails, fix it before continuing - downstream phases assume every prior gate holds.
- **EVIDENCE** boxes call out artifacts to screenshot or save into `docs/trust-layer-evidence/` for the eventual portfolio.

