"""Locked, non-recycling sequence allocation."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path, PurePath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve

_APPLICATION_ID = re.compile(r"^APP-\d{4}-\d{4}$")
LocalIdKind = Literal["release", "submission"]


class _RegistryState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    application_sequences: dict[str, int] = Field(default_factory=dict)
    local_sequences: dict[str, dict[LocalIdKind, int]] = Field(default_factory=dict)
    run_sequence: int = Field(default=0, ge=0, le=9999)
    fact_sequence: int = Field(default=0, ge=0, le=9999)
    opportunity_sequences: dict[str, int] = Field(default_factory=dict)
    merge_sequence: int = Field(default=0, ge=0, le=9999)
    evaluation_sequence: int = Field(default=0, ge=0, le=9999)


class SequenceRegistry:
    def __init__(self, root: Path, *, lock_timeout: float = 10) -> None:
        self.root = root.resolve(strict=False)
        self.path = safe_resolve(root, PurePath("registry.json"))
        self.lock_timeout = lock_timeout

    def _run_id(self) -> str:
        return f"registry-{os.getpid()}-{uuid.uuid4().hex}"

    def _load(self) -> _RegistryState:
        try:
            payload = json.loads(self.path.read_text())
        except FileNotFoundError:
            return _RegistryState()
        except (OSError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Sequence registry is unreadable",
                {"path": str(self.path)},
            ) from error
        try:
            return _RegistryState.model_validate(payload)
        except ValidationError as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Sequence registry is invalid",
                {"path": str(self.path)},
            ) from error

    def allocate_application_id(self, year: int) -> str:
        if year < 1000 or year > 9999:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Application ID year must contain four digits",
                {"year": year},
            )
        with WorkspaceLock(
            self.root,
            run_id=self._run_id(),
            timeout=self.lock_timeout,
        ):
            state = self._load()
            key = str(year)
            number = state.application_sequences.get(key, 0) + 1
            if number > 9999:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Application ID sequence is exhausted for this year",
                    {"year": year},
                )
            application_sequences = dict(state.application_sequences)
            application_sequences[key] = number
            updated = state.model_copy(update={"application_sequences": application_sequences})
            atomic_write_json(self.path, updated)
        return f"APP-{year:04d}-{number:04d}"

    def allocate_run_id(self) -> str:
        with WorkspaceLock(
            self.root,
            run_id=self._run_id(),
            timeout=self.lock_timeout,
        ):
            state = self._load()
            number = state.run_sequence + 1
            if number > 9999:
                raise CareerError(ErrorCode.CONFLICT, "Run ID sequence is exhausted")
            atomic_write_json(self.path, state.model_copy(update={"run_sequence": number}))
        return f"RUN-{number:04d}"

    def allocate_fact_id(self) -> str:
        with WorkspaceLock(
            self.root,
            run_id=self._run_id(),
            timeout=self.lock_timeout,
        ):
            state = self._load()
            number = state.fact_sequence + 1
            if number > 9999:
                raise CareerError(ErrorCode.CONFLICT, "Fact ID sequence is exhausted")
            atomic_write_json(self.path, state.model_copy(update={"fact_sequence": number}))
        return f"FACT-{number:04d}"

    def allocate_opportunity_id(self, year: int) -> str:
        if year < 1000 or year > 9999:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Opportunity ID year must contain four digits",
                {"year": year},
            )
        with WorkspaceLock(
            self.root,
            run_id=self._run_id(),
            timeout=self.lock_timeout,
        ):
            state = self._load()
            key = str(year)
            number = state.opportunity_sequences.get(key, 0) + 1
            if number > 9999:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Opportunity ID sequence is exhausted for this year",
                    {"year": year},
                )
            sequences = dict(state.opportunity_sequences)
            sequences[key] = number
            atomic_write_json(
                self.path, state.model_copy(update={"opportunity_sequences": sequences})
            )
        return f"OPP-{year:04d}-{number:04d}"

    def allocate_merge_id(self) -> str:
        with WorkspaceLock(
            self.root,
            run_id=self._run_id(),
            timeout=self.lock_timeout,
        ):
            state = self._load()
            number = state.merge_sequence + 1
            if number > 9999:
                raise CareerError(ErrorCode.CONFLICT, "Merge ID sequence is exhausted")
            atomic_write_json(self.path, state.model_copy(update={"merge_sequence": number}))
        return f"MRG-{number:04d}"

    def allocate_evaluation_id(self) -> str:
        with WorkspaceLock(
            self.root,
            run_id=self._run_id(),
            timeout=self.lock_timeout,
        ):
            state = self._load()
            number = state.evaluation_sequence + 1
            if number > 9999:
                raise CareerError(ErrorCode.CONFLICT, "Evaluation ID sequence is exhausted")
            atomic_write_json(
                self.path,
                state.model_copy(update={"evaluation_sequence": number}),
            )
        return f"EVAL-{number:04d}"

    def allocate_local_id(self, application_id: str, kind: LocalIdKind) -> str:
        if _APPLICATION_ID.fullmatch(application_id) is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Invalid application ID for local sequence",
                {"application_id": application_id},
            )
        if kind not in {"release", "submission"}:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Unknown application-local sequence kind",
                {"kind": kind},
            )
        with WorkspaceLock(
            self.root,
            run_id=self._run_id(),
            timeout=self.lock_timeout,
        ):
            state = self._load()
            local_sequences = {key: dict(value) for key, value in state.local_sequences.items()}
            counters = local_sequences.setdefault(application_id, {})
            number = counters.get(kind, 0) + 1
            if number > 9999:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Application-local ID sequence is exhausted",
                    {"application_id": application_id, "kind": kind},
                )
            counters[kind] = number
            updated = state.model_copy(update={"local_sequences": local_sequences})
            atomic_write_json(self.path, updated)
        prefix = "REL" if kind == "release" else "SUB"
        return f"{prefix}-{number:04d}"
