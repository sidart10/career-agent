"""Reusable answer retention and reuse contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, JsonValue, model_validator

from career_agent.models.base import PersistedModel, UtcDateTime

AnswerId = Annotated[str, Field(pattern=r"^ANS-\d{4}$")]


class RetentionClass(StrEnum):
    ORDINARY = "ordinary"
    CONTEXTUAL = "contextual"
    HIGH_RISK = "high_risk"
    SENSITIVE = "sensitive"
    PROHIBITED = "prohibited"


class ReusePolicy(StrEnum):
    STABLE = "stable"
    VERIFY_ON_CONFLICT = "verify_on_conflict"
    VERIFY_PER_JURISDICTION = "verify_per_jurisdiction"
    VERIFY_PER_APPLICATION = "verify_per_application"
    APPLICATION_ONLY = "application_only"
    EXPIRES_AFTER = "expires_after"


class AnswerRecord(PersistedModel):
    answer_id: AnswerId
    question_id: str = Field(min_length=1)
    value: JsonValue
    source_reference: str = Field(min_length=1)
    retention_class: RetentionClass
    reuse_policy: ReusePolicy
    confirmed_at: UtcDateTime
    expires_at: UtcDateTime | None = None
    scope: dict[str, str] = Field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    exact_user_response: JsonValue | None = None

    @model_validator(mode="after")
    def policy_is_persistable(self) -> AnswerRecord:
        if self.retention_class is RetentionClass.PROHIBITED:
            raise ValueError("prohibited answers cannot be persisted")
        if self.reuse_policy is ReusePolicy.EXPIRES_AFTER and self.expires_at is None:
            raise ValueError("expires_after policy requires an expiry")
        return self
