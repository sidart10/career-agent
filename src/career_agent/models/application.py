"""Application lifecycle, outcome, and recruiting-event contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from career_agent.models.base import (
    ApplicationId,
    EventId,
    OpportunityId,
    PersistedModel,
    PostingSnapshotId,
    UtcDateTime,
)
from career_agent.models.release import ReleaseId
from career_agent.models.submission import SubmissionAttempt, SubmissionStatus


class ApplicationStage(StrEnum):
    PREPARING = "preparing"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    APPLYING = "applying"
    SUBMITTED = "submitted"
    CLOSED = "closed"


class RecruitingEventKind(StrEnum):
    INTERVIEW = "interview"
    OFFER = "offer"
    FOLLOW_UP = "follow_up"
    STATUS = "status"


class Outcome(StrEnum):
    OFFER_ACCEPTED = "offer_accepted"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    NO_RESPONSE = "no_response"
    OFFER_DECLINED = "offer_declined"


class OutcomeSource(StrEnum):
    USER_INSTRUCTION = "user_instruction"
    ATTRIBUTABLE_EVIDENCE = "attributable_evidence"


class RecruitingEvent(PersistedModel):
    event_id: EventId
    kind: RecruitingEventKind
    occurred_at: UtcDateTime
    source_reference: str = Field(min_length=1)
    reason: str | None = None
    from_stage: ApplicationStage | None = None
    to_stage: ApplicationStage | None = None


class OutcomeRecord(PersistedModel):
    outcome: Outcome
    source: OutcomeSource
    source_reference: str | None = None

    @model_validator(mode="after")
    def evidence_source_has_reference(self) -> OutcomeRecord:
        if self.source is OutcomeSource.ATTRIBUTABLE_EVIDENCE and not self.source_reference:
            raise ValueError("attributable evidence requires a source reference")
        return self


class ApplicationManifest(PersistedModel):
    application_id: ApplicationId
    opportunity_id: OpportunityId
    stage: ApplicationStage = ApplicationStage.PREPARING
    submission_status: SubmissionStatus = SubmissionStatus.NONE
    attempts: tuple[SubmissionAttempt, ...] = ()
    events: tuple[RecruitingEvent, ...] = ()
    outcome: OutcomeRecord | None = None
    closure_reason: str | None = None
    display_slug: str = "application"
    posting_snapshot_ids: tuple[PostingSnapshotId, ...] = ()
    current_posting_snapshot_id: PostingSnapshotId | None = None
    approval_invalidated_at: UtcDateTime | None = None
    approval_invalidation_reason: str | None = None
    posting_closed_at: UtcDateTime | None = None
    release_ids: tuple[ReleaseId, ...] = ()
    current_release_id: ReleaseId | None = None
