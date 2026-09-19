from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class PortalScenario(StrEnum):
    HAPPY_PATH = "happy_path"
    CONDITIONAL_AFTER_APPROVAL = "conditional_after_approval"
    NORMALIZE_VALUE = "normalize_value"
    REJECT_UPLOAD = "reject_upload"
    SESSION_EXPIRES = "session_expires"
    DELAYED_SUBMIT = "delayed_submit"
    DUPLICATE_CLICK = "duplicate_click"
    PARTIAL_SUCCESS = "partial_success"
    NO_CONFIRMATION = "no_confirmation"
    NETWORK_FAIL_AFTER_SUBMIT = "network_fail_after_submit"


class PortalSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_token: str = Field(min_length=1)
    fields: dict[str, str]
    uploads: dict[str, str]


class FakePortalReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(min_length=1)
    echoed_fields: dict[str, str]
    received_file_digests: dict[str, str]
    submitted_at: AwareDatetime
    anomalies: tuple[str, ...] = ()
    evidence_limitations: tuple[str, ...] = ()

    @classmethod
    def at(
        cls,
        *,
        receipt_id: str,
        echoed_fields: dict[str, str],
        received_file_digests: dict[str, str],
        submitted_at: datetime,
        anomalies: tuple[str, ...] = (),
        evidence_limitations: tuple[str, ...] = (),
    ) -> FakePortalReceipt:
        return cls(
            receipt_id=receipt_id,
            echoed_fields=echoed_fields,
            received_file_digests=received_file_digests,
            submitted_at=submitted_at,
            anomalies=anomalies,
            evidence_limitations=evidence_limitations,
        )
