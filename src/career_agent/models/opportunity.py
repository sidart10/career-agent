"""Lightweight opportunity and discovery-source contracts."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from career_agent.models.base import OpportunityId, PersistedModel, UtcDateTime


class OpportunityStatus(StrEnum):
    DISCOVERED = "discovered"
    EVALUATING = "evaluating"
    PURSUED = "pursued"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class DiscoverySource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    url: AnyHttpUrl
    captured_at: UtcDateTime
    original_url: str | None = None


class Opportunity(PersistedModel):
    opportunity_id: OpportunityId
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    status: OpportunityStatus = OpportunityStatus.DISCOVERED
    sources: tuple[DiscoverySource, ...] = Field(min_length=1)
    posting_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    requisition_id: str | None = None
    canonical_url: AnyHttpUrl | None = None
    posting_text: str = ""
    posting_complete: bool = False
    deadline: date | None = None
