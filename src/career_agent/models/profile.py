"""Candidate profile facts and evidence status."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, JsonValue, model_validator

from career_agent.models.base import PersistedModel, SourceReference, UtcDateTime

FactId = Annotated[str, Field(pattern=r"^FACT-\d{4}$")]


class ConfirmationState(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ProfileFact(PersistedModel):
    fact_id: FactId
    key: str = Field(min_length=1)
    value: JsonValue
    sources: tuple[SourceReference, ...] = ()
    confirmation_state: ConfirmationState = ConfirmationState.PROPOSED
    confirmer: str | None = None
    confirmed_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def confirmation_has_evidence_and_actor(self) -> ProfileFact:
        if self.confirmation_state is ConfirmationState.CONFIRMED:
            if not self.sources:
                raise ValueError("confirmed fact requires evidence")
            if not self.confirmer or self.confirmed_at is None:
                raise ValueError("confirmed fact requires confirmer and confirmation time")
        elif self.confirmer is not None or self.confirmed_at is not None:
            raise ValueError("only a confirmed fact may record confirmation metadata")
        return self
