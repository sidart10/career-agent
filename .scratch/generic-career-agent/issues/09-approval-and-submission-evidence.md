# 09 — Approval and Submission Evidence

Type: task
Status: resolved
Blocked by: 03, 06, 07, 08

## Outcome

The CLI creates a deterministic canonical submission payload, accepts approval only through a provenance-preserving authority, binds it to one nonce and attempt, invalidates it on every material mutation, and records planned, observed, and employer-confirmed evidence without duplicate retry after uncertainty.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Canonical final review | `career submission prepare` | `CanonicalSubmissionPayload` | Every consequential field/artifact is digest-bound | `test_canonical_payload.py` |
| Trusted approval | `career submission approve` | `ApprovalRecord` | No boolean/noninteractive bypass; one nonce and attempt only | `test_approval_cli.py` |
| Safe irreversible action | `career submission begin` | `SubmissionAttempt` | Immediate digest mismatch, expiry, or stale posting refuses action | `test_approval_service.py` |
| Honest evidence | `career submission observe|confirm|resolve` | evidence-level records | Observation cannot become employer confirmation; uncertainty blocks retry | `test_submission_service.py`, `test_submission_recovery.py` |

## Files

- Create: `src/career_agent/services/payloads.py`
- Create: `src/career_agent/services/approvals.py`
- Create: `src/career_agent/services/submissions.py`
- Create: `src/career_agent/approval/authority.py`
- Create: `src/career_agent/approval/interactive.py`
- Modify: `src/career_agent/cli.py`
- Create: `tests/unit/test_canonical_payload.py`
- Create: `tests/unit/test_approval_service.py`
- Create: `tests/unit/test_submission_service.py`
- Create: `tests/contract/test_approval_cli.py`
- Create: `tests/contract/test_submission_recovery.py`

## Interfaces

```python
class ApprovalAuthority(Protocol):
    def request(self, summary: ApprovalSummary, payload_digest: str, nonce: str) -> ApprovalAttestation: ...

class PayloadService:
    def prepare(self, application_id: str) -> CanonicalSubmissionPayload: ...
    def serialize(self, payload: CanonicalSubmissionPayload) -> bytes: ...
    def digest(self, payload: CanonicalSubmissionPayload) -> str: ...

class SubmissionService:
    def approve(self, attempt_id: str, authority: ApprovalAuthority) -> ApprovalRecord: ...
    def begin(self, attempt_id: str, approval_id: str) -> SubmissionAttempt: ...
    def observe(self, attempt_id: str, evidence: ObservedEvidence) -> SubmissionAttempt: ...
    def confirm(self, attempt_id: str, evidence: EmployerConfirmation) -> SubmissionAttempt: ...
    def resolve_uncertain(self, attempt_id: str, resolution: Literal["confirmed", "unsuccessful"]) -> SubmissionAttempt: ...
```

Canonical serialization is UTF-8 JSON with sorted keys, no insignificant whitespace, normalized UTC timestamps excluded from the digest unless they are part of the reviewed payload, and a versioned `sha256` digest descriptor.

## Steps

- [x] Write golden-vector tests proving equivalent payloads serialize identically and any answer, attachment, checksum, destination, attestation, posting, conditional question, or material anomaly changes the digest.
- [x] Write failing tests proving an agent cannot pass an approval boolean or `--yes`, a non-interactive fallback is rejected, a nonce cannot be reused, an expired approval fails, and an approval cannot move between attempts.
- [x] Write failing recovery tests for timeout before submit, ambiguous result, external success before local commit, confirmation without echoed fields, and attempted retry while uncertain.
- [x] Run `uv run pytest tests/unit/test_canonical_payload.py tests/unit/test_approval_service.py tests/unit/test_submission_service.py -q` and confirm failure.
- [x] Implement canonical payload creation from checksum-verified releases, attachment copies, normalized answer fields, high-risk review flags, attestations, anomalies, posting freshness, destination, and irreversible action.
- [x] Implement `ApprovalAuthority`; the V1 fallback requires an attached interactive terminal, displays the summary and digest, issues a random one-time challenge, and stores the resulting attestation. There is no command-line flag or environment variable that bypasses the interaction.
- [x] Implement approval expiry, nonce consumption, digest recomputation immediately before `begin`, and invalidation from posting, answer, artifact, attachment, destination, or attestation changes.
- [x] Implement evidence records with `planned`, `observed`, and `employer_confirmed` levels and per-claim source, timestamp, confidence, and limitations.
- [x] Implement uncertainty so the attempt remains `uncertain`, the application remains `applying`, evidence is retained, and new attempts fail until explicit resolution.
- [x] Run focused tests, the accumulated suite, Ruff, and mypy.
- [x] Commit with `git commit -m "feat: bind trusted approval to submission evidence"`.

## Acceptance Criteria

- No bare agent-authored CLI argument can create approval.
- Every material payload change invalidates approval before the irreversible action.
- Lack of employer echo never becomes a claim of exact employer receipt.
- Crash replay after possible external success cannot create a second attempt.

## Comments

## Answer

Resolved in `8eaa647`. The implementation now creates deterministic, journal-sealed submission payloads from verified releases and attachment snapshots; accepts only provenance-preserving terminal approval bound to a versioned digest, nonce, attempt, actor, and expiry; consumes approvals exactly once with interruption repair; rechecks browser and payload state immediately before submission; and preserves typed planned, observed, and employer-confirmed evidence without upgrading uncertainty or unechoed fields into stronger claims. Material posting, answer, release, upload, attachment, destination, attestation, anomaly, and action changes fail closed before the irreversible action. Focused contract coverage includes noninteractive rejection, expiry, cross-attempt use, consumed-approval reissue, answer/attachment mutation, ambiguous outcomes, external-success recovery, and consumption-commit recovery. Final verification: 264 accumulated tests, schema drift check, Ruff, formatting, mypy, and diff hygiene all pass.
