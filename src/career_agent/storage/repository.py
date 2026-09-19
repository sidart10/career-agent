"""Transactional repositories for authoritative application manifests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path, PurePath

from pydantic import ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationManifest
from career_agent.models.operation import OperationRecord
from career_agent.state_machine import (
    InvalidTransition,
    InvalidWorkspaceState,
    validate_transition,
    validate_workspace_state,
)
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import ApplicationLock
from career_agent.storage.paths import safe_resolve

ManifestTransform = Callable[[ApplicationManifest | None], ApplicationManifest]


class ApplicationRepository:
    def __init__(self, root: Path, *, lock_timeout: float = 10) -> None:
        self.root = root.resolve(strict=False)
        self.lock_timeout = lock_timeout
        self.journal = OperationJournal(self.root, timeout=lock_timeout)

    def _path(self, application_id: str) -> Path:
        return safe_resolve(
            self.root,
            PurePath("applications", application_id, "manifest.json"),
        )

    def _load_optional(self, application_id: str) -> ApplicationManifest | None:
        path = self._path(application_id)
        try:
            payload = json.loads(path.read_text())
            manifest = ApplicationManifest.model_validate(payload)
            validate_workspace_state(manifest)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError, ValidationError, InvalidWorkspaceState) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Application manifest is unreadable or invalid",
                {"application_id": application_id},
            ) from error
        return manifest

    def load(self, application_id: str) -> ApplicationManifest:
        manifest = self._load_optional(application_id)
        if manifest is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Application manifest does not exist",
                {"application_id": application_id},
            )
        return manifest

    def create(
        self,
        manifest: ApplicationManifest,
        operation: OperationRecord,
    ) -> ApplicationManifest:
        def create_only(existing: ApplicationManifest | None) -> ApplicationManifest:
            if existing is not None:
                if existing == manifest:
                    return existing
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Application manifest already exists",
                    {"application_id": manifest.application_id},
                )
            return manifest

        return self.mutate(manifest.application_id, operation, create_only)

    def mutate(
        self,
        application_id: str,
        operation: OperationRecord,
        transform: ManifestTransform,
    ) -> ApplicationManifest:
        replay = self.journal.replay(operation.idempotency_key)
        if replay is not None:
            replayed_application = replay.result.get("application_id")
            if replayed_application != application_id:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Idempotency key belongs to another application",
                    {
                        "application_id": application_id,
                        "existing_application_id": replayed_application,
                    },
                )
            return self.load(application_id)

        active_operation = self.journal.operation_for_key(operation.idempotency_key) or operation
        self.journal.begin(active_operation)
        with ApplicationLock(
            self.root,
            application_id,
            run_id=active_operation.run_id,
            timeout=self.lock_timeout,
        ):
            prepared = self.journal.checkpoint_data(
                active_operation.run_id,
                "manifest-prepared",
            )
            if prepared is None:
                before = self._load_optional(application_id)
                candidate = transform(before)
                try:
                    manifest = ApplicationManifest.model_validate(candidate.model_dump(mode="json"))
                    if manifest.application_id != application_id:
                        raise InvalidTransition("application identity cannot change")
                    if before is None:
                        validate_workspace_state(manifest)
                    else:
                        validate_transition(before, manifest)
                except (ValidationError, InvalidTransition, InvalidWorkspaceState) as error:
                    raise CareerError(
                        ErrorCode.INVALID_INPUT,
                        "Application mutation violates its persisted contract",
                        {"application_id": application_id},
                    ) from error
                self.journal.checkpoint(
                    active_operation.run_id,
                    "manifest-prepared",
                    {"manifest": manifest.model_dump(mode="json")},
                )
            else:
                try:
                    manifest = ApplicationManifest.model_validate(prepared["manifest"])
                except (KeyError, ValidationError) as error:
                    raise CareerError(
                        ErrorCode.INTEGRITY_ERROR,
                        "Prepared application checkpoint is invalid",
                        {"run_id": active_operation.run_id},
                    ) from error
                if manifest.application_id != application_id:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Idempotency key belongs to another application",
                        {
                            "application_id": application_id,
                            "existing_application_id": manifest.application_id,
                        },
                    )

            path = self._path(application_id)
            atomic_write_json(path, manifest)
            checksum = sha256_file(path)
            self.journal.checkpoint(
                active_operation.run_id,
                "manifest-written",
                {"checksum": checksum},
            )
            self.journal.commit(
                active_operation.run_id,
                {
                    "application_id": application_id,
                    "manifest_checksum": checksum,
                    "result_references": [application_id],
                },
            )
            return manifest
