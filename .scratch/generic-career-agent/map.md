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

## Fog

- Real runtime approval primitives vary. Ticket 11 must demonstrate a trustworthy adapter or force the interactive CLI fallback for that runtime.
- Windows filesystem behavior must be proven on the declared supported environment, not inferred from Unix fixtures.
- Real portals remain manually compatibility-checked without submission; automated release evidence comes only from the fake portal.
