# 07 — Answer Bank and Privacy

Type: task
Status: ready-for-agent
Blocked by: 02, 03

## Outcome

Application answers are stored, proposed, reused, overridden, exported, and deleted according to explicit retention and reuse policies. High-risk aliases require confirmation, sensitive values are opt-in and redacted by default, and prohibited data never reaches disk.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Risk-aware resolution | `career answer resolve` | `AnswerResolution` | High-risk ambiguity returns `needs_confirmation`, never automatic reuse | `test_answer_resolution.py` |
| Controlled persistence | `career answer set` | `AnswerRecord` | Sensitive requires opt-in; prohibited refuses before journal write | `test_answer_retention.py` |
| Data control | `career answer list|export|delete` | `DeletionPreview`, `DeletionResult` | Default output is redacted and delete reports survivors | `test_answer_cli.py` |
| Diagnostic redaction | all commands | sanitized audit event | Values cannot leak to errors, logs, snapshots, or projections | `test_redaction.py` |

## Files

- Create: `src/career_agent/services/answers.py`
- Create: `src/career_agent/security/redaction.py`
- Create: `src/career_agent/security/prohibited_values.py`
- Modify: `src/career_agent/cli.py`
- Create: `tests/fixtures/answers/wording-variants.json`
- Create: `tests/unit/test_answer_resolution.py`
- Create: `tests/unit/test_answer_retention.py`
- Create: `tests/unit/test_redaction.py`
- Create: `tests/contract/test_answer_cli.py`

## Interfaces

```python
class RetentionClass(StrEnum):
    ORDINARY = "ordinary"
    CONTEXTUAL = "contextual"
    HIGH_RISK = "high_risk"
    SENSITIVE = "sensitive"
    PROHIBITED = "prohibited"

class ReusePolicy(StrEnum):
    STABLE = "stable"
    VERIFY_ON_CONFLICT = "verify_on_conflict"
    VERIFY_PER_JURISDICTION = "verify_per_jurisdiction"
    VERIFY_PER_APPLICATION = "verify_per_application"
    APPLICATION_ONLY = "application_only"
    EXPIRES_AFTER = "expires_after"

class AnswerService:
    def resolve(self, question: QuestionContext) -> AnswerResolution: ...
    def set(self, command: SetAnswerCommand) -> AnswerRecord: ...
    def delete_preview(self, answer_id: str) -> DeletionPreview: ...
    def delete(self, answer_id: str, preview_digest: str) -> DeletionResult: ...
```

## Steps

- [ ] Build wording fixtures covering sponsorship polarity, current-versus-future authorization, relocation assistance, compensation period/currency, compound questions, demographic categories, disability, veteran status, criminal history, and low-risk contact fields.
- [ ] Write failing tests proving low-risk registered aliases resolve, ambiguous or reversed questions do not, high-risk aliases require confirmation, and contextual answers require an exact scope match.
- [ ] Write failing tests proving prohibited patterns and typed prohibited fields never appear in answer files, journals, errors, logs, snapshots, or generated views.
- [ ] Run `uv run pytest tests/unit/test_answer_resolution.py tests/unit/test_answer_retention.py tests/unit/test_redaction.py -q` and confirm failure.
- [ ] Implement canonical question IDs, registered alias metadata, polarity/time-horizon/jurisdiction/unit checks, and schema-validated resolution results with `resolved`, `needs_confirmation`, or `unknown` status.
- [ ] Implement answer storage with source, exact user response, retention class, reuse policy, confirmation time, scope, sensitivity, aliases, and application-specific overrides.
- [ ] Require explicit opt-in for sensitive retention and surface every reused high-risk answer in the final review payload.
- [ ] Implement redacted-by-default list and export, owner-only exact sensitive export, digest-bound delete preview, alias deletion, and reporting of historical references that survive.
- [ ] Run focused tests, the accumulated suite, Ruff, mypy, and a repository scan fixture proving seeded secrets do not appear in generated artifacts.
- [ ] Commit with `git commit -m "feat: add risk-aware application answer bank"`.

## Acceptance Criteria

- No high-risk semantic alias is learned automatically.
- Legal and compensation fields follow field-specific policies rather than a global age.
- Sensitive persistence and exact export require distinct explicit consent.
- Delete never overclaims erasure when historical evidence survives.
- Prohibited values have negative persistence tests across every storage surface.

## Comments
