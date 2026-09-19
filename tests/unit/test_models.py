from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from career_agent.models.answer import AnswerRecord, RetentionClass, ReusePolicy
from career_agent.models.application import (
    ApplicationManifest,
    Outcome,
    OutcomeRecord,
    OutcomeSource,
    RecruitingEvent,
    RecruitingEventKind,
)
from career_agent.models.base import SourceReference
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.models.opportunity import (
    DiscoverySource,
    Opportunity,
    OpportunityStatus,
)
from career_agent.models.profile import ConfirmationState, ProfileFact
from career_agent.models.release import ArtifactRecord, ClaimReference, DocumentRelease
from career_agent.models.submission import (
    ApprovalRecord,
    EvidenceClaim,
    EvidenceLevel,
    SubmissionAttempt,
    SubmissionResolution,
    SubmissionStatus,
)
from career_agent.state_machine import InvalidWorkspaceState, validate_workspace_state

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)
CHECKSUM = "a" * 64


def source_reference() -> SourceReference:
    return SourceReference(source_id="SRC-0001", locator="resume.pdf#page=1", checksum=CHECKSUM)


def representative_models() -> list[object]:
    profile_fact = ProfileFact(
        fact_id="FACT-0001",
        key="employment.current_title",
        value="Product Manager",
        sources=(source_reference(),),
        confirmation_state=ConfirmationState.CONFIRMED,
        confirmer="user",
        confirmed_at=NOW,
    )
    opportunity = Opportunity(
        opportunity_id="OPP-2026-0001",
        company="Example Labs",
        title="Product Manager",
        location="Remote",
        status=OpportunityStatus.DISCOVERED,
        sources=(
            DiscoverySource(
                source_id="SRC-0002",
                url="https://jobs.example.test/roles/42",
                captured_at=NOW,
            ),
        ),
        posting_checksum=CHECKSUM,
    )
    answer = AnswerRecord(
        answer_id="ANS-0001",
        question_id="identity.preferred_name",
        value="Avery",
        source_reference="user-response-1",
        retention_class=RetentionClass.ORDINARY,
        reuse_policy=ReusePolicy.STABLE,
        confirmed_at=NOW,
    )
    evidence = EvidenceClaim(
        claim_id="EVD-0001",
        level=EvidenceLevel.EMPLOYER_CONFIRMED,
        source_reference="receipt-42",
        confidence=1,
    )
    attempt = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.CONFIRMED,
        approval_id="APR-0001",
        resolution=SubmissionResolution.CONFIRMED,
        evidence=(evidence,),
    )
    event = RecruitingEvent(
        event_id="EVT-0001",
        kind=RecruitingEventKind.INTERVIEW,
        occurred_at=NOW,
        source_reference="calendar-event-42",
    )
    outcome = OutcomeRecord(
        outcome=Outcome.REJECTED,
        source=OutcomeSource.ATTRIBUTABLE_EVIDENCE,
        source_reference="email-message-42",
    )
    application = ApplicationManifest(
        application_id="APP-2026-0001",
        opportunity_id=opportunity.opportunity_id,
        stage="closed",
        submission_status=SubmissionStatus.CONFIRMED,
        events=(event,),
        attempts=(attempt,),
        outcome=outcome,
    )
    release = DocumentRelease(
        release_id="REL-0001",
        application_id=application.application_id,
        artifacts=(
            ArtifactRecord(
                artifact_type="resume_pdf",
                relative_path="releases/REL-0001/resume.pdf",
                checksum=CHECKSUM,
            ),
        ),
        claims=(ClaimReference(claim_id="CLAIM-0001", fact_ids=(profile_fact.fact_id,)),),
    )
    approval = ApprovalRecord(
        approval_id="APR-0001",
        submission_id=attempt.submission_id,
        payload_digest=CHECKSUM,
        nonce="nonce-42",
        approving_actor="user",
        runtime_session="session-42",
        approved_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    operation = OperationRecord(
        run_id="RUN-0001",
        operation="application.create",
        idempotency_key="fixture-key",
        status=OperationStatus.STARTED,
    )
    return [profile_fact, opportunity, answer, attempt, application, release, approval, operation]


@pytest.mark.parametrize("model", representative_models())
def test_persisted_model_round_trips_without_losing_types(model: object) -> None:
    model_type = type(model)
    encoded = model.model_dump_json()  # type: ignore[attr-defined]

    assert model_type.model_validate_json(encoded) == model  # type: ignore[attr-defined]


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ApplicationManifest.model_validate(
            {
                "application_id": "APP-2026-0001",
                "opportunity_id": "OPP-2026-0001",
                "unexpected": True,
            }
        )


def test_unknown_schema_version_is_rejected() -> None:
    with pytest.raises(ValidationError, match="literal_error"):
        ApplicationManifest(
            schema_version=2,
            application_id="APP-2026-0001",
            opportunity_id="OPP-2026-0001",
        )


def test_naive_persisted_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        Opportunity(
            opportunity_id="OPP-2026-0001",
            company="Example Labs",
            title="Product Manager",
            location="Remote",
            status=OpportunityStatus.DISCOVERED,
            sources=(
                DiscoverySource(
                    source_id="SRC-0002",
                    url="https://jobs.example.test/roles/42",
                    captured_at=NOW,
                ),
            ),
            posting_checksum=CHECKSUM,
            created_at=datetime(2026, 9, 18, 17, 30),
        )
    assert error.value.errors()[0]["type"] == "timezone_aware"


def test_naive_event_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        RecruitingEvent(
            event_id="EVT-0001",
            kind=RecruitingEventKind.INTERVIEW,
            occurred_at=datetime(2026, 9, 18, 17, 30),
            source_reference="calendar-event-42",
        )
    assert error.value.errors()[0]["type"] == "timezone_aware"


def test_confirmed_profile_fact_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="confirmed fact requires evidence"):
        ProfileFact(
            fact_id="FACT-0001",
            key="employment.current_title",
            value="Product Manager",
            confirmation_state=ConfirmationState.CONFIRMED,
            confirmer="user",
            confirmed_at=NOW,
        )


def test_attributable_outcome_requires_source_reference() -> None:
    with pytest.raises(ValidationError, match="source reference"):
        OutcomeRecord(
            outcome=Outcome.REJECTED,
            source=OutcomeSource.ATTRIBUTABLE_EVIDENCE,
        )


def test_prohibited_answer_cannot_be_persisted() -> None:
    with pytest.raises(ValidationError, match="prohibited answers cannot be persisted"):
        AnswerRecord(
            answer_id="ANS-0001",
            question_id="credential.password",
            value="not-a-real-secret",
            source_reference="fixture",
            retention_class=RetentionClass.PROHIBITED,
            reuse_policy=ReusePolicy.APPLICATION_ONLY,
            confirmed_at=NOW,
        )


def test_duplicate_attempt_ids_are_rejected_by_workspace_validation() -> None:
    attempt = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.IN_PROGRESS,
        approval_id="APR-0001",
    )
    application = ApplicationManifest(
        application_id="APP-2026-0001",
        opportunity_id="OPP-2026-0001",
        attempts=(attempt, attempt),
    )

    with pytest.raises(InvalidWorkspaceState, match="attempt IDs must be unique"):
        validate_workspace_state(application)
