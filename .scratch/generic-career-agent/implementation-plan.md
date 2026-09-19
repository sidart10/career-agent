# Generic Career Agent V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the bounded V1 reliable application loop defined in `spec.md` for one candidate on one local machine.

**Architecture:** A Python package exposes a versioned `career` CLI as the sole writer of governed state. Runtime-neutral Agent Skills orchestrate research, drafting, browser interaction, and human communication while the CLI owns schemas, locks, journals, state transitions, releases, approval records, evidence, and generated projections. Personal data lives under a gitignored `.career/` workspace; tracked source contains only code, schemas, skills, templates, documentation, and synthetic fixtures.

**Tech Stack:** Python 3.11+, Typer, Pydantic 2, platformdirs, portalocker, pypdf, PyMuPDF, pytest, Hypothesis, Ruff, mypy, uv, LaTeX (`lualatex` or `xelatex`), PowerShell 7 for the Windows installer, and test-only FastAPI/Playwright for the local fake employer portal.

**Spec:** `.scratch/generic-career-agent/spec.md`

## Global Constraints

- The CLI is the sole writer of governed state; agents may directly edit only declared draft files.
- Application manifests and operation journals are authoritative; `pipeline.md` is disposable generated output.
- Personal data is gitignored by default and custom application-level encryption is out of scope.
- Final submission requires trusted human approval bound to one canonical payload digest and one attempt.
- Submission records distinguish planned, observed, and employer-confirmed evidence.
- Sensitive answers require explicit retention opt-in; prohibited values are never persisted.
- LaTeX/PDF is the required V1 document pipeline and doctor fails document readiness without a supported engine.
- Automated tests never contact or submit to a real employer, inbox, or production Notion workspace.
- V1 supports macOS, Linux, and Windows through the declared execution and installer matrix.
- Every implementation ticket follows red-green-refactor, runs its focused tests, then runs the accumulated suite before commit.

---

## Locked File Structure

```text
pyproject.toml                         Package metadata, pinned dependency groups, CLI entry point
uv.lock                               Reproducible Python dependency lock
src/career_agent/cli.py               Typer command tree and exit-code mapping
src/career_agent/config.py            Versioned configuration and workspace discovery
src/career_agent/errors.py            Stable typed errors and public error codes
src/career_agent/models/              Pydantic domain and persisted-contract models
src/career_agent/storage/             Locks, atomic replacement, journals, checksums, ID registry
src/career_agent/services/            Use-case services invoked by CLI commands
src/career_agent/documents/           LaTeX rendering, PDF validation, release assembly
src/career_agent/projections/         Generated pipeline projection
src/career_agent/security/            Path, symlink, redaction, and untrusted-input guards
schemas/                              Exported JSON Schemas for persisted formats
skills/                               Canonical runtime-neutral career-namespaced Agent Skills
.claude/skills/                       Installer-managed links or generated mirrors
AGENTS.md                             Codex entry point loading shared career operating rules
CLAUDE.md                             Claude Code entry point loading the same shared rules
career-rules.md                       Shared runtime-neutral operating manual
scripts/install.sh                    Idempotent Unix installer
scripts/install.ps1                   Idempotent PowerShell installer
tests/unit/                           Pure model and service tests
tests/contract/                       CLI, schema, runtime, connector, and installer contracts
tests/e2e/fake_portal/                Configurable local employer portal fixture
tests/e2e/                            Happy-path, uncertain-result, adversarial, and recovery journeys
tests/fixtures/                       Synthetic candidate, posting, email, PDF, and disorder fixtures
```

## Public CLI Surface

```text
career init
career doctor [--json]
career import preview|apply
career profile conflicts|confirm
career opportunity add|list|merge|unmerge|evaluate|pursue
career application show|transition|posting-check
career answer resolve|list|set|delete|export
career release create|verify|list
career submission prepare|approve|begin|observe|confirm|resolve
career pipeline build
career cleanup
career migrate plan|apply
career reset preview|apply
```

All machine-readable commands support `--json`, write structured output to stdout, diagnostics to stderr, and use documented nonzero exit codes from `career_agent.errors.ErrorCode`.

## Dependency Order

```text
01 foundation and provenance
 ├─> 02 domain contracts
 │    └─> 03 storage kernel
 │         ├─> 04 profile import
 │         │    └─> 05 opportunities and evaluation
 │         │         └─> 06 applications and posting freshness
 │         └─> 07 answer bank
 │
 ├────────────── 08 documents and releases <─ 04 + 06
 └────────────── 09 approval and submissions <─ 06 + 07 + 08
                  └─> 10 projections, migration, cleanup, reset
                       └─> 11 skills, installers, runtime conformance
                            └─> 12 fake-portal release gate
```

## Coverage Matrix

| Spec responsibility | Owning ticket |
|---|---|
| Packaging, pinned upstream provenance, capability inventory, doctor baseline | 01 |
| Persisted schemas, state vocabulary, transition invariants, evidence model | 02 |
| Locks, journals, atomic writes, checksums, sequence IDs, safe paths | 03 |
| Immutable imports, profile facts, conflicts, source grounding | 04 |
| Opportunity capture, reversible deduplication, authoritative evaluation | 05 |
| Application records, posting snapshots, freshness invalidation, events | 06 |
| Risk-tiered answers, aliases, overrides, export, deletion | 07 |
| LaTeX rendering, PDF validation, release checksums, upload copies | 08 |
| Canonical payload, trusted approval, attempts, uncertain results, evidence | 09 |
| Pipeline, recovery, cleanup, migrations, reset | 10 |
| Shared rules, canonical skills, Claude/Codex discovery, installers | 11 |
| Happy path, uncertainty, adversarial portal, crash replay, release matrix | 12 |

## Execution Rules

1. Implement tickets in dependency order; tickets whose blockers are resolved may run independently.
2. Claim one issue by changing its `Status:` to `claimed` before editing production files.
3. Resolve an issue only after its focused and accumulated verification commands pass.
4. Append the commit, test evidence, and material decisions under the issue's `## Comments` heading.
5. Change `Status:` to `resolved` and add the result to `map.md`.
6. Do not broaden V1 with Gmail, Notion, salary analysis, interview preparation, upskilling, or third-party portal extension.

## Definition of V1 Complete

- All twelve tickets are resolved.
- The full unit, contract, property, installer, security, and end-to-end suites pass on the declared platform matrix.
- The fake portal proves both confirmed and uncertain submission paths without a duplicate attempt.
- Direct release tampering, self-approval, payload mutation, prompt injection, path traversal, symlink escape, stale locks, and crash replay are rejected by executable tests.
- A clean clone can install, initialize a synthetic workspace, execute the V1 journey, regenerate `pipeline.md`, and remove that workspace through a previewed reset.

## Self-Review Results

- **Spec coverage:** Every Initial Release Boundary capability maps to tickets 01–12. Explicitly deferred capabilities map to the parity matrix in ticket 01 and cannot block V1.
- **Requirement contracts:** Every ticket maps its owned requirements to CLI surfaces, persisted contracts, invariant or failure behavior, and named acceptance tests.
- **Type ownership:** Ticket 02 owns persisted domain types; ticket 03 owns storage primitives; later tickets consume those names without redefining their semantics.
- **Mutation ownership:** No ticket authorizes an Agent Skill, connector, projection, or browser step to write governed state directly.
- **Placeholder scan:** The plan and tickets contain no unresolved placeholder markers or unnamed test obligations.
- **Execution boundary:** This plan creates no production implementation; ticket 01 is the first executable change.
