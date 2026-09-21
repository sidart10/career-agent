from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.answer import RetentionClass, ReusePolicy
from career_agent.models.application import ApplicationStage
from career_agent.models.submission import SubmissionResolution, SubmissionStatus
from career_agent.services.answers import AnswerService, SetAnswerCommand
from career_agent.services.applications import ApplicationService
from career_agent.services.approvals import ApprovalService
from career_agent.services.payloads import PayloadService, PrepareSubmissionRequest
from career_agent.services.submissions import (
    EmployerConfirmation,
    ObservedEvidence,
    SubmissionService,
)

from .test_approval_service import FakeAuthority, prepare_submission

NOW = datetime(2026, 9, 18, 20, 30, tzinfo=UTC)


def approved_submission(root: Path) -> tuple[str, str, str]:
    application_id, submission_id = prepare_submission(root)
    approval = ApprovalService(root).approve(
        application_id,
        submission_id,
        FakeAuthority(),
        ttl=timedelta(minutes=15),
        now=NOW,
    )
    return application_id, submission_id, approval.approval_id


def test_begin_rechecks_digest_consumes_nonce_and_creates_one_attempt(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id, approval_id = approved_submission(root)
    digest = PayloadService.digest(PayloadService(root).load(application_id, submission_id))
    service = SubmissionService(root)

    attempt = service.begin(
        application_id,
        submission_id,
        approval_id,
        observed_payload_digest=digest,
        browser_state_verified=True,
        browser_state_reference="browser-session-1#final-review",
        now=NOW + timedelta(minutes=1),
    )
    replayed = service.begin(
        application_id,
        submission_id,
        approval_id,
        observed_payload_digest=digest,
        browser_state_verified=True,
        browser_state_reference="browser-session-1#final-review",
        now=NOW + timedelta(minutes=1),
    )

    assert replayed == attempt
    assert attempt.status is SubmissionStatus.IN_PROGRESS
    assert attempt.payload_digest == digest
    assert attempt.evidence[0].claim_type == "submission_payload"
    assert attempt.evidence[0].value == {
        "browser_state_reference": "browser-session-1#final-review",
        "field_ids": ["contact.email"],
        "payload_digest": digest,
    }
    assert attempt.evidence[0].observed_at == NOW + timedelta(minutes=1)
    application = ApplicationService(root).load(application_id)
    assert application.stage is ApplicationStage.APPLYING
    assert application.submission_status is SubmissionStatus.IN_PROGRESS
    with pytest.raises(CareerError) as consumed:
        ApprovalService(root).validate(
            application_id,
            submission_id,
            approval_id,
            now=NOW + timedelta(minutes=1),
        )
    assert consumed.value.code is ErrorCode.CONFLICT


def test_begin_refuses_browser_or_payload_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id, approval_id = approved_submission(root)
    service = SubmissionService(root)

    with pytest.raises(CareerError) as digest_error:
        service.begin(
            application_id,
            submission_id,
            approval_id,
            observed_payload_digest="f" * 64,
            browser_state_verified=True,
            browser_state_reference="browser-session-1#final-review",
            now=NOW,
        )
    with pytest.raises(CareerError) as browser_error:
        service.begin(
            application_id,
            submission_id,
            approval_id,
            observed_payload_digest=PayloadService.digest(
                PayloadService(root).load(application_id, submission_id)
            ),
            browser_state_verified=False,
            browser_state_reference="browser-session-1#final-review",
            now=NOW,
        )

    assert digest_error.value.code is ErrorCode.NOT_READY
    assert browser_error.value.code is ErrorCode.NOT_READY
    application = ApplicationService(root).load(application_id)
    assert application.stage is ApplicationStage.READY_FOR_REVIEW
    assert application.approval_invalidated_at is not None
    assert application.approval_invalidation_reason == (
        "observed portal payload changed after approval"
    )


def test_begin_invalidates_expired_approval(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(root)
    approval = ApprovalService(root).approve(
        application_id,
        submission_id,
        FakeAuthority(),
        ttl=timedelta(minutes=1),
        now=NOW,
    )
    payload = PayloadService(root).load(application_id, submission_id)

    with pytest.raises(CareerError) as error:
        SubmissionService(root).begin(
            application_id,
            submission_id,
            approval.approval_id,
            observed_payload_digest=PayloadService.digest(payload),
            browser_state_verified=True,
            browser_state_reference="browser-session-1#final-review",
            now=NOW + timedelta(minutes=2),
        )

    assert error.value.code is ErrorCode.NOT_READY
    application = ApplicationService(root).load(application_id)
    assert application.stage is ApplicationStage.READY_FOR_REVIEW
    assert application.approval_invalidation_reason == "submission approval is no longer valid"


def test_payload_tampering_invalidates_approval_and_returns_to_preparing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id, approval_id = approved_submission(root)
    payload_path = PayloadService(root).path(application_id, submission_id)
    raw = json.loads(payload_path.read_text())
    raw["destination"] = "https://jobs.example.test/apply/tampered"
    payload_path.write_text(json.dumps(raw))

    with pytest.raises(CareerError) as error:
        SubmissionService(root).begin(
            application_id,
            submission_id,
            approval_id,
            observed_payload_digest="a" * 64,
            browser_state_verified=True,
            browser_state_reference="browser-session-1#final-review",
            now=NOW,
        )

    assert error.value.code is ErrorCode.INTEGRITY_ERROR
    assert ApplicationService(root).load(application_id).stage is ApplicationStage.PREPARING


def test_attachment_mutation_invalidates_approval_before_begin(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(root, with_attachment=True)
    approval = ApprovalService(root).approve(
        application_id,
        submission_id,
        FakeAuthority(),
        now=NOW,
    )
    payload = PayloadService(root).load(application_id, submission_id)
    attachment_path = root / payload.attachments[0].relative_path
    attachment_path.write_bytes(b"tampered portfolio")

    with pytest.raises(CareerError) as error:
        SubmissionService(root).begin(
            application_id,
            submission_id,
            approval.approval_id,
            observed_payload_digest=PayloadService.digest(payload),
            browser_state_verified=True,
            browser_state_reference="browser-session-1#final-review",
            now=NOW,
        )

    assert error.value.code is ErrorCode.INTEGRITY_ERROR
    assert ApplicationService(root).load(application_id).stage is ApplicationStage.PREPARING


def test_answer_mutation_invalidates_approval_before_begin(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(root, with_answer=True)
    approval = ApprovalService(root).approve(
        application_id,
        submission_id,
        FakeAuthority(),
        now=NOW,
    )
    payload_digest = PayloadService.digest(PayloadService(root).load(application_id, submission_id))
    answer = AnswerService(root).load_state().answers[0]
    AnswerService(root).set(
        SetAnswerCommand(
            question_id=answer.question_id,
            value="new@example.test",
            exact_user_response="new@example.test",
            source_reference="user-confirmation-2",
            retention_class=RetentionClass.ORDINARY,
            reuse_policy=ReusePolicy.STABLE,
            confirmed_at=NOW + timedelta(minutes=1),
            allow_override=True,
        )
    )
    with pytest.raises(CareerError) as error:
        SubmissionService(root).begin(
            application_id,
            submission_id,
            approval.approval_id,
            observed_payload_digest=payload_digest,
            browser_state_verified=True,
            browser_state_reference="browser-session-1#final-review",
            now=NOW + timedelta(minutes=1),
        )

    assert error.value.code is ErrorCode.NOT_READY
    assert ApplicationService(root).load(application_id).stage is ApplicationStage.PREPARING


def test_ambiguous_observation_blocks_retry_until_unsuccessful_resolution(
    tmp_path: Path,
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

    uncertain = service.observe(
        application_id,
        submission_id,
        ObservedEvidence(
            claim_id="portal-timeout",
            source_reference="browser-session-1#timeout",
            observed_at=NOW + timedelta(seconds=30),
            confidence=0.5,
            limitations=("submit response timed out",),
            result="uncertain",
        ),
    )

    assert uncertain.status is SubmissionStatus.UNCERTAIN
    assert uncertain.evidence[-1].claim_type == "portal_result"
    assert uncertain.evidence[-1].observed_at == NOW + timedelta(seconds=30)
    assert uncertain.evidence[-1].value == {"result": "uncertain"}
    application = ApplicationService(root).load(application_id)
    assert application.stage is ApplicationStage.APPLYING
    assert application.submission_status is SubmissionStatus.UNCERTAIN
    original_payload = PayloadService(root).load(application_id, submission_id)
    upload_record = next((root / "applications" / application_id / "uploads").glob("*.pdf.json"))
    with pytest.raises(CareerError) as retry:
        PayloadService(root).prepare(
            application_id,
            PrepareSubmissionRequest(
                release_id=original_payload.release_id,
                upload_record_paths=(upload_record.relative_to(root).as_posix(),),
                fields=original_payload.fields,
                destination=str(original_payload.destination),
                irreversible_action=original_payload.irreversible_action,
                idempotency_key="retry-while-uncertain",
            ),
        )
    assert retry.value.code is ErrorCode.CONFLICT

    resolved = service.resolve_uncertain(
        application_id,
        submission_id,
        SubmissionResolution.UNSUCCESSFUL,
    )
    assert resolved.resolution is SubmissionResolution.UNSUCCESSFUL
    assert ApplicationService(root).load(application_id).stage is ApplicationStage.READY_FOR_REVIEW


def test_employer_confirmation_does_not_overclaim_unechoed_fields(tmp_path: Path) -> None:
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

    confirmed = service.confirm(
        application_id,
        submission_id,
        EmployerConfirmation(
            claim_id="employer-receipt",
            source_reference="https://jobs.example.test/confirmation/ABC-42",
            observed_at=NOW + timedelta(seconds=45),
            confidence=1,
            receipt_id="ABC-42",
            echoed_field_ids=(),
            limitations=("confirmation did not echo answers or uploaded bytes",),
        ),
    )

    assert confirmed.status is SubmissionStatus.CONFIRMED
    assert confirmed.resolution is SubmissionResolution.CONFIRMED
    employer_claim = confirmed.evidence[-1]
    assert employer_claim.level.value == "employer_confirmed"
    assert employer_claim.claim_type == "employer_receipt"
    assert employer_claim.observed_at == NOW + timedelta(seconds=45)
    assert employer_claim.value == {"echoed_field_ids": [], "receipt_id": "ABC-42"}
    assert "uploaded bytes" in employer_claim.limitations[0]
    application = ApplicationService(root).load(application_id)
    assert application.stage is ApplicationStage.SUBMITTED
    assert application.submission_status is SubmissionStatus.CONFIRMED


def test_employer_confirmation_rejects_unreviewed_echoed_fields(tmp_path: Path) -> None:
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

    with pytest.raises(CareerError) as error:
        service.confirm(
            application_id,
            submission_id,
            EmployerConfirmation(
                claim_id="employer-receipt",
                source_reference="https://jobs.example.test/confirmation/ABC-42",
                observed_at=NOW + timedelta(seconds=45),
                confidence=1,
                receipt_id="ABC-42",
                echoed_field_ids=("unreviewed.field",),
            ),
        )

    assert error.value.code is ErrorCode.INVALID_INPUT
    application = ApplicationService(root).load(application_id)
    assert application.stage is ApplicationStage.APPLYING
    assert application.submission_status is SubmissionStatus.IN_PROGRESS


def test_confirmation_uses_frozen_review_after_post_submit_answer_change(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(root, with_answer=True)
    approval = ApprovalService(root).approve(
        application_id,
        submission_id,
        FakeAuthority(),
        now=NOW,
    )
    service = SubmissionService(root)
    payload = PayloadService(root).load(application_id, submission_id)
    service.begin(
        application_id,
        submission_id,
        approval.approval_id,
        observed_payload_digest=PayloadService.digest(payload),
        browser_state_verified=True,
        browser_state_reference="browser-session-1#final-review",
        now=NOW,
    )
    answer = AnswerService(root).load_state().answers[0]
    AnswerService(root).set(
        SetAnswerCommand(
            question_id=answer.question_id,
            value="new@example.test",
            exact_user_response="new@example.test",
            source_reference="user-confirmation-2",
            retention_class=RetentionClass.ORDINARY,
            reuse_policy=ReusePolicy.STABLE,
            confirmed_at=NOW + timedelta(minutes=1),
            allow_override=True,
        )
    )

    confirmed = service.confirm(
        application_id,
        submission_id,
        EmployerConfirmation(
            claim_id="employer-receipt",
            source_reference="https://jobs.example.test/confirmation/ABC-42",
            observed_at=NOW + timedelta(minutes=1),
            confidence=1,
            receipt_id="ABC-42",
            echoed_field_ids=("contact.email",),
        ),
    )

    assert confirmed.status is SubmissionStatus.CONFIRMED
    assert confirmed.evidence[-1].value == {
        "echoed_field_ids": ["contact.email"],
        "receipt_id": "ABC-42",
    }
