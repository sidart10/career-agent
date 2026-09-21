"""Copy-first, previewed schema migration foundations."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePath

from pydantic import BaseModel, Field, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationManifest
from career_agent.models.base import PersistedModel
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.services.applications import ApplicationIndex
from career_agent.services.opportunities import OpportunityState
from career_agent.storage.atomic import atomic_write_bytes, atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry

_DATE_DIRECTORY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class MigrationFile(PersistedModel):
    relative_path: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_version: int = Field(ge=0)


class MigrationFinding(PersistedModel):
    relative_path: str = Field(min_length=1)
    classification: str = Field(min_length=1)
    disposition: str = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class MigrationPlan(PersistedModel):
    target_version: int = Field(ge=1)
    files: tuple[MigrationFile, ...]
    findings: tuple[MigrationFinding, ...] = ()
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class MigrationBackupManifest(PersistedModel):
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    files: tuple[MigrationFile, ...]


class MigrationResult(PersistedModel):
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    backup_relative_path: str = Field(min_length=1)
    migrated_paths: tuple[str, ...]
    preserved_legacy_paths: tuple[str, ...]


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class MigrationService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.maintenance = safe_resolve(self.root, PurePath("maintenance"))
        self.plans = self.maintenance / "migration-plans"
        self.backups = self.maintenance / "migration-backups"
        self.staging = self.maintenance / "migration-staging"
        self.results = self.maintenance / "migration-results"
        self.journal = OperationJournal(self.root)
        self.registry = SequenceRegistry(self.root)

    def _governed_json_paths(self) -> tuple[Path, ...]:
        excluded_roots = {"legacy", "maintenance", "runs", ".locks"}
        return tuple(
            path
            for path in sorted(self.root.rglob("*.json"))
            if path.is_file()
            and not path.is_symlink()
            and path.relative_to(self.root).parts[0] not in excluded_roots
            and path.name != "registry.json"
        )

    @staticmethod
    def _file_material(files: tuple[MigrationFile, ...]) -> list[dict[str, object]]:
        return [
            {
                "relative_path": item.relative_path,
                "checksum": item.checksum,
                "source_version": item.source_version,
            }
            for item in files
        ]

    @staticmethod
    def _finding_material(
        findings: tuple[MigrationFinding, ...],
    ) -> list[dict[str, object]]:
        return [
            {
                "relative_path": item.relative_path,
                "classification": item.classification,
                "disposition": item.disposition,
                "fingerprint": item.fingerprint,
            }
            for item in findings
        ]

    @classmethod
    def _material(
        cls,
        target_version: int,
        files: tuple[MigrationFile, ...],
        findings: tuple[MigrationFinding, ...],
    ) -> dict[str, object]:
        return {
            "target_version": target_version,
            "files": cls._file_material(files),
            "findings": cls._finding_material(findings),
        }

    def _legacy_findings(self) -> tuple[MigrationFinding, ...]:
        legacy = self.root / "legacy"
        if not legacy.is_dir() or legacy.is_symlink():
            return ()
        paths = tuple(path for path in sorted(legacy.rglob("*")) if not path.is_symlink())
        findings: list[MigrationFinding] = []

        def add(path: Path, classification: str, disposition: str) -> None:
            fingerprint = (
                sha256_file(path)
                if path.is_file()
                else _digest(
                    [child.relative_to(path).as_posix() for child in sorted(path.rglob("*"))]
                )
            )
            findings.append(
                MigrationFinding(
                    relative_path=path.relative_to(self.root).as_posix(),
                    classification=classification,
                    disposition=disposition,
                    fingerprint=fingerprint,
                )
            )

        for path in paths:
            name = path.name.casefold()
            if path.is_dir() and "shared" in name and "resume" in name:
                add(path, "shared_resume_folder", "preserve_for_explicit_import")
            if path.is_file() and "final" in path.stem.casefold():
                add(path, "duplicate_final_candidate", "preserve_without_guessing_canonical")
            if any(_DATE_DIRECTORY.fullmatch(part) for part in path.parts):
                add(path, "date_based_application", "preserve_date_as_legacy_metadata")
            if (
                path.is_dir()
                and path.name.casefold() == "application"
                and not (path / "manifest.json").is_file()
            ):
                add(path, "missing_manifest", "quarantine_for_human_mapping")
            if path.is_file() and path.suffix.casefold() in {".aux", ".log", ".out", ".toc"}:
                add(path, "temporary_latex", "exclude_from_canonical_migration")
            if path.is_file() and path.suffix.casefold() in {".csv", ".json"}:
                peer_suffix = ".json" if path.suffix.casefold() == ".csv" else ".csv"
                if path.with_suffix(peer_suffix).is_file():
                    add(path, "competing_csv_json", "preserve_both_sources")
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8").casefold()
                except (OSError, UnicodeDecodeError):
                    content = ""
                if "uncertain" in content:
                    add(path, "uncertain_submission", "preserve_uncertainty")
            if path.is_file() and "google-sheet" in name:
                add(path, "google_sheet_metadata", "preserve_as_inert_legacy_metadata")
        unique = {(item.relative_path, item.classification): item for item in findings}
        return tuple(unique[key] for key in sorted(unique))

    def plan(self, *, target_version: int) -> MigrationPlan:
        if target_version != 1:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Only the declared schema version 1 migration target is supported",
                {"target_version": target_version},
            )
        files: list[MigrationFile] = []
        for path in self._governed_json_paths():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Governed JSON is unreadable during migration planning",
                    {"path": path.relative_to(self.root).as_posix()},
                ) from error
            if not isinstance(raw, dict) or not isinstance(raw.get("schema_version"), int):
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Governed JSON has no integer schema version",
                    {"path": path.relative_to(self.root).as_posix()},
                )
            source_version = raw["schema_version"]
            if source_version > target_version:
                raise CareerError(ErrorCode.NOT_READY, "Workspace schema is newer than this CLI")
            files.append(
                MigrationFile(
                    relative_path=path.relative_to(self.root).as_posix(),
                    checksum=sha256_file(path),
                    source_version=source_version,
                )
            )
        file_tuple = tuple(files)
        findings = self._legacy_findings()
        digest = _digest(self._material(target_version, file_tuple, findings))
        plan = MigrationPlan(
            target_version=target_version,
            files=file_tuple,
            findings=findings,
            plan_digest=digest,
        )
        atomic_write_json(self.plans / f"{digest}.json", plan)
        return plan

    def _load_plan(self, plan_digest: str) -> MigrationPlan:
        path = self.plans / f"{plan_digest}.json"
        try:
            plan = MigrationPlan.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Migration requires an existing unchanged plan digest",
            ) from error
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Migration plan is unreadable") from error
        if (
            plan.plan_digest != plan_digest
            or _digest(self._material(plan.target_version, plan.files, plan.findings))
            != plan_digest
        ):
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Migration plan digest is invalid")
        return plan

    def _validate_staged(self, relative_path: str, payload: dict[str, object]) -> None:
        model: type[BaseModel] | None = None
        if relative_path == "applications/index.json":
            model = ApplicationIndex
        elif relative_path == "opportunities/state.json":
            model = OpportunityState
        elif re.fullmatch(r"applications/APP-\d{4}-\d{4}/manifest\.json", relative_path):
            model = ApplicationManifest
        try:
            if model is not None:
                model.model_validate(payload)
            elif payload.get("schema_version") != 1:
                raise ValueError("staged schema version is not 1")
        except (ValidationError, ValueError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Staged migration output failed schema validation",
                {"path": relative_path},
            ) from error

    def apply(self, plan_digest: str) -> MigrationResult:
        result_path = self.results / f"{plan_digest}.json"
        try:
            return MigrationResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            pass
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Migration result is unreadable",
            ) from error
        plan = self._load_plan(plan_digest)
        current = self._governed_json_paths()
        current_relative = tuple(path.relative_to(self.root).as_posix() for path in current)
        planned_relative = tuple(item.relative_path for item in plan.files)
        if current_relative != planned_relative:
            raise CareerError(ErrorCode.CONFLICT, "Migration file scope changed after planning")
        for item in plan.files:
            path = safe_resolve(self.root, PurePath(item.relative_path))
            if not path.is_file() or sha256_file(path) != item.checksum:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Migration input changed after planning",
                    {"path": item.relative_path},
                )
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="maintenance.migrate",
            idempotency_key=f"migration-apply:{plan_digest}",
            status=OperationStatus.STARTED,
        )
        backup_root = self.backups / plan_digest
        staging_root = self.staging / plan_digest
        with WorkspaceLock(self.root, run_id=run_id):
            self.journal.begin(operation)
            for item in plan.files:
                source = safe_resolve(self.root, PurePath(item.relative_path))
                atomic_write_bytes(backup_root / item.relative_path, source.read_bytes())
                try:
                    payload = json.loads(source.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise CareerError(
                        ErrorCode.INTEGRITY_ERROR,
                        "Migration source is invalid",
                    ) from error
                if not isinstance(payload, dict):
                    raise CareerError(
                        ErrorCode.INTEGRITY_ERROR,
                        "Migration source must be an object",
                    )
                payload["schema_version"] = plan.target_version
                self._validate_staged(item.relative_path, payload)
                atomic_write_json(staging_root / item.relative_path, payload)
            backup_manifest = MigrationBackupManifest(
                plan_digest=plan_digest,
                files=plan.files,
            )
            atomic_write_json(backup_root / "backup-manifest.json", backup_manifest)
            for item in backup_manifest.files:
                backup = backup_root / item.relative_path
                if not backup.is_file() or sha256_file(backup) != item.checksum:
                    raise CareerError(
                        ErrorCode.INTEGRITY_ERROR,
                        "Migration backup verification failed before replacement",
                        {"path": item.relative_path},
                    )
            try:
                for item in plan.files:
                    staged = staging_root / item.relative_path
                    target = safe_resolve(self.root, PurePath(item.relative_path))
                    atomic_write_bytes(target, staged.read_bytes())
            except BaseException:
                for item in plan.files:
                    backup = backup_root / item.relative_path
                    target = safe_resolve(self.root, PurePath(item.relative_path))
                    atomic_write_bytes(target, backup.read_bytes())
                raise
            result = MigrationResult(
                plan_digest=plan_digest,
                backup_relative_path=backup_root.relative_to(self.root).as_posix(),
                migrated_paths=tuple(item.relative_path for item in plan.files),
                preserved_legacy_paths=tuple(
                    sorted({finding.relative_path for finding in plan.findings})
                ),
            )
            atomic_write_json(result_path, result)
            self.journal.commit(
                run_id,
                {
                    "plan_digest": plan_digest,
                    "backup": result.backup_relative_path,
                    "result_references": list(result.migrated_paths),
                },
            )
        return result
