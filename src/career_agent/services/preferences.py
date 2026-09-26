"""Governed career goals kept separate from historical profile evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import PersistedModel
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry


class WeightedPriority(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    weight: int = Field(ge=1, le=5)


class PreferenceInput(BaseModel):
    """User-authored preferences; omitted optional fields are recorded as defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_roles: tuple[str, ...] = Field(min_length=1)
    seniority: tuple[str, ...] | None = None
    industries: tuple[str, ...] | None = None
    locations: tuple[str, ...] | None = None
    work_modes: tuple[Literal["onsite", "hybrid", "remote"], ...] | None = None
    relocation: Literal["unknown", "not_willing", "willing"] | None = None
    travel_max_percent: int | None = Field(default=None, ge=0, le=100)
    hard_exclusions: tuple[str, ...] | None = None
    weighted_priorities: tuple[WeightedPriority, ...] | None = None

    @model_validator(mode="after")
    def priorities_are_unique(self) -> PreferenceInput:
        names = [item.name.casefold() for item in self.weighted_priorities or ()]
        if len(names) != len(set(names)):
            raise ValueError("weighted priority names must be unique")
        return self


class PreferenceProfile(PersistedModel):
    target_roles: tuple[str, ...] = Field(min_length=1)
    seniority: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    work_modes: tuple[Literal["onsite", "hybrid", "remote"], ...] = ()
    relocation: Literal["unknown", "not_willing", "willing"] = "unknown"
    travel_max_percent: int | None = Field(default=None, ge=0, le=100)
    hard_exclusions: tuple[str, ...] = ()
    weighted_priorities: tuple[WeightedPriority, ...] = ()
    defaulted_fields: tuple[str, ...] = ()


class PreferenceService:
    _DEFAULTABLE = ("industries", "seniority")

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.path = safe_resolve(self.root, PurePath("profile", "preferences.json"))
        self.registry = SequenceRegistry(self.root)
        self.journal = OperationJournal(self.root)

    def load(self) -> PreferenceProfile | None:
        try:
            return PreferenceProfile.model_validate_json(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Career preferences are unreadable or invalid",
                {"path": str(self.path)},
            ) from error

    def set(self, request: PreferenceInput) -> PreferenceProfile:
        existing = self.load()
        defaulted = tuple(
            sorted(name for name in self._DEFAULTABLE if getattr(request, name) is None)
        )
        now = datetime.now(UTC)
        profile = PreferenceProfile(
            target_roles=request.target_roles,
            seniority=request.seniority or (),
            industries=request.industries or (),
            locations=request.locations or (),
            work_modes=request.work_modes or (),
            relocation=request.relocation or "unknown",
            travel_max_percent=request.travel_max_percent,
            hard_exclusions=request.hard_exclusions or (),
            weighted_priorities=request.weighted_priorities or (),
            defaulted_fields=defaulted,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        if existing is not None:
            unchanged = existing.model_dump(exclude={"updated_at"}) == profile.model_dump(
                exclude={"updated_at"}
            )
            if unchanged:
                return existing
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="preferences.set",
            idempotency_key="preferences:" + profile.model_dump_json(exclude={"updated_at"}),
            status=OperationStatus.STARTED,
        )
        with WorkspaceLock(self.root, run_id=run_id):
            self.journal.begin(operation)
            atomic_write_json(self.path, profile)
            self.journal.commit(
                run_id,
                {"result_references": [str(self.path)], "defaulted_fields": list(defaulted)},
            )
        return profile
