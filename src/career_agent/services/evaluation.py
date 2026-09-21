"""Schema-validated, evidence-backed opportunity evaluation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path, PurePath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import PersistedModel
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.services.opportunities import OpportunityService
from career_agent.services.profile import ProfileService
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry

EvaluationId = Annotated[str, Field(pattern=r"^EVAL-\d{4}$")]


class EvaluationMode(StrEnum):
    PRELIMINARY = "preliminary"
    AUTHORITATIVE = "authoritative"


class EvidenceSource(StrEnum):
    POSTING = "posting"
    PROFILE = "profile"


class _EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceReference(_EvaluationModel):
    source: EvidenceSource
    reference_id: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def posting_evidence_has_span(self) -> EvidenceReference:
        if self.source is EvidenceSource.POSTING:
            if self.start is None or self.end is None or self.end <= self.start:
                raise ValueError("posting evidence requires a valid character span")
        elif self.start is not None or self.end is not None:
            raise ValueError("profile evidence does not use posting spans")
        return self


class ConstraintFinding(_EvaluationModel):
    name: str = Field(min_length=1)
    satisfied: bool
    evidence: tuple[EvidenceReference, ...] = ()


class PreferenceFinding(_EvaluationModel):
    name: str = Field(min_length=1)
    weight: Decimal = Field(gt=0)
    rating: Decimal = Field(ge=0, le=1)
    evidence: tuple[EvidenceReference, ...] = ()


class EvaluationDraft(_EvaluationModel):
    mode: EvaluationMode
    hard_constraints: tuple[ConstraintFinding, ...] = ()
    weighted_preferences: tuple[PreferenceFinding, ...] = ()
    supporting_evidence: tuple[EvidenceReference, ...] = ()
    opposing_evidence: tuple[EvidenceReference, ...] = ()


class FitEvaluation(PersistedModel):
    evaluation_id: EvaluationId
    opportunity_id: str
    mode: EvaluationMode
    hard_constraints: tuple[ConstraintFinding, ...]
    weighted_preferences: tuple[PreferenceFinding, ...]
    supporting_evidence: tuple[EvidenceReference, ...]
    opposing_evidence: tuple[EvidenceReference, ...]
    score: Decimal = Field(ge=0, le=100)
    recommendation: Literal["pursue", "review", "dismiss"]


class EvaluationState(PersistedModel):
    evaluations: tuple[FitEvaluation, ...] = ()
    idempotency_results: dict[str, str] = Field(default_factory=dict)


def _all_evidence(draft: EvaluationDraft) -> Iterable[EvidenceReference]:
    yield from draft.supporting_evidence
    yield from draft.opposing_evidence
    for constraint in draft.hard_constraints:
        yield from constraint.evidence
    for preference in draft.weighted_preferences:
        yield from preference.evidence


class EvaluationService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.path = safe_resolve(
            self.root,
            PurePath("opportunities", "evaluations.json"),
        )
        self.opportunities = OpportunityService(self.root)
        self.profile = ProfileService(self.root)
        self.registry = SequenceRegistry(self.root)
        self.journal = OperationJournal(self.root)

    def load_state(self) -> EvaluationState:
        try:
            return EvaluationState.model_validate_json(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return EvaluationState()
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Evaluation state is unreadable or invalid",
                {"path": str(self.path)},
            ) from error

    @staticmethod
    def _find(state: EvaluationState, evaluation_id: str) -> FitEvaluation:
        evaluation = next(
            (item for item in state.evaluations if item.evaluation_id == evaluation_id),
            None,
        )
        if evaluation is None:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Evaluation result reference is missing",
                {"evaluation_id": evaluation_id},
            )
        return evaluation

    def _validate_evidence(self, opportunity_id: str, draft: EvaluationDraft) -> None:
        opportunity = self.opportunities.get(opportunity_id)
        evidence = tuple(_all_evidence(draft))
        for reference in evidence:
            if reference.source is EvidenceSource.POSTING:
                if reference.reference_id != opportunity_id:
                    raise CareerError(
                        ErrorCode.INVALID_INPUT,
                        "Posting evidence references another opportunity",
                        {"reference_id": reference.reference_id},
                    )
                assert reference.start is not None and reference.end is not None
                if opportunity.posting_text[reference.start : reference.end] != reference.excerpt:
                    raise CareerError(
                        ErrorCode.INVALID_INPUT,
                        "Posting evidence excerpt was not found in the captured posting",
                        {"excerpt": reference.excerpt},
                    )
            else:
                fact = self.profile.get_confirmed_fact(reference.reference_id)
                if reference.excerpt not in str(fact.value):
                    raise CareerError(
                        ErrorCode.INVALID_INPUT,
                        "Profile evidence excerpt was not found in the confirmed fact",
                        {"fact_id": fact.fact_id},
                    )
        if draft.mode is EvaluationMode.AUTHORITATIVE:
            if not opportunity.posting_complete:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Authoritative evaluation requires the complete posting",
                    {"opportunity_id": opportunity_id},
                )
            if not draft.supporting_evidence or not draft.opposing_evidence:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Authoritative evaluation requires supporting and opposing evidence",
                )
            if not any(item.source is EvidenceSource.PROFILE for item in evidence):
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Authoritative evaluation requires confirmed profile evidence",
                )

    @staticmethod
    def _score(draft: EvaluationDraft) -> Decimal:
        total_weight = sum(
            (finding.weight for finding in draft.weighted_preferences),
            start=Decimal(0),
        )
        if total_weight == 0:
            return Decimal("0.00")
        weighted = sum(
            (finding.weight * finding.rating for finding in draft.weighted_preferences),
            start=Decimal(0),
        )
        return ((weighted / total_weight) * 100).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def evaluate(
        self,
        opportunity_id: str,
        draft: EvaluationDraft,
        *,
        idempotency_key: str,
    ) -> FitEvaluation:
        state = self.load_state()
        existing_id = state.idempotency_results.get(idempotency_key)
        if existing_id is not None:
            existing = self._find(state, existing_id)
            if existing.opportunity_id != opportunity_id:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Evaluation idempotency key belongs to another opportunity",
                    {
                        "opportunity_id": opportunity_id,
                        "existing_opportunity_id": existing.opportunity_id,
                    },
                )
            prior = self.journal.operation_for_key(f"opportunity-evaluate:{idempotency_key}")
            if prior is not None and self.journal.replay(prior.idempotency_key) is None:
                with WorkspaceLock(self.root, run_id=prior.run_id):
                    checksum = sha256_file(self.path)
                    self.journal.checkpoint(
                        prior.run_id,
                        "evaluations-written",
                        {"checksum": checksum},
                    )
                    self.journal.commit(
                        prior.run_id,
                        {
                            "evaluation_id": existing_id,
                            "state_checksum": checksum,
                            "result_references": [existing_id],
                        },
                    )
            return existing
        self._validate_evidence(opportunity_id, draft)
        score = self._score(draft)
        hard_failure = any(not finding.satisfied for finding in draft.hard_constraints)
        recommendation: Literal["pursue", "review", "dismiss"]
        if hard_failure or score < 40:
            recommendation = "dismiss"
        elif score < 70:
            recommendation = "review"
        else:
            recommendation = "pursue"
        evaluation_id = self.registry.allocate_evaluation_id()
        run_id = self.registry.allocate_run_id()
        evaluation = FitEvaluation(
            evaluation_id=evaluation_id,
            opportunity_id=opportunity_id,
            mode=draft.mode,
            hard_constraints=draft.hard_constraints,
            weighted_preferences=draft.weighted_preferences,
            supporting_evidence=draft.supporting_evidence,
            opposing_evidence=draft.opposing_evidence,
            score=score,
            recommendation=recommendation,
        )
        operation = OperationRecord(
            run_id=run_id,
            operation="opportunity.evaluate",
            idempotency_key=f"opportunity-evaluate:{idempotency_key}",
            status=OperationStatus.STARTED,
        )
        with WorkspaceLock(self.root, run_id=run_id):
            state = self.load_state()
            existing_id = state.idempotency_results.get(idempotency_key)
            if existing_id is not None:
                existing = self._find(state, existing_id)
                if existing.opportunity_id != opportunity_id:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Evaluation idempotency key belongs to another opportunity",
                        {
                            "opportunity_id": opportunity_id,
                            "existing_opportunity_id": existing.opportunity_id,
                        },
                    )
                prior = self.journal.operation_for_key(operation.idempotency_key)
                if prior is not None and self.journal.replay(prior.idempotency_key) is None:
                    checksum = sha256_file(self.path)
                    self.journal.checkpoint(
                        prior.run_id,
                        "evaluations-written",
                        {"checksum": checksum},
                    )
                    self.journal.commit(
                        prior.run_id,
                        {
                            "evaluation_id": existing_id,
                            "state_checksum": checksum,
                            "result_references": [existing_id],
                        },
                    )
                return existing
            self.journal.begin(operation)
            idempotency_results = dict(state.idempotency_results)
            idempotency_results[idempotency_key] = evaluation_id
            updated = state.model_copy(
                update={
                    "evaluations": (*state.evaluations, evaluation),
                    "idempotency_results": idempotency_results,
                }
            )
            atomic_write_json(self.path, updated)
            checksum = sha256_file(self.path)
            self.journal.checkpoint(run_id, "evaluations-written", {"checksum": checksum})
            self.journal.commit(
                run_id,
                {
                    "evaluation_id": evaluation_id,
                    "state_checksum": checksum,
                    "result_references": [evaluation_id],
                },
            )
            return evaluation
