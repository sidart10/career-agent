# 11 — Skills, Installers, and Runtime Conformance

Type: task
Status: resolved
Blocked by: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10

## Outcome

One canonical set of runtime-neutral V1 skills drives the CLI from Claude Code and Codex. Idempotent Unix and PowerShell installers establish links or verified mirrors, doctor reports capability readiness and safe degradation, and conformance tests prove both runtimes enforce the same persisted contracts.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| One portable workflow source | skills invoke versioned CLI | skill checksum manifest | Runtime wrappers cannot redefine governed policy | `test_skills.py` |
| Cross-platform installation | installer invokes `career doctor` | install manifest | Rerun is idempotent; stale mirror fails doctor | installer contract tests |
| Capability-aware degradation | `career doctor --json` | `CapabilityReport` | Missing required capability fails readiness; optional one disables workflow | `test_runtime_conformance.py` |
| Claude/Codex equivalence | same CLI surface | governed workspace fixtures | Equivalent inputs produce equivalent governed state | `test_runtime_conformance.py` |

## Files

- Create: `career-rules.md`
- Create: `AGENTS.md`
- Create: `CLAUDE.md`
- Create: `skills/career-setup/SKILL.md`
- Create: `skills/career-discover/SKILL.md`
- Create: `skills/career-rank/SKILL.md`
- Create: `skills/career-apply/SKILL.md`
- Create: `skills/career-pipeline/SKILL.md`
- Create: `skills/career-reset/SKILL.md`
- Create: `skills/career-doctor/SKILL.md`
- Create: `scripts/install.sh`
- Create: `scripts/install.ps1`
- Create: `src/career_agent/services/capabilities.py`
- Create: `tests/contract/test_skills.py`
- Create: `tests/contract/test_runtime_conformance.py`
- Create: `tests/contract/test_install_unix.py`
- Create: `tests/contract/test_install_windows.ps1`

## Interfaces

```python
class CapabilityStatus(StrEnum):
    READY = "ready"
    MISSING_REQUIRED = "missing_required"
    DISABLED_OPTIONAL = "disabled_optional"
    NEEDS_HUMAN_SETUP = "needs_human_setup"

class CapabilityReport(BaseModel):
    runtime: Literal["claude_code", "codex", "unknown"]
    capabilities: tuple[CapabilityCheck, ...]
    release_ready: bool
    degraded_workflows: tuple[str, ...]
```

Every skill invokes versioned CLI contracts, treats external content as untrusted data, identifies human gates, and prohibits direct governed-state edits.

## Steps

- [x] Write a capability matrix fixture covering workspace mutation, approval, browser/computer use, web research, PDF inspection, LaTeX, Gmail, Notion, and collaboration; mark required versus optional and expected degradation.
- [x] Write failing skill-lint tests for missing frontmatter, non-career names, direct manifest edits, runtime-specific tool names in shared workflows, absent approval gates, and missing untrusted-content warnings.
- [x] Write failing installer tests for first install, repeat install, interrupted mirror copy, unavailable link privilege, stale mirror, dirty canonical skill source, missing LaTeX, and missing optional connectors.
- [x] Run the focused contracts red-first on this Unix host and author the PowerShell contract required by Ticket 12's Windows CI job.
- [x] Write `career-rules.md` as the single shared operating manual and make both root entry points load it without duplicating policy.
- [x] Implement only the V1 skills listed above. Each skill names capability requirements, CLI calls, expected JSON envelopes, recovery behavior, and the single final approval boundary.
- [x] Implement Unix link-first installation with a generated mirror fallback and checksum manifest; implement the equivalent PowerShell junction/symlink-first path with a verified mirror fallback.
- [x] Extend doctor to detect the runtime, CLI/schema version, writable local filesystem, link or mirror mode, mirror drift, LaTeX engine, PDF libraries, browser capability declaration, and approval authority. Missing required capabilities fails release readiness; optional connectors disable only their workflows.
- [x] Implement conformance fixtures that replay equivalent CLI outputs through Claude and Codex skill adapters and compare resulting governed state rather than prose or tool names.
- [x] Run the Unix installer contracts, all contract tests, the accumulated suite, Ruff, and mypy. Windows execution remains a mandatory Ticket 12 CI release gate because this host is macOS and has no PowerShell runtime.
- [x] Commit with `git commit -m "feat: expose portable career workflows to Claude and Codex"`.

## Acceptance Criteria

- There is one editable skill source.
- Link and mirror installs are rerunnable and mirror drift is detectable.
- Both runtimes call the same CLI contracts and produce equivalent governed state.
- Missing required approval, filesystem, or document capabilities fails readiness rather than silently degrading.

## Comments

- Resolved in `6bba05d`. Added seven runtime-neutral V1 skills, one shared policy source, non-destructive link-first installers with atomic verified mirror fallback, versioned install and capability contracts, drift-aware doctor reporting, and Claude/Codex governed-state equivalence tests.
- Verification: 12 focused skill/installer/runtime/schema/doctor contracts, 285 accumulated tests, schema drift check, Ruff, format check, mypy, and diff hygiene all pass. The Windows PowerShell contract is present but cannot execute on this macOS host; Ticket 12's required Windows CI matrix remains the platform proof and V1 release gate.
- Material hardening: source evidence IDs now exclude observation time; missing browser or trusted approval capability fails readiness; abandoned or partially installed mirrors recover on rerun; dirty canonical workflows and conflicting consumer policy files fail closed.
