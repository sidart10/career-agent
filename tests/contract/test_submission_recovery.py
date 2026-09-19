from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.submission import EvidenceLevel, SubmissionStatus
from career_agent.services.applications import ApplicationService
from career_agent.services.approvals import ApprovalService
from career_agent.services.payloads import PayloadService
from career_agent.services.submissions import EmployerConfirmation, SubmissionService

from ..unit.test_submission_service import approved_submission

NOW = datetime(2026, 9, 18, 20, 30, tzinfo=UTC)


def test_external_success_before_local_commit_recovers_without_duplicate_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id, approval_id = approved_submission(root)
    service = SubmissionService(root)
    digest = PayloadService.digest(PayloadService(root).load(application_id, submission_id))
    service.begin(
        application_id,
        submission_id,
        approval_id,
        observed_payload_digest=digest,
        browser_state_verified=True,
        browser_state_reference="browser-session-1#final-review",
        now=NOW,
    )
    evidence = EmployerConfirmation(
        claim_id="employer-receipt",
        source_reference="https://jobs.example.test/confirmation/ABC-42",
        observed_at=NOW,
        confidence=1,
        receipt_id="ABC-42",
        limitations=("confirmation did not echo uploaded bytes",),
    )
    real_commit = service.repository.journal.commit
    interrupted = False

    def interrupt_commit(run_id: str, result: object) -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise OSError("simulated local commit interruption after employer success")
        real_commit(run_id, result)  # type: ignore[arg-type]

    monkeypatch.setattr(service.repository.journal, "commit", interrupt_commit)
    with pytest.raises(OSError, match="employer success"):
        service.confirm(application_id, submission_id, evidence)

    recovered = service.confirm(application_id, submission_id, evidence)

    assert recovered.status is SubmissionStatus.CONFIRMED
    employer_claims = [
        claim for claim in recovered.evidence if claim.level is EvidenceLevel.EMPLOYER_CONFIRMED
    ]
    assert len(employer_claims) == 1
    assert employer_claims[0].claim_id == "employer-receipt"


def test_begin_recovers_consumption_commit_without_reusing_nonce(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id, approval_id = approved_submission(root)
    service = SubmissionService(root)
    digest = PayloadService.digest(PayloadService(root).load(application_id, submission_id))
    real_commit = service.approvals.journal.commit
    interrupted = False

    def interrupt_consumption_commit(run_id: str, result: object) -> None:
        nonlocal interrupted
        if not interrupted and isinstance(result, dict) and "consumption_checksum" in result:
            interrupted = True
            raise OSError("simulated consumption commit interruption")
        real_commit(run_id, result)  # type: ignore[arg-type]

    monkeypatch.setattr(service.approvals.journal, "commit", interrupt_consumption_commit)
    with pytest.raises(OSError, match="consumption commit"):
        service.begin(
            application_id,
            submission_id,
            approval_id,
            observed_payload_digest=digest,
            browser_state_verified=True,
            browser_state_reference="browser-session-1#final-review",
            now=NOW,
        )

    recovered = service.begin(
        application_id,
        submission_id,
        approval_id,
        observed_payload_digest=digest,
        browser_state_verified=True,
        browser_state_reference="browser-session-1#final-review",
        now=NOW,
    )

    assert recovered.status is SubmissionStatus.IN_PROGRESS
    assert len(ApplicationService(root).load(application_id).attempts) == 1
    with pytest.raises(CareerError) as consumed:
        ApprovalService(root).validate(
            application_id,
            submission_id,
            approval_id,
            now=NOW,
        )
    assert consumed.value.code is ErrorCode.CONFLICT
