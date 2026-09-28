"""Governed acknowledgement for model-assisted processing of personal evidence."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path, PurePath

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import PersistedModel
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry

PRIVACY_POLICY_VERSION = "2026-09-26.v1"
DISCLOSURE = (
    "Career Agent stores authoritative workspace state locally as plaintext files, but "
    "model-assisted resume "
    "interpretation may send selected extracted text to the model provider configured in the "
    "agent host. Provider processing and retention are governed by that provider and host, not "
    "by Career Agent. Deterministic import can proceed without this acknowledgement."
)


class PrivacyStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str
    workspace_path: str
    disclosure: str
    acknowledged: bool
    provider: str | None = None
    acknowledged_at: datetime | None = None


class PrivacyAcknowledgement(PersistedModel):
    policy_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_processing_allowed: bool = True


class PrivacyService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.path = safe_resolve(self.root, PurePath("profile", "privacy.json"))
        self.registry = SequenceRegistry(self.root)
        self.journal = OperationJournal(self.root)

    def load(self) -> PrivacyAcknowledgement | None:
        try:
            return PrivacyAcknowledgement.model_validate_json(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Privacy acknowledgement is unreadable or invalid",
                {"path": str(self.path)},
            ) from error

    def status(self) -> PrivacyStatus:
        acknowledgement = self.load()
        current = (
            acknowledgement
            if acknowledgement is not None
            and acknowledgement.policy_version == PRIVACY_POLICY_VERSION
            and acknowledgement.model_processing_allowed
            and (
                not os.environ.get("CAREER_MODEL_PROVIDER")
                or acknowledgement.provider == os.environ["CAREER_MODEL_PROVIDER"]
            )
            else None
        )
        return PrivacyStatus(
            policy_version=PRIVACY_POLICY_VERSION,
            workspace_path=str(self.root),
            disclosure=DISCLOSURE,
            acknowledged=current is not None,
            provider=current.provider if current is not None else None,
            acknowledged_at=current.updated_at if current is not None else None,
        )

    def require_acknowledgement(self) -> PrivacyAcknowledgement:
        acknowledgement = self.load()
        if (
            acknowledgement is None
            or acknowledgement.policy_version != PRIVACY_POLICY_VERSION
            or not acknowledgement.model_processing_allowed
            or not self.status().acknowledged
        ):
            raise CareerError(
                ErrorCode.APPROVAL_REQUIRED,
                "Model-assisted interpretation requires the current privacy acknowledgement",
                {"policy_version": PRIVACY_POLICY_VERSION},
            )
        return acknowledgement

    def acknowledge(self, policy_version: str, provider: str) -> PrivacyAcknowledgement:
        if policy_version != PRIVACY_POLICY_VERSION:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Privacy policy version changed; review the current disclosure",
                {"current_policy_version": PRIVACY_POLICY_VERSION},
            )
        normalized_provider = provider.strip()
        if not normalized_provider:
            raise CareerError(ErrorCode.INVALID_INPUT, "Model provider must be identified")
        initial = self.load()
        already_acknowledged = (
            initial is not None
            and initial.policy_version == policy_version
            and initial.provider == normalized_provider
            and initial.model_processing_allowed
        )
        candidate_run = None if already_acknowledged else self.registry.allocate_run_id()
        with WorkspaceLock(self.root, run_id="privacy-acknowledge"):
            existing = self.load()
            # Complete an interrupted durable write before considering a new transition.
            for pending in self.journal.operations():
                if pending.operation != "privacy.acknowledge" or (
                    pending.status is not OperationStatus.STARTED
                ):
                    continue
                checkpoint = self.journal.checkpoint_data(pending.run_id, "acknowledgement")
                if (
                    checkpoint is not None
                    and existing is not None
                    and (checkpoint.get("value") == existing.model_dump(mode="json"))
                ):
                    self._commit_acknowledgement(pending.run_id, existing)
            if (
                existing is not None
                and existing.policy_version == policy_version
                and existing.provider == normalized_provider
                and existing.model_processing_allowed
            ):
                return existing
            transition = json.dumps(
                [
                    policy_version,
                    normalized_provider,
                    existing.model_dump(mode="json") if existing else None,
                ],
                sort_keys=True,
            )
            import hashlib

            key = "privacy-transition:" + hashlib.sha256(transition.encode()).hexdigest()
            operation = self.journal.operation_for_key(key)
            if operation is None:
                if candidate_run is None:
                    raise CareerError(ErrorCode.CONFLICT, "Consent changed concurrently; retry")
                operation = OperationRecord(
                    run_id=candidate_run,
                    operation="privacy.acknowledge",
                    idempotency_key=key,
                    status=OperationStatus.STARTED,
                )
            self.journal.begin(operation)
            checkpoint = self.journal.checkpoint_data(operation.run_id, "acknowledgement")
            if checkpoint is not None:
                acknowledgement = PrivacyAcknowledgement.model_validate(checkpoint["value"])
            else:
                now = datetime.now(UTC)
                acknowledgement = PrivacyAcknowledgement(
                    policy_version=policy_version,
                    provider=normalized_provider,
                    created_at=existing.created_at if existing is not None else now,
                    updated_at=now,
                )
                self.journal.checkpoint(
                    operation.run_id,
                    "acknowledgement",
                    {"value": acknowledgement.model_dump(mode="json")},
                )
            atomic_write_json(self.path, acknowledgement)
            self._commit_acknowledgement(operation.run_id, acknowledgement)
            return acknowledgement

    def _commit_acknowledgement(self, run_id: str, value: PrivacyAcknowledgement) -> None:
        self.journal.commit(
            run_id,
            {
                "policy_version": value.policy_version,
                "provider": value.provider,
                "result_references": ["profile/privacy.json"],
            },
        )
