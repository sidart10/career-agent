"""Risk-aware, journaled answer storage and scope-qualified reuse."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path, PurePath

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.answer import AnswerRecord, RetentionClass, ReusePolicy
from career_agent.models.base import PersistedModel, UtcDateTime
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.security.prohibited_values import reject_prohibited
from career_agent.security.redaction import REDACTED
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry


class AnswerResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNKNOWN = "unknown"


class QuestionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    wording: str = Field(min_length=1)
    question_id: str | None = None
    application_id: str | None = None
    jurisdiction: str | None = None
    scope: dict[str, str] = Field(default_factory=dict)
    at: UtcDateTime = Field(default_factory=lambda: datetime.now(UTC))


class AnswerResolution(PersistedModel):
    status: AnswerResolutionStatus
    question_id: str | None = None
    answer_id: str | None = None
    value: JsonValue | None = None
    reason: str
    requires_final_review: bool = False


class SetAnswerCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(min_length=1)
    value: JsonValue
    exact_user_response: JsonValue
    source_reference: str = Field(min_length=1)
    retention_class: RetentionClass
    reuse_policy: ReusePolicy
    confirmed_at: UtcDateTime
    expires_at: UtcDateTime | None = None
    scope: dict[str, str] = Field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    confirm_aliases: bool = False
    sensitive_retention_opt_in: bool = False
    allow_override: bool = False
    idempotency_key: str | None = None


class CompensationPeriod(StrEnum):
    HOURLY = "hourly"
    MONTHLY = "monthly"
    ANNUAL = "annual"


class CompensationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    currency: str = Field(pattern=r"^[A-Z]{3}$")
    period: CompensationPeriod
    minimum: Decimal = Field(ge=0)
    maximum: Decimal | None = Field(default=None, ge=0)
    location_context: str = Field(min_length=1)
    flexible: bool

    @model_validator(mode="after")
    def range_is_ordered(self) -> CompensationAnswer:
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("compensation maximum cannot be below minimum")
        return self


class AnswerAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    answer_id: str
    question_id: str
    action: str
    occurred_at: UtcDateTime
    affected_applications: tuple[str, ...] = ()


class HistoricalRepresentation(StrEnum):
    EXACT_VALUE = "exact_value"
    REDACTED_VALUE = "redacted_value"
    DIGEST = "digest"
    IDENTIFIER = "identifier"


class HistoricalReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str
    representation: HistoricalRepresentation


class DeletionPreview(PersistedModel):
    answer_id: str
    aliases: tuple[str, ...]
    surviving_references: tuple[HistoricalReference, ...]
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class DeletionResult(PersistedModel):
    answer_id: str
    deleted: bool
    surviving_references: tuple[HistoricalReference, ...]
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class AnswerState(PersistedModel):
    answers: tuple[AnswerRecord, ...] = ()
    audit_events: tuple[AnswerAuditEvent, ...] = ()
    idempotency_results: dict[str, str] = Field(default_factory=dict)
    deletion_results: tuple[DeletionResult, ...] = ()


_LOW_RISK_ALIASES = {
    "email": "contact.email",
    "e mail": "contact.email",
    "e mail address": "contact.email",
    "email address": "contact.email",
    "phone": "contact.phone",
    "phone number": "contact.phone",
    "mobile phone number": "contact.phone",
}

_HIGH_RISK_ALIASES = {
    "are you currently authorized to work in the united states": "authorization.current_us",
    "will you now or in the future require sponsorship": "sponsorship.future_us",
    "would you need relocation assistance": "relocation.assistance",
    "what are your annual salary expectations in usd": "compensation.expectation",
    "voluntary self identification of disability": "demographic.disability",
    "protected veteran status": "demographic.veteran",
    "have you ever been convicted of a crime": "legal.criminal_history",
}

_HIGH_RISK_PREFIXES = (
    "authorization.",
    "sponsorship.",
    "relocation.",
    "compensation.",
    "demographic.",
    "legal.",
)


def _normalized_wording(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _scope_key(question_id: str, scope: dict[str, str]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return question_id, tuple(sorted(scope.items()))


def _command_key(command: SetAnswerCommand) -> str:
    if command.idempotency_key:
        digest = hashlib.sha256(command.idempotency_key.encode()).hexdigest()
        return f"user:{digest}"
    payload = command.model_dump(mode="json", exclude={"idempotency_key"})
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"answer-set:{digest}"


class AnswerService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.path = safe_resolve(self.root, PurePath("answers", "state.json"))
        self.registry = SequenceRegistry(self.root)
        self.journal = OperationJournal(self.root)

    def load_state(self) -> AnswerState:
        try:
            return AnswerState.model_validate_json(self.path.read_text())
        except FileNotFoundError:
            return AnswerState()
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Answer state is unreadable or invalid",
                {"path": str(self.path)},
            ) from error

    @staticmethod
    def _answer(state: AnswerState, answer_id: str) -> AnswerRecord:
        answer = next((item for item in state.answers if item.answer_id == answer_id), None)
        if answer is None:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Answer state references a missing answer",
                {"answer_id": answer_id},
            )
        return answer

    @staticmethod
    def _matches_command(answer: AnswerRecord, command: SetAnswerCommand) -> bool:
        return (
            answer.question_id == command.question_id
            and answer.value == command.value
            and answer.exact_user_response == command.exact_user_response
            and answer.source_reference == command.source_reference
            and answer.retention_class is command.retention_class
            and answer.reuse_policy is command.reuse_policy
            and answer.confirmed_at == command.confirmed_at
            and answer.expires_at == command.expires_at
            and answer.scope == command.scope
            and answer.aliases == tuple(dict.fromkeys(command.aliases))
        )

    @staticmethod
    def _idempotent_answer(
        state: AnswerState,
        answer_id: str,
        command: SetAnswerCommand,
    ) -> AnswerRecord:
        answer = AnswerService._answer(state, answer_id)
        if not AnswerService._matches_command(answer, command):
            raise CareerError(
                ErrorCode.CONFLICT,
                "Idempotency key belongs to another answer command",
                {"existing_answer_id": answer_id},
            )
        return answer

    def _repair_set_commit(self, key: str, answer: AnswerRecord) -> None:
        operation_key = f"answer-set:{key}"
        if self.journal.replay(operation_key) is not None:
            return
        active = self.journal.operation_for_key(operation_key)
        if active is not None:
            self.journal.commit(
                active.run_id,
                {
                    "answer_id": answer.answer_id,
                    "result_references": [answer.answer_id],
                },
            )

    def set(self, command: SetAnswerCommand) -> AnswerRecord:
        reject_prohibited(command.question_id, command.value, command.exact_user_response)
        if command.question_id.startswith("narrative."):
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Employer-specific narratives belong to application drafts",
                {"question_id": command.question_id},
            )
        if command.retention_class is RetentionClass.PROHIBITED:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Prohibited answers cannot be persisted",
                {"question_id": command.question_id},
            )
        if (
            command.retention_class is RetentionClass.SENSITIVE
            and not command.sensitive_retention_opt_in
        ):
            raise CareerError(
                ErrorCode.APPROVAL_REQUIRED,
                "Sensitive answer retention requires explicit opt-in",
                {"question_id": command.question_id},
            )
        high_risk = command.question_id.startswith(_HIGH_RISK_PREFIXES)
        if high_risk and command.retention_class is RetentionClass.ORDINARY:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Known high-risk questions require a high-risk or contextual retention class",
                {"question_id": command.question_id},
            )
        if command.question_id.startswith("demographic.") and (
            command.retention_class is not RetentionClass.SENSITIVE
        ):
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Demographic answers require sensitive retention",
                {"question_id": command.question_id},
            )
        if command.question_id.startswith("compensation."):
            try:
                compensation = CompensationAnswer.model_validate(command.value)
            except ValidationError as error:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Compensation requires currency, period, range, location, and flexibility",
                    {"question_id": command.question_id},
                ) from error
            if (
                command.scope.get("currency") != compensation.currency
                or command.scope.get("period") != compensation.period.value
                or command.reuse_policy is ReusePolicy.STABLE
            ):
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Compensation scope and reuse policy must preserve its units",
                    {"question_id": command.question_id},
                )
        if high_risk and command.aliases and not command.confirm_aliases:
            raise CareerError(
                ErrorCode.APPROVAL_REQUIRED,
                "High-risk aliases require explicit confirmation",
                {"question_id": command.question_id},
            )
        required_scope: str | None = None
        if command.reuse_policy in {
            ReusePolicy.APPLICATION_ONLY,
            ReusePolicy.VERIFY_PER_APPLICATION,
        }:
            required_scope = "application_id"
        elif command.reuse_policy is ReusePolicy.VERIFY_PER_JURISDICTION:
            required_scope = "jurisdiction"
        if required_scope is not None and not command.scope.get(required_scope):
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Reuse policy requires its matching answer scope",
                {"question_id": command.question_id, "required_scope": required_scope},
            )
        if command.reuse_policy is ReusePolicy.EXPIRES_AFTER and command.expires_at is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Expiry-based reuse requires an explicit expiry",
                {"question_id": command.question_id},
            )
        key = _command_key(command)
        state = self.load_state()
        replayed_id = state.idempotency_results.get(key)
        if replayed_id is not None:
            replayed_answer = self._idempotent_answer(state, replayed_id, command)
            self._repair_set_commit(key, replayed_answer)
            return replayed_answer
        scope_key = _scope_key(command.question_id, command.scope)
        existing = next(
            (
                item
                for item in state.answers
                if _scope_key(item.question_id, item.scope) == scope_key
            ),
            None,
        )
        if existing is not None and existing.value != command.value and not command.allow_override:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Conflicting answer requires an explicit override classification",
                {"question_id": command.question_id, "answer_id": existing.answer_id},
            )
        operation_key = f"answer-set:{key}"
        active = self.journal.operation_for_key(operation_key)
        reserved_identity = (
            self.journal.checkpoint_data(active.run_id, "answer-identity")
            if active is not None
            else None
        )
        reserved_answer_id = (
            reserved_identity.get("answer_id") if reserved_identity is not None else None
        )
        if reserved_answer_id is not None and not isinstance(reserved_answer_id, str):
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Reserved answer identity is invalid",
                {"run_id": active.run_id if active is not None else None},
            )
        answer_id = (
            existing.answer_id
            if existing is not None
            else reserved_answer_id or self.registry.allocate_answer_id()
        )
        run_id = active.run_id if active is not None else self.registry.allocate_run_id()
        answer = AnswerRecord(
            answer_id=answer_id,
            question_id=command.question_id,
            value=command.value,
            exact_user_response=command.exact_user_response,
            source_reference=command.source_reference,
            retention_class=command.retention_class,
            reuse_policy=command.reuse_policy,
            confirmed_at=command.confirmed_at,
            expires_at=command.expires_at,
            scope=command.scope,
            aliases=tuple(dict.fromkeys(command.aliases)),
        )
        operation = OperationRecord(
            run_id=run_id,
            operation="answer.set",
            idempotency_key=operation_key,
            status=OperationStatus.STARTED,
        )
        active = active or operation
        with WorkspaceLock(self.root, run_id=active.run_id):
            locked = self.load_state()
            replayed_id = locked.idempotency_results.get(key)
            if replayed_id is not None:
                replayed_answer = self._idempotent_answer(locked, replayed_id, command)
                self._repair_set_commit(key, replayed_answer)
                return replayed_answer
            locked_existing = next(
                (
                    item
                    for item in locked.answers
                    if _scope_key(item.question_id, item.scope) == scope_key
                ),
                None,
            )
            if (
                locked_existing is not None
                and locked_existing.value != command.value
                and not command.allow_override
            ):
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Conflicting answer requires an explicit override classification",
                    {
                        "question_id": command.question_id,
                        "answer_id": locked_existing.answer_id,
                    },
                )
            if locked_existing is not None:
                answer = answer.model_copy(
                    update={
                        "answer_id": locked_existing.answer_id,
                        "created_at": locked_existing.created_at,
                    }
                )
            self.journal.begin(active)
            self.journal.checkpoint(
                active.run_id,
                "answer-identity",
                {"answer_id": answer.answer_id},
            )
            answers = tuple(
                answer if item.answer_id == answer.answer_id else item for item in locked.answers
            )
            if locked_existing is None:
                answers = (*answers, answer)
            results = dict(locked.idempotency_results)
            results[key] = answer.answer_id
            affected = tuple(
                value for name, value in command.scope.items() if name == "application_id"
            )
            event = AnswerAuditEvent(
                run_id=active.run_id,
                answer_id=answer.answer_id,
                question_id=answer.question_id,
                action="updated" if locked_existing is not None else "created",
                occurred_at=datetime.now(UTC),
                affected_applications=affected,
            )
            updated = locked.model_copy(
                update={
                    "answers": answers,
                    "audit_events": (*locked.audit_events, event),
                    "idempotency_results": results,
                    "updated_at": datetime.now(UTC),
                }
            )
            atomic_write_json(self.path, updated)
            self.journal.commit(
                active.run_id,
                {
                    "answer_id": answer.answer_id,
                    "result_references": [answer.answer_id],
                },
            )
        return answer

    def resolve(self, question: QuestionContext) -> AnswerResolution:
        normalized = _normalized_wording(question.wording)
        state = self.load_state()
        question_id = question.question_id
        alias_is_high_risk = False
        if question_id is None:
            question_id = _LOW_RISK_ALIASES.get(normalized)
            if question_id is None:
                question_id = _HIGH_RISK_ALIASES.get(normalized)
                alias_is_high_risk = question_id is not None
        if question_id is None:
            alias_answer = next(
                (
                    answer
                    for answer in state.answers
                    if normalized in {_normalized_wording(alias) for alias in answer.aliases}
                ),
                None,
            )
            if alias_answer is not None:
                question_id = alias_answer.question_id
                alias_is_high_risk = alias_answer.retention_class in {
                    RetentionClass.HIGH_RISK,
                    RetentionClass.SENSITIVE,
                }
        if question_id is None:
            return AnswerResolution(
                status=AnswerResolutionStatus.UNKNOWN,
                reason="No exact registered question or alias matched",
            )
        candidates = [answer for answer in state.answers if answer.question_id == question_id]
        if not candidates:
            return AnswerResolution(
                status=AnswerResolutionStatus.UNKNOWN,
                question_id=question_id,
                reason="No stored answer exists",
                requires_final_review=alias_is_high_risk,
            )
        answer = self._select_candidate(candidates, question)
        high_risk = alias_is_high_risk or answer.retention_class in {
            RetentionClass.HIGH_RISK,
            RetentionClass.SENSITIVE,
        }
        scope_matches = self._scope_matches(answer, question)
        expired = answer.expires_at is not None and answer.expires_at <= question.at
        if high_risk or not scope_matches or expired:
            return AnswerResolution(
                status=AnswerResolutionStatus.NEEDS_CONFIRMATION,
                question_id=question_id,
                answer_id=answer.answer_id,
                reason=(
                    "High-risk answer requires confirmation"
                    if high_risk
                    else "Stored answer scope or freshness does not match"
                ),
                requires_final_review=high_risk,
            )
        return AnswerResolution(
            status=AnswerResolutionStatus.RESOLVED,
            question_id=question_id,
            answer_id=answer.answer_id,
            value=answer.value,
            reason="Exact policy-qualified answer found",
        )

    @staticmethod
    def _view(answer: AnswerRecord, *, include_sensitive: bool) -> dict[str, object]:
        payload = answer.model_dump(mode="json")
        sensitive = answer.retention_class in {
            RetentionClass.HIGH_RISK,
            RetentionClass.SENSITIVE,
        }
        if sensitive and not include_sensitive:
            payload["value"] = REDACTED
        if not include_sensitive:
            payload["exact_user_response"] = REDACTED
        return payload

    def list(self) -> tuple[dict[str, object], ...]:
        return tuple(
            self._view(answer, include_sensitive=False) for answer in self.load_state().answers
        )

    def export(
        self,
        *,
        include_sensitive: bool = False,
        owner_confirmed: bool = False,
    ) -> tuple[dict[str, object], ...]:
        if include_sensitive and not owner_confirmed:
            raise CareerError(
                ErrorCode.APPROVAL_REQUIRED,
                "Exact sensitive export requires distinct owner confirmation",
            )
        return tuple(
            self._view(answer, include_sensitive=include_sensitive)
            for answer in self.load_state().answers
        )

    def _historical_references(self, answer: AnswerRecord) -> tuple[HistoricalReference, ...]:
        applications = safe_resolve(self.root, PurePath("applications"))
        encoded_value = json.dumps(answer.value, sort_keys=True, separators=(",", ":"))
        plain_value = answer.value if isinstance(answer.value, str) else None
        value_digest = hashlib.sha256(encoded_value.encode()).hexdigest()
        references: list[HistoricalReference] = []
        for path in sorted(applications.glob("APP-*/**/*.json")):
            try:
                content = path.read_text()
            except OSError as error:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Historical answer reference is unreadable",
                    {"path": str(path)},
                ) from error
            representation: HistoricalRepresentation | None = None
            if encoded_value in content or (plain_value is not None and plain_value in content):
                representation = HistoricalRepresentation.EXACT_VALUE
            elif value_digest in content:
                representation = HistoricalRepresentation.DIGEST
            elif REDACTED in content and answer.answer_id in content:
                representation = HistoricalRepresentation.REDACTED_VALUE
            elif answer.answer_id in content:
                representation = HistoricalRepresentation.IDENTIFIER
            if representation is not None:
                references.append(
                    HistoricalReference(
                        relative_path=path.relative_to(self.root).as_posix(),
                        representation=representation,
                    )
                )
        return tuple(references)

    @staticmethod
    def _preview_digest(
        answer: AnswerRecord,
        references: tuple[HistoricalReference, ...],
    ) -> str:
        answer_fingerprint = hashlib.sha256(
            json.dumps(
                answer.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        payload = {
            "answer_id": answer.answer_id,
            "answer_fingerprint": answer_fingerprint,
            "aliases": answer.aliases,
            "surviving_references": [reference.model_dump(mode="json") for reference in references],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def delete_preview(self, answer_id: str) -> DeletionPreview:
        state = self.load_state()
        answer = next((item for item in state.answers if item.answer_id == answer_id), None)
        if answer is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Answer does not exist",
                {"answer_id": answer_id},
            )
        references = self._historical_references(answer)
        return DeletionPreview(
            answer_id=answer_id,
            aliases=answer.aliases,
            surviving_references=references,
            preview_digest=self._preview_digest(answer, references),
        )

    def _repair_delete_commit(self, result: DeletionResult) -> None:
        operation_key = f"answer-delete:{result.answer_id}:{result.preview_digest}"
        if self.journal.replay(operation_key) is not None:
            return
        active = self.journal.operation_for_key(operation_key)
        if active is not None:
            self.journal.commit(
                active.run_id,
                {
                    "answer_id": result.answer_id,
                    "result_references": [result.answer_id],
                },
            )

    def delete(self, answer_id: str, preview_digest: str) -> DeletionResult:
        state = self.load_state()
        replayed = next(
            (
                result
                for result in state.deletion_results
                if result.preview_digest == preview_digest and result.answer_id == answer_id
            ),
            None,
        )
        if replayed is not None:
            self._repair_delete_commit(replayed)
            return replayed
        preview = self.delete_preview(answer_id)
        if preview.preview_digest != preview_digest:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Deletion preview is stale or does not match",
                {"answer_id": answer_id},
            )
        run_id = self.registry.allocate_run_id()
        operation_key = f"answer-delete:{answer_id}:{preview_digest}"
        operation = OperationRecord(
            run_id=run_id,
            operation="answer.delete",
            idempotency_key=operation_key,
            status=OperationStatus.STARTED,
        )
        active = self.journal.operation_for_key(operation_key) or operation
        with WorkspaceLock(self.root, run_id=active.run_id):
            locked = self.load_state()
            replayed = next(
                (
                    item
                    for item in locked.deletion_results
                    if item.preview_digest == preview_digest and item.answer_id == answer_id
                ),
                None,
            )
            if replayed is not None:
                self._repair_delete_commit(replayed)
                return replayed
            answer = next(
                (item for item in locked.answers if item.answer_id == answer_id),
                None,
            )
            if answer is None:
                raise CareerError(ErrorCode.CONFLICT, "Answer was already deleted")
            current_references = self._historical_references(answer)
            if self._preview_digest(answer, current_references) != preview_digest:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Deletion preview is stale or does not match",
                    {"answer_id": answer_id},
                )
            self.journal.begin(active)
            result = DeletionResult(
                answer_id=answer_id,
                deleted=True,
                surviving_references=current_references,
                preview_digest=preview_digest,
            )
            retained_results = {
                key: value
                for key, value in locked.idempotency_results.items()
                if value != answer_id
            }
            event = AnswerAuditEvent(
                run_id=active.run_id,
                answer_id=answer_id,
                question_id=answer.question_id,
                action="deleted",
                occurred_at=datetime.now(UTC),
            )
            updated = locked.model_copy(
                update={
                    "answers": tuple(
                        item for item in locked.answers if item.answer_id != answer_id
                    ),
                    "audit_events": (*locked.audit_events, event),
                    "idempotency_results": retained_results,
                    "deletion_results": (*locked.deletion_results, result),
                    "updated_at": datetime.now(UTC),
                }
            )
            atomic_write_json(self.path, updated)
            self.journal.commit(
                active.run_id,
                {"answer_id": answer_id, "result_references": [answer_id]},
            )
        return result

    @staticmethod
    def _select_candidate(
        candidates: Sequence[AnswerRecord],
        question: QuestionContext,
    ) -> AnswerRecord:
        matching = [
            answer for answer in candidates if AnswerService._scope_matches(answer, question)
        ]
        if matching:
            return max(matching, key=lambda answer: len(answer.scope))
        return candidates[0]

    @staticmethod
    def _scope_matches(answer: AnswerRecord, question: QuestionContext) -> bool:
        context_scope = dict(question.scope)
        if question.application_id is not None:
            context_scope["application_id"] = question.application_id
        if question.jurisdiction is not None:
            context_scope["jurisdiction"] = question.jurisdiction
        if answer.retention_class is RetentionClass.CONTEXTUAL:
            return answer.scope == context_scope
        if answer.reuse_policy is ReusePolicy.VERIFY_PER_JURISDICTION:
            return answer.scope.get("jurisdiction") == question.jurisdiction
        if answer.reuse_policy in {
            ReusePolicy.VERIFY_PER_APPLICATION,
            ReusePolicy.APPLICATION_ONLY,
        }:
            return answer.scope.get("application_id") == question.application_id
        return True
