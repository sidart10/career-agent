"""Conservative startup recovery for incomplete operation journals."""

from __future__ import annotations

from pathlib import Path, PurePath

from pydantic import Field

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


class RecoveryService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.journal = OperationJournal(self.root)
        self.recovery_root = safe_resolve(
            self.root,
            PurePath("maintenance", "recovery"),
        )

    def _recover_manifest_write(self, operation: OperationRecord) -> bool:
        prepared = self.journal.checkpoint_data(operation.run_id, "manifest-prepared")
        written = self.journal.checkpoint_data(operation.run_id, "manifest-written")
        if prepared is None or written is None:
            return False
        manifest_data = prepared.get("manifest")
        checksum = written.get("checksum")
        if not isinstance(manifest_data, dict) or not isinstance(checksum, str):
            return False
        try:
            manifest = ApplicationManifest.model_validate(manifest_data)
        except ValueError:
            return False
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
            return False
        if operation.operation == "application.create":
            if not operation.idempotency_key.startswith("application-create:"):
                return False
        elif manifest.application_id not in operation.idempotency_key:
            return False
        path = safe_resolve(
            self.root,
            PurePath("applications", manifest.application_id, "manifest.json"),
        )
        if not path.is_file() or sha256_file(path) != checksum:
            return False
        self.journal.commit(
            operation.run_id,
            {
                "application_id": manifest.application_id,
                "manifest_checksum": checksum,
                "result_references": [manifest.application_id],
            },
        )
        return True

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

    def recover(self) -> RecoveryReport:
        recovered: list[str] = []
        quarantined: list[str] = []
        for operation in self.journal.operations():
            if operation.status in {OperationStatus.COMMITTED, OperationStatus.FAILED}:
                continue
            if operation.operation.startswith("application.") and self._recover_manifest_write(
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
