from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest

from career_agent.approval.authority import ApprovalAttestation, ApprovalSummary
from career_agent.approval.interactive import InteractiveApprovalAuthority
from career_agent.errors import CareerError, ErrorCode
from career_agent.models.answer import RetentionClass, ReusePolicy
from career_agent.models.application import ApplicationStage
from career_agent.models.release import ArtifactType
from career_agent.services.answers import AnswerService, SetAnswerCommand
from career_agent.services.applications import ApplicationService
from career_agent.services.approvals import ApprovalService
from career_agent.services.payloads import (
    AttachmentCategory,
    AttachmentRequest,
    PayloadField,
    PayloadService,
    PrepareSubmissionRequest,
)

from .documents.test_release import request as release_request
from .documents.test_release import setup_workspace

NOW = datetime(2026, 9, 18, 20, 30, tzinfo=UTC)


class TtyStringIO(StringIO):
    def isatty(self) -> bool:
        return True


class FakeAuthority:
    def __init__(self, *, mutate_digest: bool = False) -> None:
        self.mutate_digest = mutate_digest
        self.summary: ApprovalSummary | None = None

    def request(
        self,
        summary: ApprovalSummary,
        payload_digest: str,
        nonce: str,
    ) -> ApprovalAttestation:
        self.summary = summary
        return ApprovalAttestation(
            payload_digest="f" * 64 if self.mutate_digest else payload_digest,
            nonce=nonce,
            approving_actor="synthetic-user",
            runtime_session="test-terminal-1",
            authority="test-trusted-authority",
            approved_at=NOW,
            provenance_reference="test-attestation-1",
        )


def prepare_submission(
    root: Path,
    *,
    with_attachment: bool = False,
    with_answer: bool = False,
) -> tuple[str, str]:
    application_id, _ = setup_workspace(root)
    from career_agent.documents.release import DocumentService

    documents = DocumentService(root)
    release = documents.create_release(application_id, release_request())
    upload = documents.prepare_upload_copy(
        application_id,
        release.release_id,
        ArtifactType.RESUME_PDF,
    )
    ApplicationService(root).transition(
        application_id,
        ApplicationStage.READY_FOR_REVIEW,
        "final review assembled",
    )
    attachments: tuple[AttachmentRequest, ...] = ()
    if with_attachment:
        source = root / "resources" / "portfolio.pdf"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"verified portfolio")
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        attachments = (
            AttachmentRequest(
                attachment_id="portfolio",
                category=AttachmentCategory.PORTFOLIO,
                source_relative_path="resources/portfolio.pdf",
                upload_filename="Portfolio.pdf",
                checksum=checksum,
            ),
        )
    answer_id: str | None = None
    if with_answer:
        answer = AnswerService(root).set(
            SetAnswerCommand(
                question_id="contact.email",
                value="avery@example.test",
                exact_user_response="avery@example.test",
                source_reference="user-confirmation-1",
                retention_class=RetentionClass.ORDINARY,
                reuse_policy=ReusePolicy.STABLE,
                confirmed_at=NOW,
            )
        )
        answer_id = answer.answer_id
    payload = PayloadService(root).prepare(
        application_id,
        PrepareSubmissionRequest(
            release_id=release.release_id,
            upload_record_paths=(upload.record_path,),
            attachments=attachments,
            fields=(
                PayloadField(
                    field_id="contact.email",
                    value="avery@example.test",
                    answer_id=answer_id,
                    retention_class=RetentionClass.ORDINARY,
                ),
            ),
            destination="https://jobs.example.test/apply/42",
            irreversible_action="Submit application",
            idempotency_key="prepare-42",
        ),
    )
    return application_id, payload.submission_id


def test_trusted_attestation_binds_digest_nonce_and_attempt(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(root)
    authority = FakeAuthority()
    service = ApprovalService(root)

    approval = service.approve(
        application_id,
        submission_id,
        authority,
        ttl=timedelta(minutes=15),
        now=NOW,
    )

    assert approval.approval_id == "APR-0001"
    assert approval.submission_id == submission_id
    assert approval.payload_digest == PayloadService.digest(
        PayloadService(root).load(application_id, submission_id)
    )
    assert approval.nonce
    assert approval.approving_actor == "synthetic-user"
    assert authority.summary is not None
    assert ApplicationService(root).load(application_id).stage is ApplicationStage.APPROVED
    assert service.load(application_id, submission_id, approval.approval_id) == approval


def test_authority_must_echo_exact_digest_and_nonce(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(root)

    with pytest.raises(CareerError) as error:
        ApprovalService(root).approve(
            application_id,
            submission_id,
            FakeAuthority(mutate_digest=True),
            now=NOW,
        )

    assert error.value.code is ErrorCode.INVALID_INPUT
    assert ApplicationService(root).load(application_id).stage is ApplicationStage.READY_FOR_REVIEW


def test_expired_approval_and_cross_attempt_use_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(root)
    service = ApprovalService(root)
    approval = service.approve(
        application_id,
        submission_id,
        FakeAuthority(),
        ttl=timedelta(minutes=5),
        now=NOW,
    )

    with pytest.raises(CareerError) as expired:
        service.validate(
            application_id,
            submission_id,
            approval.approval_id,
            now=NOW + timedelta(minutes=6),
        )
    with pytest.raises(CareerError) as moved:
        service.validate(
            application_id,
            "SUB-9999",
            approval.approval_id,
            now=NOW,
        )

    assert expired.value.code is ErrorCode.NOT_READY
    assert moved.value.code is ErrorCode.INVALID_INPUT


def test_consumed_approval_is_never_reissued_as_fresh(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(root)
    service = ApprovalService(root)
    first = service.approve(
        application_id,
        submission_id,
        FakeAuthority(),
        ttl=timedelta(minutes=15),
        now=NOW,
    )
    service.consume(
        application_id,
        submission_id,
        first.approval_id,
        consumed_at=NOW + timedelta(minutes=1),
    )

    second = service.approve(
        application_id,
        submission_id,
        FakeAuthority(),
        ttl=timedelta(minutes=15),
        now=NOW + timedelta(minutes=2),
    )

    assert second.approval_id != first.approval_id
    assert second.nonce != first.nonce


def test_stale_payload_cannot_reuse_existing_approval(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(root, with_answer=True)
    service = ApprovalService(root)
    service.approve(application_id, submission_id, FakeAuthority(), now=NOW)
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
        service.approve(
            application_id,
            submission_id,
            FakeAuthority(),
            now=NOW + timedelta(minutes=2),
        )

    assert error.value.code is ErrorCode.NOT_READY


def test_interactive_authority_requires_attached_tty_and_exact_challenge() -> None:
    summary = ApprovalSummary(
        application_id="APP-2026-0001",
        submission_id="SUB-0001",
        company="Example Labs",
        role="Product Manager",
        destination="https://jobs.example.test/apply/42",
        artifact_filenames=("Avery_Resume_abcd1234.pdf",),
        attachment_filenames=(),
        fields=(),
        high_risk_field_ids=(),
        attestations=(),
        anomalies=(),
        irreversible_action="Submit application",
    )
    digest = "a" * 64
    nonce = "one-time-nonce"

    with pytest.raises(CareerError) as detached:
        InteractiveApprovalAuthority(
            input_stream=StringIO("synthetic-user\nAPPROVE one-time-nonce\n"),
            output_stream=StringIO(),
        ).request(summary, digest, nonce)

    output = TtyStringIO()
    attestation = InteractiveApprovalAuthority(
        input_stream=TtyStringIO("synthetic-user\nAPPROVE one-time-nonce\n"),
        output_stream=output,
    ).request(summary, digest, nonce)

    assert detached.value.code is ErrorCode.NOT_READY
    assert attestation.payload_digest == digest
    assert attestation.nonce == nonce
    assert attestation.approving_actor == "synthetic-user"
    assert "sha256-v1" in output.getvalue()
