# 02 — Domain Contracts and State Machine

Type: task
Status: ready-for-agent
Blocked by: 01

## Outcome

Versioned Pydantic contracts and JSON Schemas encode the profile, opportunity, application, answer, release, approval, submission, event, and operation-journal vocabulary. One transition validator enforces every state invariant in the specification.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Versioned governed state | consumed by every command | `schemas/*.schema.json` | Unknown versions and unknown fields fail closed | `test_models.py`, `test_schema_exports.py` |
| Orthogonal lifecycle | `career application transition` | `ApplicationManifest` | Only explicit table transitions and valid dimension combinations pass | `test_state_machine.py` |
| Repeatable recruiting activity | later event command | `RecruitingEvent` | Interview and offer events never become hidden stage transitions | `test_state_machine.py` |

## Files

- Create: `src/career_agent/models/base.py`
- Create: `src/career_agent/models/profile.py`
- Create: `src/career_agent/models/opportunity.py`
- Create: `src/career_agent/models/application.py`
- Create: `src/career_agent/models/answer.py`
- Create: `src/career_agent/models/release.py`
- Create: `src/career_agent/models/submission.py`
- Create: `src/career_agent/models/operation.py`
- Create: `src/career_agent/state_machine.py`
- Create: `scripts/export_schemas.py`
- Create: `schemas/*.schema.json`
- Create: `tests/unit/test_models.py`
- Create: `tests/unit/test_state_machine.py`
- Create: `tests/contract/test_schema_exports.py`

## Interfaces

```python
class OpportunityStatus(StrEnum):
    DISCOVERED = "discovered"
    EVALUATING = "evaluating"
    PURSUED = "pursued"
    DISMISSED = "dismissed"
    EXPIRED = "expired"

class ApplicationStage(StrEnum):
    PREPARING = "preparing"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    APPLYING = "applying"
    SUBMITTED = "submitted"
    CLOSED = "closed"

class SubmissionStatus(StrEnum):
    NONE = "none"
    IN_PROGRESS = "in_progress"
    UNCERTAIN = "uncertain"
    CONFIRMED = "confirmed"

class Outcome(StrEnum):
    OFFER_ACCEPTED = "offer_accepted"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    NO_RESPONSE = "no_response"
    OFFER_DECLINED = "offer_declined"

def validate_transition(before: ApplicationManifest, after: ApplicationManifest) -> None: ...
def validate_workspace_state(application: ApplicationManifest) -> None: ...
```

Every persisted object contains `schema_version`, stable ID, UTC timestamps, and explicit source references. Unknown schema versions fail closed.

## Steps

- [ ] Write parameterized failing tests for every allowed application transition and every forbidden cross-dimensional combination listed under `State Transition and Integrity Invariants`.
- [ ] Add property tests proving that arbitrary event insertion cannot produce `submitted` without a confirmed attempt and that `uncertain` blocks a new attempt.
- [ ] Run `uv run pytest tests/unit/test_state_machine.py -q` and confirm collection or import failure.
- [ ] Implement the enums, immutable identifiers, timestamps, source references, evidence levels, event records, and manifest models.
- [ ] Implement `validate_transition` as an explicit transition table plus cross-dimensional invariant checks; do not infer transitions from enum ordering.
- [ ] Implement deterministic JSON Schema export with sorted keys and a check mode that fails when committed schemas drift.
- [ ] Write round-trip tests for every persisted model and rejection tests for unknown fields, unknown schema versions, naive timestamps, reused IDs, and invalid evidence references.
- [ ] Run `uv run python scripts/export_schemas.py --check`, `uv run mypy src`, and `uv run pytest tests/unit/test_models.py tests/unit/test_state_machine.py tests/contract/test_schema_exports.py -q`.
- [ ] Commit with `git commit -m "feat: define career workspace contracts and state machine"`.

## Acceptance Criteria

- The specification's state vocabulary exists once in typed code.
- Every allowed transition is enumerated and every listed invariant has a negative test.
- Interviews and offers are repeatable events, not application stages.
- Schema generation is deterministic and drift-tested.

## Comments
