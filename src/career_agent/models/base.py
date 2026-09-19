"""Shared primitives for persisted career workspace models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal[1] = 1

ApplicationId = Annotated[str, Field(pattern=r"^APP-\d{4}-\d{4}$")]
OpportunityId = Annotated[str, Field(pattern=r"^OPP-\d{4}-\d{4}$")]
SubmissionId = Annotated[str, Field(pattern=r"^SUB-\d{4}$")]
ApprovalId = Annotated[str, Field(pattern=r"^APR-\d{4}$")]
EventId = Annotated[str, Field(pattern=r"^EVT-\d{4}$")]


def normalize_utc(value: datetime) -> datetime:
    """Normalize an already timezone-aware timestamp to UTC."""

    return value.astimezone(UTC)


UtcDateTime = Annotated[AwareDatetime, AfterValidator(normalize_utc)]


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(UTC)


class PersistedModel(BaseModel):
    """Strict, immutable base for every governed persisted record."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    schema_version: Literal[1] = SCHEMA_VERSION
    created_at: UtcDateTime = Field(default_factory=utc_now)
    updated_at: UtcDateTime = Field(default_factory=utc_now)


class SourceReference(BaseModel):
    """Explicit pointer to evidence outside the current record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
