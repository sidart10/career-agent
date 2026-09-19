"""Document release, artifact, and claim provenance contracts."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from career_agent.models.base import ApplicationId, PersistedModel
from career_agent.models.profile import FactId

ReleaseId = Annotated[str, Field(pattern=r"^REL-\d{4}$")]
ClaimId = Annotated[str, Field(pattern=r"^CLAIM-\d{4}$")]


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_type: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("relative_path")
    @classmethod
    def path_is_relative_and_contained(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact path must remain relative")
        return value


class ClaimReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: ClaimId
    fact_ids: tuple[FactId, ...] = Field(min_length=1)


class DocumentRelease(PersistedModel):
    release_id: ReleaseId
    application_id: ApplicationId
    artifacts: tuple[ArtifactRecord, ...] = Field(min_length=1)
    claims: tuple[ClaimReference, ...] = ()
