"""Submission attempt and evidence vocabulary."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from career_agent.models.base import ApprovalId, PersistedModel, SubmissionId, UtcDateTime


class SubmissionStatus(StrEnum):
    NONE = "none"
    IN_PROGRESS = "in_progress"
    UNCERTAIN = "uncertain"
    CONFIRMED = "confirmed"


class SubmissionResolution(StrEnum):
    CONFIRMED = "confirmed"
    UNSUCCESSFUL = "unsuccessful"


class EvidenceLevel(StrEnum):
    PLANNED = "planned"
    OBSERVED = "observed"
    EMPLOYER_CONFIRMED = "employer_confirmed"


class EvidenceClaim(PersistedModel):
    claim_id: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    level: EvidenceLevel
    source_reference: str = Field(min_length=1)
    observed_at: UtcDateTime
    value: JsonValue | None = None
    confidence: float = Field(ge=0, le=1)
    limitations: tuple[str, ...] = ()


class SubmissionAttempt(PersistedModel):
    submission_id: SubmissionId
    status: SubmissionStatus
    approval_id: ApprovalId
    payload_digest: str = Field(default="0" * 64, pattern=r"^[a-f0-9]{64}$")
    resolution: SubmissionResolution | None = None
    evidence: tuple[EvidenceClaim, ...] = ()

    @model_validator(mode="after")
    def status_and_resolution_agree(self) -> SubmissionAttempt:
        claim_ids = [claim.claim_id for claim in self.evidence]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("submission evidence claim IDs must be unique")
        if self.status is SubmissionStatus.NONE:
            raise ValueError("a submission attempt cannot have status none")
        if self.status is SubmissionStatus.IN_PROGRESS and self.resolution is not None:
            raise ValueError("an in-progress attempt cannot be resolved")
        if (
            self.status is SubmissionStatus.CONFIRMED
            and self.resolution is not SubmissionResolution.CONFIRMED
        ):
            raise ValueError("a confirmed attempt requires confirmed resolution")
        if (
            self.resolution is SubmissionResolution.CONFIRMED
            and self.status is not SubmissionStatus.CONFIRMED
        ):
            raise ValueError("confirmed resolution requires confirmed status")
        if (
            self.resolution is SubmissionResolution.UNSUCCESSFUL
            and self.status is not SubmissionStatus.UNCERTAIN
        ):
            raise ValueError("unsuccessful resolution applies only to an uncertain attempt")
        return self


class ApprovalRecord(PersistedModel):
    approval_id: ApprovalId
    submission_id: SubmissionId
    payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    digest_algorithm: Literal["sha256-v1"] = "sha256-v1"
    nonce: str = Field(min_length=1)
    approving_actor: str = Field(min_length=1)
    runtime_session: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    provenance_reference: str = Field(min_length=1)
    attestation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_at: UtcDateTime
    expires_at: UtcDateTime

    @model_validator(mode="after")
    def expiry_follows_approval(self) -> ApprovalRecord:
        if self.expires_at <= self.approved_at:
            raise ValueError("approval expiry must follow approval time")
        return self
