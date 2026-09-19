"""Document release, artifact, and claim provenance contracts."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from career_agent.models.base import ApplicationId, PersistedModel, SourceReference, UtcDateTime
from career_agent.models.profile import FactId

ReleaseId = Annotated[str, Field(pattern=r"^REL-\d{4}$")]
ClaimId = Annotated[str, Field(pattern=r"^CLAIM-\d{4}$")]


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path must remain relative")
    return value


class ArtifactType(StrEnum):
    RESUME_PDF = "resume_pdf"
    COVER_LETTER_PDF = "cover_letter_pdf"
    RESUME_DOCX = "resume_docx"
    COVER_LETTER_DOCX = "cover_letter_docx"


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_type: ArtifactType
    relative_path: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("relative_path")
    @classmethod
    def path_is_relative_and_contained(cls, value: str) -> str:
        return _relative_path(value)


class ClaimReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: ClaimId
    fact_ids: tuple[FactId, ...] = ()
    evidence_sources: tuple[SourceReference, ...] = ()

    @model_validator(mode="after")
    def has_grounding_reference(self) -> ClaimReference:
        if not self.fact_ids and not self.evidence_sources:
            raise ValueError("claim requires a confirmed fact or evidence source")
        return self


class ValidationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_type: ArtifactType
    passed: bool
    report_path: str = Field(min_length=1)
    report_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("report_path")
    @classmethod
    def path_is_relative_and_contained(cls, value: str) -> str:
        return _relative_path(value)


class DocumentRelease(PersistedModel):
    release_id: ReleaseId
    application_id: ApplicationId
    artifacts: tuple[ArtifactRecord, ...] = Field(min_length=1)
    claims: tuple[ClaimReference, ...] = ()
    validation_reports: tuple[ValidationSummary, ...] = ()
    request_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def artifact_validation_and_claim_identities_are_unique(self) -> DocumentRelease:
        artifact_types = [artifact.artifact_type for artifact in self.artifacts]
        report_types = [report.artifact_type for report in self.validation_reports]
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(artifact_types) != len(set(artifact_types)):
            raise ValueError("release artifact types must be unique")
        if len(report_types) != len(set(report_types)):
            raise ValueError("release validation report types must be unique")
        if set(report_types) != set(artifact_types) or any(
            not report.passed for report in self.validation_reports
        ):
            raise ValueError("every release artifact requires a passing validation report")
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("release claim IDs must be unique")
        return self


class UploadArtifact(PersistedModel):
    application_id: ApplicationId
    release_id: ReleaseId
    artifact_type: ArtifactType
    filename: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    record_path: str = Field(min_length=1)
    source_relative_path: str = Field(min_length=1)
    source_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    employer_receipt_confirmed: Literal[False] = False
    valid: bool = True
    invalidated_at: UtcDateTime | None = None
    invalidation_reason: str | None = None

    @field_validator("relative_path", "record_path", "source_relative_path")
    @classmethod
    def paths_are_relative_and_contained(cls, value: str) -> str:
        return _relative_path(value)

    @field_validator("filename")
    @classmethod
    def filename_is_a_basename(cls, value: str) -> str:
        if PurePosixPath(value).name != value:
            raise ValueError("upload filename must not contain a path")
        return value
