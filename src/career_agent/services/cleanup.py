"""Digest-bound cleanup of disposable local run artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePath
from typing import Literal

from pydantic import Field, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import PersistedModel, UtcDateTime
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry

_RUN_ID = re.compile(r"^RUN-\d{4}$")


class CleanupItem(PersistedModel):
    relative_path: str = Field(pattern=r"^runs/RUN-\d{4}$")
    reason: Literal["committed_run", "expired_failed", "expired_orphan"]
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class CleanupPlan(PersistedModel):
    planned_at: UtcDateTime
    retention_days: int = Field(ge=1)
    items: tuple[CleanupItem, ...] = ()
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class CleanupResult(PersistedModel):
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    deleted_paths: tuple[str, ...]


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _tree_fingerprint(path: Path) -> str:
    if path.is_symlink() or not path.is_dir():
        raise CareerError(
            ErrorCode.UNSAFE_PATH,
            "Cleanup targets must be real managed run directories",
            {"path": str(path)},
        )
    material: list[dict[str, object]] = []
    for candidate in sorted(path.rglob("*")):
        if candidate.is_symlink():
            raise CareerError(
                ErrorCode.UNSAFE_PATH,
                "Cleanup does not plan directories containing symlinks",
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
            raise CareerError(
                ErrorCode.UNSAFE_PATH,
                "Cleanup encountered an unsupported filesystem entry",
                {"path": str(candidate)},
            )
    return _canonical_digest(material)


class CleanupService:
    def __init__(self, root: Path, *, retention: timedelta = timedelta(days=7)) -> None:
        self.root = root.resolve(strict=False)
        self.retention = retention
        self.runs = safe_resolve(self.root, PurePath("runs"))
        self.plans = safe_resolve(self.root, PurePath("maintenance", "cleanup-plans"))
        self.results = safe_resolve(self.root, PurePath("maintenance", "cleanup-results"))
        self.journal = OperationJournal(self.root)
        self.registry = SequenceRegistry(self.root)

    @staticmethod
    def _plan_material(
        planned_at: datetime,
        retention_days: int,
        items: tuple[CleanupItem, ...],
    ) -> dict[str, object]:
        return {
            "planned_at": planned_at.isoformat(),
            "retention_days": retention_days,
            "items": [
                {
                    "relative_path": item.relative_path,
                    "reason": item.reason,
                    "fingerprint": item.fingerprint,
                }
                for item in items
            ],
        }

    def plan(self, *, now: datetime | None = None) -> CleanupPlan:
        planned_at = (now or datetime.now(UTC)).astimezone(UTC)
        items: list[CleanupItem] = []
        if self.runs.is_dir():
            for path in sorted(self.runs.iterdir(), key=lambda item: item.name):
                if path.is_symlink() or not path.is_dir() or _RUN_ID.fullmatch(path.name) is None:
                    continue
                reason: (
                    Literal[
                        "committed_run",
                        "expired_failed",
                        "expired_orphan",
                    ]
                    | None
                ) = None
                try:
                    operation = self.journal.recover(path.name)
                except CareerError as error:
                    if error.code is not ErrorCode.INVALID_INPUT:
                        raise
                    modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
                    age = planned_at - modified_at
                    if timedelta(0) <= age and age >= self.retention:
                        reason = "expired_orphan"
                else:
                    if operation.status is OperationStatus.COMMITTED:
                        reason = "committed_run"
                    elif operation.status is OperationStatus.FAILED:
                        modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
                        age = planned_at - modified_at
                        if timedelta(0) <= age and age >= self.retention:
                            reason = "expired_failed"
                if reason is not None:
                    items.append(
                        CleanupItem(
                            relative_path=path.relative_to(self.root).as_posix(),
                            reason=reason,
                            fingerprint=_tree_fingerprint(path),
                        )
                    )
        item_tuple = tuple(items)
        retention_days = self.retention.days
        material = self._plan_material(planned_at, retention_days, item_tuple)
        digest = _canonical_digest(material)
        plan = CleanupPlan(
            planned_at=planned_at,
            retention_days=retention_days,
            items=item_tuple,
            plan_digest=digest,
            created_at=planned_at,
            updated_at=planned_at,
        )
        atomic_write_json(self.plans / f"{digest}.json", plan)
        return plan

    def _load_plan(self, plan_digest: str) -> CleanupPlan:
        path = self.plans / f"{plan_digest}.json"
        try:
            plan = CleanupPlan.model_validate_json(path.read_text())
        except FileNotFoundError as error:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Cleanup requires an existing unchanged preview digest",
                {"plan_digest": plan_digest},
            ) from error
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Cleanup plan is unreadable") from error
        material = self._plan_material(plan.planned_at, plan.retention_days, plan.items)
        if plan.plan_digest != plan_digest or _canonical_digest(material) != plan_digest:
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Cleanup plan digest is invalid")
        return plan

    def apply(self, plan_digest: str) -> CleanupResult:
        result_path = self.results / f"{plan_digest}.json"
        try:
            return CleanupResult.model_validate_json(result_path.read_text())
        except FileNotFoundError:
            pass
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Cleanup result is unreadable") from error
        plan = self._load_plan(plan_digest)
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="maintenance.cleanup",
            idempotency_key=f"cleanup-apply:{plan_digest}",
            status=OperationStatus.STARTED,
        )
        with WorkspaceLock(self.root, run_id=run_id):
            self.journal.begin(operation)
            targets: list[Path] = []
            for item in plan.items:
                target = safe_resolve(self.root, PurePath(item.relative_path))
                if target.parent != self.runs or target.is_symlink():
                    raise CareerError(ErrorCode.UNSAFE_PATH, "Cleanup target escaped runs")
                if not target.is_dir() or _tree_fingerprint(target) != item.fingerprint:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Cleanup scope changed after preview",
                        {"path": item.relative_path},
                    )
                targets.append(target)
            for target in targets:
                shutil.rmtree(target)
            result = CleanupResult(
                plan_digest=plan_digest,
                deleted_paths=tuple(item.relative_path for item in plan.items),
            )
            atomic_write_json(result_path, result)
            self.journal.commit(
                run_id,
                {
                    "plan_digest": plan_digest,
                    "result_references": list(result.deleted_paths),
                },
            )
        return result
