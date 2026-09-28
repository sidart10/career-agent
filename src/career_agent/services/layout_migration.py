"""Explicit, resumable format-2 migration; historical journals are never rewritten."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePath
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from career_agent.config import workspace_identity
from career_agent.errors import CareerError, ErrorCode
from career_agent.services.imports import ImportResult
from career_agent.services.profile import ProfileState
from career_agent.storage.atomic import atomic_write_bytes, atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve


def _encode(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()


Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class LayoutMigrationItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    path: str = Field(
        pattern=r"^(workspace\.json|profile/profile\.json|runs/RUN-[^/\\]+/import-result\.json)$"
    )
    before: Digest
    after: Digest


class LayoutMigrationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1]
    target_version: Literal[2]
    workspace_id: str = Field(min_length=1)
    former_root: str = Field(min_length=1)
    files: tuple[LayoutMigrationItem, ...] = Field(min_length=1)
    plan_digest: Digest

    @model_validator(mode="after")
    def marker_last(self) -> LayoutMigrationPlan:
        paths = [item.path for item in self.files]
        if paths[-1] != "workspace.json" or len(paths) != len(set(paths)):
            raise ValueError("Migration requires unique paths and the workspace marker last")
        return self


class LayoutMigrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1] = 1
    target_version: Literal[2] = 2
    workspace_id: str = Field(min_length=1)
    plan_digest: Digest
    backup_relative_path: str = Field(
        pattern=r"^maintenance/layout-migrations/[a-f0-9]{64}/backup$"
    )


class LayoutMigrationService:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = safe_resolve(self.root, PurePath("maintenance/layout-migrations"))

    def _path(self, digest: str, *parts: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise CareerError(ErrorCode.INVALID_INPUT, "Invalid migration digest")
        return safe_resolve(self.root, PurePath("maintenance/layout-migrations", digest, *parts))

    def has_plan(self, digest: str) -> bool:
        return self._path(digest, "plan.json").is_file()

    def _convert(self, relative: str, former: Path) -> bytes:
        path = safe_resolve(self.root, PurePath(relative))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if relative == "workspace.json":
                data["schema_version"] = 2
            else:
                for source in data.get("imported_sources", []):
                    for key, checksum_key in (
                        ("stored_path", "checksum"),
                        ("extracted_text_path", "normalized_text_checksum"),
                    ):
                        if not source.get(key):
                            continue
                        recorded = Path(source[key])
                        if recorded.is_absolute():
                            try:
                                recorded = recorded.relative_to(former)
                            except ValueError as error:
                                raise CareerError(
                                    ErrorCode.UNSAFE_PATH,
                                    "Legacy evidence path does not match the supplied former root",
                                ) from error
                        resolved = safe_resolve(self.root, PurePath(recorded))
                        if not resolved.is_file() or sha256_file(resolved) != source[checksum_key]:
                            raise CareerError(
                                ErrorCode.INTEGRITY_ERROR,
                                "Migration evidence checksum mismatch",
                                {"path": str(recorded)},
                            )
                        source[key] = recorded.as_posix()
                if relative == "profile/profile.json":
                    data["schema_version"] = 2
                    data.setdefault("rejected_proposals", {})
                    ProfileState.model_validate(data)
                else:
                    ImportResult.model_validate(data)
            return _encode(data)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR, "Invalid migration input", {"path": relative}
            ) from error

    def plan(self, former_root: Path | None = None) -> dict[str, Any]:
        identity = workspace_identity(self.root)
        if identity.schema_version != 1:
            raise CareerError(ErrorCode.CONFLICT, "Workspace already uses format 2")
        former = (former_root or self.root).expanduser().resolve()
        paths = [
            p.relative_to(self.root).as_posix()
            for p in sorted(self.root.glob("runs/RUN-*/import-result.json"))
        ]
        if (self.root / "profile/profile.json").exists():
            paths.append("profile/profile.json")
        paths.append("workspace.json")  # commit marker last
        files = [
            {
                "path": relative,
                "before": sha256_file(safe_resolve(self.root, PurePath(relative))),
                "after": hashlib.sha256(self._convert(relative, former)).hexdigest(),
            }
            for relative in paths
        ]
        material = {
            "schema_version": 1,
            "target_version": 2,
            "workspace_id": identity.workspace_id,
            "former_root": str(former),
            "files": files,
        }
        digest = hashlib.sha256(_encode(material)).hexdigest()
        plan = {**material, "plan_digest": digest}
        LayoutMigrationPlan.model_validate_json(_encode(plan))
        atomic_write_json(self._path(digest, "plan.json"), plan)
        return plan

    def apply(self, digest: str) -> dict[str, Any]:
        directory = self._path(digest)
        try:
            plan = LayoutMigrationPlan.model_validate_json(
                self._path(digest, "plan.json").read_text()
            ).model_dump(mode="json")
            material = {k: v for k, v in plan.items() if k != "plan_digest"}
            if (
                plan["plan_digest"] != digest
                or hashlib.sha256(_encode(material)).hexdigest() != digest
            ):
                raise ValueError("digest mismatch")
            if workspace_identity(self.root).workspace_id != plan["workspace_id"]:
                raise ValueError("workspace identity changed")
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Migration plan is missing, invalid, changed, or belongs to another workspace; "
                "preview again",
            ) from error
        with WorkspaceLock(self.root, run_id="layout-migration"):
            # Validate all destinations before writing any backup or replacing inputs.
            self._path(digest, "result.json")
            for item in plan["files"]:
                self._path(digest, "backup", item["path"])
                self._path(digest, "staged", item["path"])
            for item in plan["files"]:
                path = safe_resolve(self.root, PurePath(item["path"]))
                if sha256_file(path) not in {item["before"], item["after"]}:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Migration input changed; preview again",
                        {"path": item["path"]},
                    )
            # Stage and verify every backup before any replacement. On interruption,
            # the same digest accepts only known before/after bytes and resumes.
            for item in plan["files"]:
                path = safe_resolve(self.root, PurePath(item["path"]))
                backup = self._path(digest, "backup", item["path"])
                staged = self._path(digest, "staged", item["path"])
                if not backup.exists():
                    if sha256_file(path) != item["before"]:
                        raise CareerError(
                            ErrorCode.INTEGRITY_ERROR, "Migration backup missing after replacement"
                        )
                    atomic_write_bytes(backup, path.read_bytes())
                if sha256_file(backup) != item["before"]:
                    raise CareerError(
                        ErrorCode.INTEGRITY_ERROR, "Migration backup checksum mismatch"
                    )
                if not staged.exists():
                    atomic_write_bytes(
                        staged, self._convert(item["path"], Path(plan["former_root"]))
                    )
                if sha256_file(staged) != item["after"]:
                    raise CareerError(
                        ErrorCode.INTEGRITY_ERROR, "Migration staging checksum mismatch"
                    )
            for item in plan["files"]:
                path = safe_resolve(self.root, PurePath(item["path"]))
                staged = self._path(digest, "staged", item["path"])
                atomic_write_bytes(path, staged.read_bytes())
            result = LayoutMigrationResult(
                plan_digest=digest,
                workspace_id=plan["workspace_id"],
                backup_relative_path=(directory / "backup").relative_to(self.root).as_posix(),
            ).model_dump(mode="json")
            atomic_write_json(self._path(digest, "result.json"), result)
            return result
