"""Conservative startup recovery for incomplete operation journals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationManifest
from career_agent.models.base import PersistedModel
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.paths import safe_resolve


class RecoveryQuarantine(PersistedModel):
    run_id: str = Field(pattern=r"^RUN-\d{4}$")
    operation: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    checkpoints: tuple[str, ...] = ()


class RecoveryReport(PersistedModel):
    recovered_run_ids: tuple[str, ...] = ()
    quarantined_run_ids: tuple[str, ...] = ()


class RecoveryPlan(BaseModel):
    """Read-only recovery classification bound to the current journal state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    recoverable_run_ids: tuple[str, ...] = ()
    quarantine_run_ids: tuple[str, ...] = ()
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class RecoveryService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.journal = OperationJournal(self.root)
        self.recovery_root = safe_resolve(
            self.root,
            PurePath("maintenance", "recovery"),
        )

    def _recoverable_manifest(
        self,
        operation: OperationRecord,
    ) -> tuple[ApplicationManifest, str] | None:
        prepared = self.journal.checkpoint_data(operation.run_id, "manifest-prepared")
        written = self.journal.checkpoint_data(operation.run_id, "manifest-written")
        if prepared is None or written is None:
            return None
        manifest_data = prepared.get("manifest")
        checksum = written.get("checksum")
        if not isinstance(manifest_data, dict) or not isinstance(checksum, str):
            return None
        try:
            manifest = ApplicationManifest.model_validate(manifest_data)
        except ValueError:
            return None
        allowed_operations = {
            "application.create",
            "application.rename-display",
            "application.transition",
            "application.add-event",
            "submission.begin",
            "submission.observe",
            "submission.confirm",
            "submission.resolve-confirmed",
            "submission.resolve-unsuccessful",
            "submission.invalidate-approval",
        }
        if operation.operation not in allowed_operations:
            return None
        if operation.operation == "application.create":
            if not operation.idempotency_key.startswith("application-create:"):
                return None
        elif manifest.application_id not in operation.idempotency_key:
            return None
        path = safe_resolve(
            self.root,
            PurePath("applications", manifest.application_id, "manifest.json"),
        )
        if not path.is_file() or sha256_file(path) != checksum:
            return None
        return manifest, checksum

    def _recover_manifest_write(self, operation: OperationRecord) -> bool:
        recoverable = self._recoverable_manifest(operation)
        if recoverable is None:
            return False
        manifest, checksum = recoverable
        self.journal.commit(
            operation.run_id,
            {
                "application_id": manifest.application_id,
                "manifest_checksum": checksum,
                "result_references": [manifest.application_id],
            },
        )
        return True

    @staticmethod
    def _plan_digest(recoverable: tuple[str, ...], quarantine: tuple[str, ...]) -> str:
        material = {
            "schema_version": 1,
            "recoverable_run_ids": list(recoverable),
            "quarantine_run_ids": list(quarantine),
        }
        return hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def plan(self) -> RecoveryPlan:
        """Classify incomplete operations without writing or repairing anything."""

        recoverable: list[str] = []
        quarantine: list[str] = []
        for operation in self.journal.operations():
            if operation.status in {OperationStatus.COMMITTED, OperationStatus.FAILED}:
                continue
            if self._recoverable_manifest(operation) is not None:
                recoverable.append(operation.run_id)
            else:
                quarantine.append(operation.run_id)
        recoverable_ids = tuple(sorted(recoverable))
        quarantine_ids = tuple(sorted(quarantine))
        return RecoveryPlan(
            recoverable_run_ids=recoverable_ids,
            quarantine_run_ids=quarantine_ids,
            plan_digest=self._plan_digest(recoverable_ids, quarantine_ids),
        )

    def _quarantine(self, operation: OperationRecord, reason: str) -> None:
        relative_path = f"maintenance/recovery/{operation.run_id}.json"
        atomic_write_json(
            self.recovery_root / f"{operation.run_id}.json",
            RecoveryQuarantine(
                run_id=operation.run_id,
                operation=operation.operation,
                reason=reason,
                checkpoints=operation.checkpoints,
            ),
        )
        self.journal.fail(
            operation.run_id,
            {"reason": reason, "quarantine_record": relative_path},
        )

    def apply(self, plan_digest: str) -> RecoveryReport:
        plan = self.plan()
        if plan.plan_digest != plan_digest:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Recovery scope changed after preview",
                {"expected_plan_digest": plan.plan_digest},
            )
        recovered: list[str] = []
        quarantined: list[str] = []
        for operation in self.journal.operations():
            if operation.status in {OperationStatus.COMMITTED, OperationStatus.FAILED}:
                continue
            if operation.run_id in plan.recoverable_run_ids and self._recover_manifest_write(
                operation
            ):
                recovered.append(operation.run_id)
                continue
            self._quarantine(
                operation,
                "automatic recovery could not prove a complete checksum-bound local write",
            )
            quarantined.append(operation.run_id)
        report = RecoveryReport(
            recovered_run_ids=tuple(sorted(recovered)),
            quarantined_run_ids=tuple(sorted(quarantined)),
        )
        atomic_write_json(self.recovery_root / "latest.json", report)
        return report

    def recover(self) -> RecoveryReport:
        """Compatibility helper for callers that already chose immediate recovery."""

        plan = self.plan()
        return self.apply(plan.plan_digest)
