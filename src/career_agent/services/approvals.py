"""Trusted approval persistence and payload binding."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePath

from pydantic import ValidationError

from career_agent.approval.authority import (
    ApprovalAttestation,
    ApprovalAuthority,
    ApprovalFieldSummary,
    ApprovalSummary,
)
from career_agent.errors import CareerError, ErrorCode
from career_agent.models.answer import RetentionClass
from career_agent.models.application import ApplicationStage
from career_agent.models.base import ApplicationId, PersistedModel, SubmissionId, UtcDateTime
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.models.submission import ApprovalRecord
from career_agent.services.applications import ApplicationService
from career_agent.services.opportunities import OpportunityService
from career_agent.services.payloads import PayloadService
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import ApplicationLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry


class ApprovalConsumption(PersistedModel):
    application_id: ApplicationId
    submission_id: SubmissionId
    approval_id: str
    nonce: str
    payload_digest: str
    consumed_at: UtcDateTime


class ApprovalService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.applications = ApplicationService(self.root)
        self.opportunities = OpportunityService(self.root)
        self.payloads = PayloadService(self.root)
        self.registry = SequenceRegistry(self.root)
        self.journal = OperationJournal(self.root)

    def path(self, application_id: str, submission_id: str, approval_id: str) -> Path:
        return safe_resolve(
            self.root,
            PurePath(
                "applications",
                application_id,
                "submissions",
                submission_id,
                "approvals",
                f"{approval_id}.json",
            ),
        )

    def consumption_path(
        self,
        application_id: str,
        submission_id: str,
        approval_id: str,
    ) -> Path:
        return self.path(application_id, submission_id, approval_id).with_suffix(".consumed.json")

    @staticmethod
    def _operation_key(
        application_id: str,
        submission_id: str,
        approval_id: str,
    ) -> str:
        return f"approval-create:{application_id}:{submission_id}:{approval_id}"

    def _summary(self, application_id: str, submission_id: str) -> ApprovalSummary:
        payload = self.payloads.load(application_id, submission_id)
        application = self.applications.load(application_id)
        opportunity = self.opportunities.get(application.opportunity_id)
        return ApprovalSummary(
            application_id=application_id,
            submission_id=submission_id,
            company=opportunity.company,
            role=opportunity.title,
            destination=payload.destination,
            artifact_filenames=tuple(item.filename for item in payload.artifacts),
            attachment_filenames=tuple(item.filename for item in payload.attachments),
            fields=tuple(
                ApprovalFieldSummary(
                    field_id=item.field_id,
                    value=item.value,
                    requires_final_review=item.requires_final_review,
                )
                for item in payload.fields
            ),
            high_risk_field_ids=tuple(
                item.field_id
                for item in payload.fields
                if item.retention_class in {RetentionClass.HIGH_RISK, RetentionClass.SENSITIVE}
            ),
            attestations=tuple(item.label for item in payload.attestations),
            anomalies=payload.anomalies,
            irreversible_action=payload.irreversible_action,
        )

    @staticmethod
    def _attestation_digest(attestation: ApprovalAttestation) -> str:
        encoded = json.dumps(
            attestation.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _ensure_approved_stage(self, application_id: str) -> None:
        application = self.applications.load(application_id)
        if application.stage is ApplicationStage.APPROVED:
            return
        if application.stage not in {
            ApplicationStage.READY_FOR_REVIEW,
            ApplicationStage.APPROVED,
        }:
            raise CareerError(
                ErrorCode.NOT_READY,
                "Application is not awaiting final approval",
                {"application_id": application_id, "stage": application.stage.value},
            )
        self.applications.transition(
            application_id,
            ApplicationStage.APPROVED,
            "trusted submission payload approval recorded",
        )

    def _existing(self, application_id: str, submission_id: str) -> ApprovalRecord | None:
        root = safe_resolve(
            self.root,
            PurePath(
                "applications",
                application_id,
                "submissions",
                submission_id,
                "approvals",
            ),
        )
        paths = sorted(root.glob("APR-*.json"))
        return self.load(application_id, submission_id, paths[-1].stem) if paths else None

    def approve(
        self,
        application_id: str,
        submission_id: str,
        authority: ApprovalAuthority,
        *,
        ttl: timedelta = timedelta(minutes=15),
        now: datetime | None = None,
    ) -> ApprovalRecord:
        current_time = now or datetime.now(UTC)
        if ttl <= timedelta(0):
            raise CareerError(ErrorCode.INVALID_INPUT, "Approval TTL must be positive")
        existing = self._existing(application_id, submission_id)
        if existing is not None and existing.expires_at > current_time:
            consumption_path = self.consumption_path(
                application_id,
                submission_id,
                existing.approval_id,
            )
            if consumption_path.is_file():
                self.load_consumption(
                    application_id,
                    submission_id,
                    existing.approval_id,
                )
            else:
                current_payload = self.payloads.load(application_id, submission_id)
                if existing.payload_digest != self.payloads.digest(current_payload):
                    raise CareerError(
                        ErrorCode.NOT_READY,
                        "Existing approval payload digest is stale",
                        {"approval_id": existing.approval_id},
                    )
                self._ensure_approved_stage(application_id)
                return existing
        application = self.applications.load(application_id)
        if application.stage not in {
            ApplicationStage.READY_FOR_REVIEW,
            ApplicationStage.APPROVED,
        }:
            raise CareerError(
                ErrorCode.NOT_READY,
                "Application is not awaiting final approval",
                {"application_id": application_id, "stage": application.stage.value},
            )
        payload = self.payloads.load(application_id, submission_id)
        payload_digest = self.payloads.digest(payload)
        nonce = secrets.token_urlsafe(18)
        summary = self._summary(application_id, submission_id)
        attestation = authority.request(summary, payload_digest, nonce)
        if attestation.payload_digest != payload_digest or attestation.nonce != nonce:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Approval authority did not attest the exact payload and nonce",
                {"submission_id": submission_id},
            )
        if attestation.approved_at > current_time + timedelta(minutes=1):
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Approval attestation timestamp is in the future",
            )
        approval_id = self.registry.allocate_approval_id()
        approval = ApprovalRecord(
            approval_id=approval_id,
            submission_id=submission_id,
            payload_digest=payload_digest,
            nonce=nonce,
            approving_actor=attestation.approving_actor,
            runtime_session=attestation.runtime_session,
            authority=attestation.authority,
            provenance_reference=attestation.provenance_reference,
            attestation_digest=self._attestation_digest(attestation),
            approved_at=attestation.approved_at,
            expires_at=attestation.approved_at + ttl,
        )
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="submission.approve",
            idempotency_key=self._operation_key(
                application_id,
                submission_id,
                approval_id,
            ),
            status=OperationStatus.STARTED,
        )
        self.journal.begin(operation)
        path = self.path(application_id, submission_id, approval_id)
        with ApplicationLock(self.root, application_id, run_id=run_id):
            atomic_write_json(path, approval)
            checksum = sha256_file(path)
            self.journal.checkpoint(
                run_id,
                "approval-written",
                {"checksum": checksum},
            )
        self.journal.commit(
            run_id,
            {
                "approval_id": approval_id,
                "approval_checksum": checksum,
                "result_references": [approval_id],
            },
        )
        self._ensure_approved_stage(application_id)
        return approval

    def load(
        self,
        application_id: str,
        submission_id: str,
        approval_id: str,
    ) -> ApprovalRecord:
        path = self.path(application_id, submission_id, approval_id)
        try:
            approval = ApprovalRecord.model_validate_json(path.read_text())
        except FileNotFoundError as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Approval record does not exist for this submission attempt",
                {"submission_id": submission_id, "approval_id": approval_id},
            ) from error
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Approval record is unreadable or invalid",
                {"submission_id": submission_id, "approval_id": approval_id},
            ) from error
        if approval.approval_id != approval_id or approval.submission_id != submission_id:
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Approval identity mismatch")
        operation_key = self._operation_key(application_id, submission_id, approval_id)
        replay = self.journal.replay(operation_key)
        checksum = sha256_file(path)
        if replay is None:
            active = self.journal.operation_for_key(operation_key)
            checkpoint = (
                self.journal.checkpoint_data(active.run_id, "approval-written")
                if active is not None
                else None
            )
            if active is None or checkpoint is None or checkpoint.get("checksum") != checksum:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Approval record has no valid journal seal",
                )
            self.journal.commit(
                active.run_id,
                {
                    "approval_id": approval_id,
                    "approval_checksum": checksum,
                    "result_references": [approval_id],
                },
            )
        elif replay.result.get("approval_checksum") != checksum:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Approval record does not match its journal seal",
            )
        return approval

    def validate(
        self,
        application_id: str,
        submission_id: str,
        approval_id: str,
        *,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        approval = self.load(application_id, submission_id, approval_id)
        payload = self.payloads.load(application_id, submission_id)
        current_time = now or datetime.now(UTC)
        if approval.payload_digest != self.payloads.digest(payload):
            raise CareerError(
                ErrorCode.NOT_READY,
                "Approval payload digest is stale",
                {"approval_id": approval_id},
            )
        if current_time >= approval.expires_at:
            raise CareerError(
                ErrorCode.NOT_READY,
                "Approval has expired",
                {"approval_id": approval_id},
            )
        if self.consumption_path(application_id, submission_id, approval_id).is_file():
            self.load_consumption(application_id, submission_id, approval_id)
            raise CareerError(
                ErrorCode.CONFLICT,
                "Approval nonce has already been consumed",
                {"approval_id": approval_id},
            )
        return approval

    def consume(
        self,
        application_id: str,
        submission_id: str,
        approval_id: str,
        *,
        consumed_at: datetime,
    ) -> ApprovalConsumption:
        approval = self.load(application_id, submission_id, approval_id)
        consumption = ApprovalConsumption(
            application_id=application_id,
            submission_id=submission_id,
            approval_id=approval_id,
            nonce=approval.nonce,
            payload_digest=approval.payload_digest,
            consumed_at=consumed_at,
        )
        path = self.consumption_path(application_id, submission_id, approval_id)
        if path.exists():
            existing = self.load_consumption(application_id, submission_id, approval_id)
            if (
                existing.application_id == consumption.application_id
                and existing.submission_id == consumption.submission_id
                and existing.approval_id == consumption.approval_id
                and existing.nonce == consumption.nonce
                and existing.payload_digest == consumption.payload_digest
            ):
                return existing
            raise CareerError(ErrorCode.CONFLICT, "Approval consumption record differs")
        run_id = self.registry.allocate_run_id()
        operation_key = f"approval-consume:{application_id}:{submission_id}:{approval_id}"
        operation = OperationRecord(
            run_id=run_id,
            operation="approval.consume",
            idempotency_key=operation_key,
            status=OperationStatus.STARTED,
        )
        self.journal.begin(operation)
        with ApplicationLock(self.root, application_id, run_id=run_id):
            atomic_write_json(path, consumption)
            checksum = sha256_file(path)
            self.journal.checkpoint(
                run_id,
                "consumption-written",
                {"checksum": checksum},
            )
        self.journal.commit(
            run_id,
            {
                "approval_id": approval_id,
                "consumption_checksum": checksum,
                "result_references": [approval_id],
            },
        )
        return consumption

    def load_consumption(
        self,
        application_id: str,
        submission_id: str,
        approval_id: str,
    ) -> ApprovalConsumption:
        path = self.consumption_path(application_id, submission_id, approval_id)
        try:
            consumption = ApprovalConsumption.model_validate_json(path.read_text())
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Approval consumption record is unreadable or invalid",
            ) from error
        operation_key = f"approval-consume:{application_id}:{submission_id}:{approval_id}"
        replay = self.journal.replay(operation_key)
        checksum = sha256_file(path)
        if replay is None:
            active = self.journal.operation_for_key(operation_key)
            checkpoint = (
                self.journal.checkpoint_data(active.run_id, "consumption-written")
                if active is not None
                else None
            )
            if active is None or checkpoint is None or checkpoint.get("checksum") != checksum:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Approval consumption does not match its journal seal",
                )
            self.journal.commit(
                active.run_id,
                {
                    "approval_id": approval_id,
                    "consumption_checksum": checksum,
                    "result_references": [approval_id],
                },
            )
        elif replay.result.get("consumption_checksum") != checksum:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Approval consumption does not match its journal seal",
            )
        return consumption
