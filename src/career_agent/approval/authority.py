"""Runtime-neutral authority contract for human submission approval."""

from __future__ import annotations

from typing import Protocol

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, JsonValue

from career_agent.models.base import ApplicationId, SubmissionId, UtcDateTime


class ApprovalFieldSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_id: str
    value: JsonValue
    requires_final_review: bool


class ApprovalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: ApplicationId
    submission_id: SubmissionId
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    destination: AnyHttpUrl
    artifact_filenames: tuple[str, ...]
    attachment_filenames: tuple[str, ...]
    fields: tuple[ApprovalFieldSummary, ...]
    high_risk_field_ids: tuple[str, ...]
    attestations: tuple[str, ...]
    anomalies: tuple[str, ...]
    irreversible_action: str = Field(min_length=1)


class ApprovalAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    nonce: str = Field(min_length=1)
    approving_actor: str = Field(min_length=1)
    runtime_session: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    approved_at: UtcDateTime
    provenance_reference: str = Field(min_length=1)


class ApprovalAuthority(Protocol):
    def request(
        self,
        summary: ApprovalSummary,
        payload_digest: str,
        nonce: str,
    ) -> ApprovalAttestation: ...
