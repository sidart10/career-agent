"""Submission attempt lifecycle and evidence-level truthfulness."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationManifest, ApplicationStage
from career_agent.models.base import UtcDateTime
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.models.submission import (
    EvidenceClaim,
    EvidenceLevel,
    SubmissionAttempt,
    SubmissionResolution,
    SubmissionStatus,
)
from career_agent.services.applications import ApplicationService
from career_agent.services.approvals import ApprovalService
from career_agent.services.payloads import PayloadService
from career_agent.storage.registry import SequenceRegistry
from career_agent.storage.repository import ApplicationRepository


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObservedEvidence(_ContractModel):
    claim_id: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    observed_at: UtcDateTime
    confidence: float = Field(ge=0, le=1)
    limitations: tuple[str, ...] = ()
    result: Literal["in_progress", "uncertain"]


class EmployerConfirmation(_ContractModel):
    claim_id: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    observed_at: UtcDateTime
    confidence: float = Field(ge=0, le=1)
    receipt_id: str | None = None
    echoed_field_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class BeginSubmissionRequest(_ContractModel):
    approval_id: str = Field(pattern=r"^APR-\d{4}$")
    observed_payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    browser_state_verified: bool
    browser_state_reference: str = Field(min_length=1)


class SubmissionService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.applications = ApplicationService(self.root)
        self.repository = ApplicationRepository(self.root)
        self.approvals = ApprovalService(self.root)
        self.payloads = PayloadService(self.root)
        self.registry = SequenceRegistry(self.root)

    def _return_to_review(
        self,
        application_id: str,
        reason: str,
        *,
        preparing: bool = False,
    ) -> None:
        application = self.applications.load(application_id)
        if application.stage is not ApplicationStage.APPROVED:
            return
        self.applications.transition(
            application_id,
            (ApplicationStage.PREPARING if preparing else ApplicationStage.READY_FOR_REVIEW),
            reason,
        )
        invalidated_at = datetime.now(UTC)
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="submission.invalidate-approval",
            idempotency_key=f"submission-invalidate-approval:{application_id}:{run_id}",
            status=OperationStatus.STARTED,
        )

        def record_invalidation(
            current: ApplicationManifest | None,
        ) -> ApplicationManifest:
            if current is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            return current.model_copy(
                update={
                    "approval_invalidated_at": invalidated_at,
                    "approval_invalidation_reason": reason,
                    "updated_at": invalidated_at,
                }
            )

        self.repository.mutate(application_id, operation, record_invalidation)

    @staticmethod
    def _find_attempt(
        application: ApplicationManifest,
        submission_id: str,
    ) -> tuple[int, SubmissionAttempt] | None:
        return next(
            (
                (index, attempt)
                for index, attempt in enumerate(application.attempts)
                if attempt.submission_id == submission_id
            ),
            None,
        )

    def begin(
        self,
        application_id: str,
        submission_id: str,
        approval_id: str,
        *,
        observed_payload_digest: str,
        browser_state_verified: bool,
        browser_state_reference: str,
        now: datetime | None = None,
    ) -> SubmissionAttempt:
        current_time = now or datetime.now(UTC)
        application = self.applications.load(application_id)
        existing = self._find_attempt(application, submission_id)
        if existing is not None:
            attempt = existing[1]
            if (
                attempt.approval_id != approval_id
                or attempt.payload_digest != observed_payload_digest
            ):
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Submission attempt is bound to different approval material",
                )
            consumption_path = self.approvals.consumption_path(
                application_id,
                submission_id,
                approval_id,
            )
            if not consumption_path.is_file():
                self.approvals.consume(
                    application_id,
                    submission_id,
                    approval_id,
                    consumed_at=current_time,
                )
            else:
                self.approvals.load_consumption(
                    application_id,
                    submission_id,
                    approval_id,
                )
            return attempt
        if application.stage is not ApplicationStage.APPROVED:
            raise CareerError(
                ErrorCode.NOT_READY,
                "Application must have a current trusted approval before submission",
                {"application_id": application_id},
            )
        if not browser_state_verified:
            self._return_to_review(
                application_id,
                "browser state could not be verified before submission",
            )
            raise CareerError(
                ErrorCode.NOT_READY,
                "Browser state must be verified immediately before submission",
            )
        try:
            payload = self.payloads.load(application_id, submission_id)
        except CareerError:
            self._return_to_review(
                application_id,
                "canonical submission payload became stale or invalid",
                preparing=True,
            )
            raise
        payload_digest = self.payloads.digest(payload)
        if observed_payload_digest != payload_digest:
            self._return_to_review(
                application_id,
                "observed portal payload changed after approval",
            )
            raise CareerError(
                ErrorCode.NOT_READY,
                "Observed browser payload differs from the approved payload",
            )
        try:
            approval = self.approvals.validate(
                application_id,
                submission_id,
                approval_id,
                now=current_time,
            )
        except CareerError:
            self._return_to_review(
                application_id,
                "submission approval is no longer valid",
            )
            raise
        if approval.payload_digest != payload_digest:
            raise CareerError(ErrorCode.NOT_READY, "Approval digest is stale")
        planned = EvidenceClaim(
            claim_id="planned-payload",
            claim_type="submission_payload",
            level=EvidenceLevel.PLANNED,
            source_reference=f"payload:sha256-v1:{payload_digest}",
            observed_at=current_time,
            value={
                "browser_state_reference": browser_state_reference,
                "field_ids": [field.field_id for field in payload.fields],
                "payload_digest": payload_digest,
            },
            confidence=1,
            limitations=payload.evidence_limitations,
        )
        attempt = SubmissionAttempt(
            submission_id=submission_id,
            status=SubmissionStatus.IN_PROGRESS,
            approval_id=approval_id,
            payload_digest=payload_digest,
            evidence=(planned,),
        )
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="submission.begin",
            idempotency_key=f"submission-begin:{application_id}:{submission_id}",
            status=OperationStatus.STARTED,
        )

        def append(current: ApplicationManifest | None) -> ApplicationManifest:
            if current is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            found = self._find_attempt(current, submission_id)
            if found is not None:
                if found[1] == attempt:
                    return current
                raise CareerError(ErrorCode.CONFLICT, "Submission attempt already exists")
            return current.model_copy(
                update={
                    "stage": ApplicationStage.APPLYING,
                    "submission_status": SubmissionStatus.IN_PROGRESS,
                    "attempts": (*current.attempts, attempt),
                    "updated_at": current_time,
                }
            )

        updated = self.repository.mutate(application_id, operation, append)
        self.approvals.consume(
            application_id,
            submission_id,
            approval_id,
            consumed_at=current_time,
        )
        persisted = self._find_attempt(updated, submission_id)
        if persisted is None:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Submission begin lost its persisted attempt",
            )
        return persisted[1]

    def observe(
        self,
        application_id: str,
        submission_id: str,
        evidence: ObservedEvidence,
    ) -> SubmissionAttempt:
        claim = EvidenceClaim(
            claim_id=evidence.claim_id,
            claim_type="portal_result",
            level=EvidenceLevel.OBSERVED,
            source_reference=evidence.source_reference,
            observed_at=evidence.observed_at,
            value={"result": evidence.result},
            confidence=evidence.confidence,
            limitations=evidence.limitations,
        )
        target_status = (
            SubmissionStatus.UNCERTAIN
            if evidence.result == "uncertain"
            else SubmissionStatus.IN_PROGRESS
        )
        return self._update_attempt(
            application_id,
            submission_id,
            claim=claim,
            status=target_status,
            resolution=None,
            stage=ApplicationStage.APPLYING,
            application_status=target_status,
            operation_name="observe",
        )

    def confirm(
        self,
        application_id: str,
        submission_id: str,
        evidence: EmployerConfirmation,
    ) -> SubmissionAttempt:
        application = self.applications.load(application_id)
        found = self._find_attempt(application, submission_id)
        if found is None:
            raise CareerError(ErrorCode.INVALID_INPUT, "Submission attempt does not exist")
        planned = next(
            (
                claim
                for claim in found[1].evidence
                if claim.level is EvidenceLevel.PLANNED and claim.claim_type == "submission_payload"
            ),
            None,
        )
        planned_value = planned.value if planned is not None else None
        field_ids = planned_value.get("field_ids") if isinstance(planned_value, dict) else None
        if not isinstance(field_ids, list) or not all(
            isinstance(field_id, str) for field_id in field_ids
        ):
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Submission attempt is missing its frozen reviewed field set",
            )
        reviewed_field_ids = set(field_ids)
        unknown_echoes = sorted(set(evidence.echoed_field_ids) - reviewed_field_ids)
        if unknown_echoes:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Employer confirmation echoes fields outside the reviewed payload",
                {"field_ids": unknown_echoes},
            )
        limitations = evidence.limitations
        if not evidence.echoed_field_ids and not limitations:
            limitations = ("employer confirmation did not echo submitted fields",)
        claim = EvidenceClaim(
            claim_id=evidence.claim_id,
            claim_type="employer_receipt",
            level=EvidenceLevel.EMPLOYER_CONFIRMED,
            source_reference=evidence.source_reference,
            observed_at=evidence.observed_at,
            value={
                "echoed_field_ids": list(evidence.echoed_field_ids),
                "receipt_id": evidence.receipt_id,
            },
            confidence=evidence.confidence,
            limitations=limitations,
        )
        return self._update_attempt(
            application_id,
            submission_id,
            claim=claim,
            status=SubmissionStatus.CONFIRMED,
            resolution=SubmissionResolution.CONFIRMED,
            stage=ApplicationStage.SUBMITTED,
            application_status=SubmissionStatus.CONFIRMED,
            operation_name="confirm",
        )

    def resolve_uncertain(
        self,
        application_id: str,
        submission_id: str,
        resolution: SubmissionResolution,
    ) -> SubmissionAttempt:
        application = self.applications.load(application_id)
        found = self._find_attempt(application, submission_id)
        if found is None or found[1].status is not SubmissionStatus.UNCERTAIN:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Only an uncertain submission attempt can be resolved",
            )
        if resolution is SubmissionResolution.CONFIRMED:
            if not any(
                item.level is EvidenceLevel.EMPLOYER_CONFIRMED for item in found[1].evidence
            ):
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Confirmed resolution requires employer confirmation evidence",
                )
            status = SubmissionStatus.CONFIRMED
            stage = ApplicationStage.SUBMITTED
            application_status = SubmissionStatus.CONFIRMED
        else:
            status = SubmissionStatus.UNCERTAIN
            stage = ApplicationStage.READY_FOR_REVIEW
            application_status = SubmissionStatus.NONE
        return self._update_attempt(
            application_id,
            submission_id,
            claim=None,
            status=status,
            resolution=resolution,
            stage=stage,
            application_status=application_status,
            operation_name=f"resolve-{resolution.value}",
        )

    def _update_attempt(
        self,
        application_id: str,
        submission_id: str,
        *,
        claim: EvidenceClaim | None,
        status: SubmissionStatus,
        resolution: SubmissionResolution | None,
        stage: ApplicationStage,
        application_status: SubmissionStatus,
        operation_name: str,
    ) -> SubmissionAttempt:
        now = datetime.now(UTC)
        run_id = self.registry.allocate_run_id()
        if claim is not None:
            claim_key = claim.claim_id
        elif resolution is not None:
            claim_key = resolution.value
        else:
            raise CareerError(ErrorCode.INVALID_INPUT, "Submission update has no identity")
        operation = OperationRecord(
            run_id=run_id,
            operation=f"submission.{operation_name}",
            idempotency_key=(
                f"submission-{operation_name}:{application_id}:{submission_id}:{claim_key}"
            ),
            status=OperationStatus.STARTED,
        )

        def update(current: ApplicationManifest | None) -> ApplicationManifest:
            if current is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            found = self._find_attempt(current, submission_id)
            if found is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Submission attempt does not exist")
            index, attempt = found
            if attempt.status is SubmissionStatus.CONFIRMED:
                if status is SubmissionStatus.CONFIRMED and resolution is attempt.resolution:
                    return current
                raise CareerError(ErrorCode.CONFLICT, "Confirmed submission is immutable")
            evidence = attempt.evidence
            if claim is not None:
                duplicate = next(
                    (item for item in evidence if item.claim_id == claim.claim_id),
                    None,
                )
                if duplicate is not None and duplicate != claim:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Evidence claim identity already contains different content",
                    )
                if duplicate is None:
                    evidence = (*evidence, claim)
            updated_attempt = attempt.model_copy(
                update={
                    "status": status,
                    "resolution": resolution,
                    "evidence": evidence,
                    "updated_at": now,
                }
            )
            attempts = list(current.attempts)
            attempts[index] = updated_attempt
            return current.model_copy(
                update={
                    "stage": stage,
                    "submission_status": application_status,
                    "attempts": tuple(attempts),
                    "updated_at": now,
                }
            )

        updated = self.repository.mutate(application_id, operation, update)
        found = self._find_attempt(updated, submission_id)
        if found is None:
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Submission update lost its attempt")
        return found[1]
