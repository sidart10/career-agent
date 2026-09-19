"""Previewed, digest-bound local workspace reset operations."""

from __future__ import annotations

import hashlib
import json
import shutil
from enum import StrEnum
from pathlib import Path, PurePath
from typing import ClassVar

from pydantic import Field, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import PersistedModel
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry


class ResetScope(StrEnum):
    GENERATED_DRAFTS = "generated_drafts"
    TEMPORARY_FILES = "temporary_files"
    INTEGRATIONS = "integrations"
    IMPORTED_SOURCES = "imported_sources"
    RELEASES = "releases"
    SUBMISSION_EVIDENCE = "submission_evidence"
    ALL_PERSONAL_WORKSPACE_DATA = "all_personal_workspace_data"
    REMOTE_DATA = "remote_data"


class ResetItem(PersistedModel):
    relative_path: str = Field(min_length=1)
    kind: str = Field(pattern=r"^(file|directory)$")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResetPlan(PersistedModel):
    scopes: tuple[ResetScope, ...] = Field(min_length=1)
    items: tuple[ResetItem, ...] = ()
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResetResult(PersistedModel):
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    scopes: tuple[ResetScope, ...]
    deleted_paths: tuple[str, ...]


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _fingerprint(path: Path) -> tuple[str, str]:
    if path.is_symlink():
        raise CareerError(ErrorCode.UNSAFE_PATH, "Reset never follows or deletes symlink targets")
    if path.is_file():
        return "file", _canonical_digest(
            {"checksum": sha256_file(path), "size": path.stat().st_size, "type": "file"}
        )
    if not path.is_dir():
        raise CareerError(ErrorCode.UNSAFE_PATH, "Reset target is not a regular file or directory")
    material: list[dict[str, object]] = []
    for candidate in sorted(path.rglob("*")):
        if candidate.is_symlink():
            raise CareerError(
                ErrorCode.UNSAFE_PATH,
                "Reset refuses directories containing symlinks",
                {"path": str(candidate)},
            )
        relative = candidate.relative_to(path).as_posix()
        if candidate.is_dir():
            material.append({"path": relative, "type": "directory"})
        elif candidate.is_file():
            material.append(
                {
                    "path": relative,
                    "type": "file",
                    "checksum": sha256_file(candidate),
                    "size": candidate.stat().st_size,
                }
            )
        else:
            raise CareerError(ErrorCode.UNSAFE_PATH, "Reset found an unsupported entry")
    return "directory", _canonical_digest(material)


class ResetService:
    _PROTECTED: ClassVar[set[ResetScope]] = {
        ResetScope.IMPORTED_SOURCES,
        ResetScope.RELEASES,
        ResetScope.SUBMISSION_EVIDENCE,
    }

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.plans = safe_resolve(self.root, PurePath("maintenance", "reset-plans"))
        self.results = safe_resolve(self.root, PurePath("maintenance", "reset-results"))
        self.journal = OperationJournal(self.root)
        self.registry = SequenceRegistry(self.root)

    @staticmethod
    def _material(
        scopes: tuple[ResetScope, ...],
        items: tuple[ResetItem, ...],
    ) -> dict[str, object]:
        return {
            "scopes": [scope.value for scope in scopes],
            "items": [
                {
                    "relative_path": item.relative_path,
                    "kind": item.kind,
                    "fingerprint": item.fingerprint,
                }
                for item in items
            ],
        }

    def _candidate_paths(self, scope: ResetScope) -> tuple[Path, ...]:
        applications = self.root / "applications"
        if scope is ResetScope.GENERATED_DRAFTS:
            candidates = list(applications.glob("APP-*/drafts"))
            candidates.append(self.root / "pipeline.md")
            return tuple(candidates)
        if scope is ResetScope.TEMPORARY_FILES:
            return (self.root / "runs",)
        if scope is ResetScope.INTEGRATIONS:
            return (self.root / "integrations",)
        if scope is ResetScope.IMPORTED_SOURCES:
            return (self.root / "resources" / "imports",)
        if scope is ResetScope.RELEASES:
            return tuple(applications.glob("APP-*/releases"))
        if scope is ResetScope.SUBMISSION_EVIDENCE:
            return tuple(applications.glob("APP-*/submissions"))
        if scope is ResetScope.ALL_PERSONAL_WORKSPACE_DATA:
            return tuple(
                self.root / name
                for name in (
                    "profile",
                    "resources",
                    "opportunities",
                    "answers",
                    "applications",
                    "integrations",
                    "runs",
                    "journals",
                    "pipeline.md",
                )
            )
        return ()

    def plan(self, scopes: frozenset[ResetScope]) -> ResetPlan:
        if not scopes:
            raise CareerError(ErrorCode.INVALID_INPUT, "Reset requires at least one exact scope")
        if ResetScope.REMOTE_DATA in scopes:
            if len(scopes) != 1:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Remote deletion must use a separate reset plan",
                )
            raise CareerError(
                ErrorCode.APPROVAL_REQUIRED,
                "Remote deletion requires its integration-specific operation",
            )
        if ResetScope.ALL_PERSONAL_WORKSPACE_DATA in scopes and len(scopes) != 1:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "All-personal-data reset cannot be combined with another scope",
            )
        if len(scopes) > 1 and scopes & self._PROTECTED:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Protected history deletion requires a separate exact reset plan",
            )
        ordered_scopes = tuple(sorted(scopes, key=lambda scope: scope.value))
        if ordered_scopes == (ResetScope.ALL_PERSONAL_WORKSPACE_DATA,):
            (self.root / "journals").mkdir(parents=True, exist_ok=True)
        candidates = {
            candidate
            for scope in ordered_scopes
            for candidate in self._candidate_paths(scope)
            if candidate.exists() or candidate.is_symlink()
        }
        items: list[ResetItem] = []
        for candidate in sorted(candidates):
            if candidate.is_symlink():
                raise CareerError(
                    ErrorCode.UNSAFE_PATH,
                    "Reset refuses symlinked scope roots",
                    {"path": str(candidate)},
                )
            relative = candidate.relative_to(self.root)
            resolved = safe_resolve(self.root, PurePath(relative))
            kind, fingerprint = _fingerprint(resolved)
            items.append(
                ResetItem(
                    relative_path=resolved.relative_to(self.root).as_posix(),
                    kind=kind,
                    fingerprint=fingerprint,
                )
            )
        item_tuple = tuple(items)
        digest = _canonical_digest(self._material(ordered_scopes, item_tuple))
        plan = ResetPlan(scopes=ordered_scopes, items=item_tuple, plan_digest=digest)
        atomic_write_json(self.plans / f"{digest}.json", plan)
        return plan

    def _load_plan(self, plan_digest: str) -> ResetPlan:
        path = self.plans / f"{plan_digest}.json"
        try:
            plan = ResetPlan.model_validate_json(path.read_text())
        except FileNotFoundError as error:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Reset requires an existing unchanged preview digest",
                {"plan_digest": plan_digest},
            ) from error
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Reset plan is unreadable") from error
        if (
            plan.plan_digest != plan_digest
            or _canonical_digest(self._material(plan.scopes, plan.items)) != plan_digest
        ):
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Reset plan digest is invalid")
        return plan

    def apply(self, plan_digest: str) -> ResetResult:
        result_path = self.results / f"{plan_digest}.json"
        try:
            return ResetResult.model_validate_json(result_path.read_text())
        except FileNotFoundError:
            pass
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Reset result is unreadable") from error
        plan = self._load_plan(plan_digest)
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="maintenance.reset",
            idempotency_key=f"reset-apply:{plan_digest}",
            status=OperationStatus.STARTED,
        )
        with WorkspaceLock(self.root, run_id=run_id):
            targets: list[Path] = []
            for item in plan.items:
                target = safe_resolve(self.root, PurePath(item.relative_path))
                if target.is_symlink() or not target.exists():
                    raise CareerError(ErrorCode.CONFLICT, "Reset scope changed after preview")
                kind, fingerprint = _fingerprint(target)
                if kind != item.kind or fingerprint != item.fingerprint:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Reset scope changed after preview",
                        {"path": item.relative_path},
                    )
                targets.append(target)
            self.journal.begin(operation)
            terminal_full_reset = plan.scopes == (ResetScope.ALL_PERSONAL_WORKSPACE_DATA,)
            if terminal_full_reset:
                self.journal.commit(
                    run_id,
                    {
                        "plan_digest": plan_digest,
                        "result_references": [item.relative_path for item in plan.items],
                    },
                )
            for target in sorted(targets, key=lambda path: len(path.parts), reverse=True):
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            result = ResetResult(
                plan_digest=plan_digest,
                scopes=plan.scopes,
                deleted_paths=tuple(item.relative_path for item in plan.items),
            )
            atomic_write_json(result_path, result)
            if not terminal_full_reset:
                self.journal.commit(
                    run_id,
                    {
                        "plan_digest": plan_digest,
                        "result_references": list(result.deleted_paths),
                    },
                )
        return result
