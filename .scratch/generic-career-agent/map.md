# Generic Career Agent V1 Wayfinder

## Notes

- Canonical requirements: [`spec.md`](spec.md)
- Execution plan: [`implementation-plan.md`](implementation-plan.md)
- Upstream evidence: [`upstream-ai-job-search-audit.md`](upstream-ai-job-search-audit.md)
- V1 deliberately excludes Gmail, Notion, interviews, offers, salary analysis, reporting, upskilling, upstream-update automation, private Git versioning, and third-party adapter extension.

## Ticket Map

| ID | Ticket | Blocked by | Initial state |
|---:|---|---|---|
| 01 | [Foundation and provenance](issues/01-foundation-and-provenance.md) | — | ready-for-agent |
| 02 | [Domain contracts and state machine](issues/02-domain-contracts-and-state-machine.md) | 01 | ready-for-agent |
| 03 | [Transactional storage kernel](issues/03-transactional-storage-kernel.md) | 01, 02 | ready-for-agent |
| 04 | [Profile import and evidence](issues/04-profile-import-and-evidence.md) | 02, 03 | ready-for-agent |
| 05 | [Opportunities, deduplication, and evaluation](issues/05-opportunities-and-evaluation.md) | 02, 03, 04 | ready-for-agent |
| 06 | [Applications and posting freshness](issues/06-applications-and-posting-freshness.md) | 02, 03, 05 | ready-for-agent |
| 07 | [Answer bank and privacy](issues/07-answer-bank-and-privacy.md) | 02, 03 | ready-for-agent |
| 08 | [Documents and releases](issues/08-documents-and-releases.md) | 03, 04, 06 | ready-for-agent |
| 09 | [Approval and submission evidence](issues/09-approval-and-submission-evidence.md) | 03, 06, 07, 08 | ready-for-agent |
| 10 | [Pipeline, recovery, migration, and reset](issues/10-pipeline-recovery-and-maintenance.md) | 03, 09 | ready-for-agent |
| 11 | [Skills, installers, and runtime conformance](issues/11-skills-installers-and-runtime-conformance.md) | 01–10 | ready-for-agent |
| 12 | [Adversarial end-to-end release gate](issues/12-adversarial-end-to-end-release-gate.md) | 01–11 | ready-for-agent |

## Decisions So Far

- 2026-09-18 — The specification was changed from `ready-for-agent` to `ready-for-decomposition`; V1 is the reliable application loop, not the entire upstream feature surface.
- 2026-09-18 — Python owns deterministic state and document operations; Agent Skills own host-runtime orchestration.
- 2026-09-18 — Application manifests and journals are authoritative; Markdown and external integrations are projections.
- 2026-09-18 — Approval must have preserved human provenance or fall back to an interactive CLI confirmation that the agent cannot self-issue.
- 2026-09-18 — Submission evidence uses planned, observed, and employer-confirmed levels rather than claiming exact employer receipt.
- 2026-09-18 — The reviewed V1 issue set now exists; `spec.md` is `decomposed`, and implementation begins at ticket 01.
- 2026-09-18 — Ticket 01 resolved in `3f35c16`: installable Python package, CLI/doctor baseline, stable error codes, pinned upstream provenance, and 32-capability parity inventory; 7 contract tests pass.
- 2026-09-18 — Ticket 02 resolved in `0d23699` plus invariant hardening `0b4c00a`: strict versioned domain models, explicit lifecycle table, cross-dimensional invariants, eight deterministic JSON Schemas, and 48 passing accumulated tests.
- 2026-09-18 — Ticket 03 resolved in `fb19592`: safe cross-platform paths and readiness, owned locks with stale recovery, atomic JSON replacement, hash-chained journals, monotonic sequence allocation, application transactions, and interruption-safe replay; 98 accumulated tests pass.
- 2026-09-18 — Ticket 04 resolved in `e58927f`: copy-first text/PDF/DOCX import, checksum deduplication, inert untrusted content, persistent conflicts, explicit evidence-bound confirmation, stable fact reuse, import/profile CLI contracts, and three new deterministic schemas; 121 accumulated tests pass.
- 2026-09-18 — Ticket 05 resolved in `87df615`: public URL safety, lightweight capture, exact-only automatic merges, reversible provenance snapshots, review-only similarity candidates, schema-validated evidence spans, computed fit scores, and four new deterministic schemas; 146 accumulated tests pass.
- 2026-09-18 — Ticket 06 resolved in `582e8a0`: stable application ownership, immutable posting snapshots and adjacent change history, fail-closed freshness classification, approval invalidation, closure propagation, repeatable recruiting events, concurrency-safe pursuit recovery, application CLI contracts, and four new deterministic schemas; 178 accumulated tests pass.
- 2026-09-18 — Ticket 07 resolved in `dab9c16`: policy-scoped reusable answers and overrides, risk-aware alias resolution, typed compensation, prohibited-value admission controls, redacted diagnostics/views, consent-gated sensitive retention/export, digest-bound deletion with survivor reporting, crash-safe sanitized journals, and four new deterministic schemas; 213 accumulated tests pass.
- 2026-09-18 — Ticket 08 resolved in `7731cd4`: bounded canonical LaTeX rendering with checksum provenance, application-owned PDF/DOCX drafts, mechanical ATS/layout validation, confirmed-evidence claim grounding, locked and journal-sealed append-only releases, tamper quarantine with readiness/upload invalidation, professional upload copies, and three new deterministic schemas; 233 accumulated tests pass.
- 2026-09-18 — Ticket 09 resolved in `8eaa647`: deterministic journal-sealed submission payloads, terminal-provenance approval bound to one digest/nonce/attempt, interruption-safe one-time consumption, immediate browser and payload revalidation, and honest planned/observed/employer-confirmed evidence with uncertainty-safe recovery; 264 accumulated tests pass.
- 2026-09-18 — Ticket 10 resolved in `5b4f8ee`: manifest-derived deterministic pipeline projection, conservative startup recovery with terminal quarantine, symlink-safe expiring cleanup, copy-first schema migrations with verified backups, and exact digest-bound local reset scopes separated from protected and remote deletion; 278 accumulated tests pass.
- 2026-09-18 — Ticket 11 resolved in `6bba05d`: seven canonical runtime-neutral skills, shared policy entry points, safe link-first Unix/PowerShell installers with verified mirror fallback, capability-aware doctor reporting, and equivalent Claude/Codex governed state; 285 accumulated tests pass. Windows execution remains an explicit Ticket 12 CI release gate.

## Fog

- Runtime approval remains fail-closed: doctor requires a trusted approval capability, and the submission workflow falls back to the interactive terminal authority rather than accepting model-authored approval.
- Windows filesystem behavior must be proven on the declared supported environment, not inferred from Unix fixtures.
- Real portals remain manually compatibility-checked without submission; automated release evidence comes only from the fake portal.
