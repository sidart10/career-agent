"""Long-running operation and replay metadata."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from career_agent.models.base import PersistedModel

RunId = Annotated[str, Field(pattern=r"^RUN-\d{4}$")]


class OperationStatus(StrEnum):
    STARTED = "started"
    COMMITTED = "committed"
    FAILED = "failed"


class OperationRecord(PersistedModel):
    run_id: RunId
    operation: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    status: OperationStatus
    checkpoints: tuple[str, ...] = ()
    result_references: tuple[str, ...] = ()
