# 06 — Applications and Posting Freshness

Type: task
Status: resolved
Blocked by: 02, 03, 05

## Outcome

Pursuing an opportunity creates one application-owned record with a stable ID, posting snapshot, drafts, events, and validated lifecycle. Freshness checks detect material changes or closure and invalidate readiness without erasing history.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Complete application ownership | `career opportunity pursue`, `career application show` | `ApplicationManifest` | Stable ID survives slug changes and owns all later artifacts | `test_applications.py` |
| Posting preservation | `career application posting-check` | `PostingSnapshot`, `PostingChangeSet` | Original capture is never overwritten | `test_posting_freshness.py` |
| Readiness invalidation | `career application posting-check` | application event and stage | Material or uncertain changes invalidate approval/readiness | `test_posting_freshness.py` |
| Repeatable recruiting events | `career application transition` plus event service | `RecruitingEvent` | Events cannot bypass submission transitions | `test_recruiting_events.py` |

## Files

- Create: `src/career_agent/services/applications.py`
- Create: `src/career_agent/services/postings.py`
- Create: `src/career_agent/services/events.py`
- Modify: `src/career_agent/cli.py`
- Create: `tests/unit/test_applications.py`
- Create: `tests/unit/test_posting_freshness.py`
- Create: `tests/unit/test_recruiting_events.py`
- Create: `tests/contract/test_application_cli.py`

## Interfaces

```python
class ApplicationService:
    def create_from_opportunity(self, opportunity_id: str, idempotency_key: str) -> ApplicationManifest: ...
    def transition(self, application_id: str, target: ApplicationStage, reason: str) -> ApplicationManifest: ...
    def add_event(self, application_id: str, event: RecruitingEvent) -> ApplicationManifest: ...

class PostingService:
    def capture(self, application_id: str, posting: PostingCapture) -> PostingSnapshot: ...
    def compare(self, previous: PostingSnapshot, current: PostingSnapshot) -> PostingChangeSet: ...
    def apply_freshness(self, application_id: str, change_set: PostingChangeSet) -> ApplicationManifest: ...
```

Material fields are availability, responsibilities, location, compensation, eligibility, deadline, and employer requisition identity. Cosmetic text, ordering, analytics parameters, and presentation markup are non-material.

## Steps

- [ ] Write failing tests for stable year-scoped application IDs, slug renames without identity changes, idempotent pursuit, application-local release/submission namespaces, and an expired opportunity with preserved application history.
- [ ] Write posting-diff fixtures for whitespace-only edits, reordered sections, changed responsibility, location change, compensation change, eligibility change, closure, and a reused URL pointing at a new requisition.
- [ ] Run `uv run pytest tests/unit/test_applications.py tests/unit/test_posting_freshness.py -q` and confirm failure.
- [ ] Implement application directory creation through the storage repository using stable ID plus readable slug; manifests refer to IDs rather than path-derived identity.
- [ ] Implement posting snapshots with raw capture, normalized text, source URL, retrieval time, checksum, and source adapter metadata.
- [ ] Implement deterministic material-change classification for structured fields and schema-validated model assistance for unstructured responsibility changes; uncertain classification is material and returns to review.
- [ ] Implement transition invalidation: a material change moves `ready_for_review` or `approved` to `preparing`, invalidates approvals, and records an event; closure blocks new attempts and marks the opportunity expired.
- [ ] Implement repeatable interview, follow-up, and offer events without turning them into application stages.
- [ ] Run focused tests, the accumulated suite, Ruff, and mypy.
- [ ] Commit with `git commit -m "feat: create application records and posting freshness checks"`.

## Acceptance Criteria

- Renaming a company or role never changes application identity.
- Every application contains the original posting basis and subsequent freshness history.
- Material or uncertain changes invalidate readiness and approval.
- Interviews and offers may repeat without illegal stage regressions.

## Comments

- 2026-09-18 — Implemented on `feature/generic-career-agent-v1` in commit `582e8a0`.
- RED evidence: application tests first failed because ownership services did not exist; freshness tests failed because structured comparisons, invalidation, and immutable history did not exist; event tests failed because lifecycle-safe append operations did not exist; CLI contracts failed because pursue/application commands did not exist. Pressure tests then exposed index/status crash windows, cross-opportunity idempotency reuse, concurrent pursuit races, mutable posting history, stale comparisons, unvalidated snapshot IDs, availability handling, and malformed responsibility-classifier output.
- GREEN evidence: 29 focused application/freshness/event/CLI tests and 178 accumulated tests pass; deterministic schema checking, Ruff, formatting, strict mypy, and diff checks all pass.
- Design note: application IDs are stable and independent of display slugs. A workspace lock serializes the one-application-per-opportunity claim, while journal replay repairs manifest/index/status interruptions without recycling sequence numbers.
- Design note: every posting check preserves an immutable raw snapshot and adjacent change record. Structured availability, responsibility, location, compensation, eligibility, deadline, and requisition changes are material; cosmetic ordering/tracking changes are ignored; malformed or unavailable unstructured classification fails closed to `uncertain`.
- Design note: material or uncertain changes invalidate readiness/approval and append a status event. Closure also expires the opportunity and blocks new submission attempts without deleting application history. Interviews, follow-ups, and offers remain repeatable events rather than lifecycle stages.
