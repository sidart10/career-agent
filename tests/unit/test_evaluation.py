from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.services.evaluation import (
    ConstraintFinding,
    EvaluationDraft,
    EvaluationMode,
    EvaluationService,
    EvidenceReference,
    EvidenceSource,
    PreferenceFinding,
)
from career_agent.services.opportunities import OpportunityCapture, OpportunityService
from career_agent.services.profile import ProfileService

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)
POSTING_TEXT = (
    "Lead measurement products with engineering and data science. "
    "Five years of product experience required. Travel is required."
)


def add_opportunity(root: Path, *, complete: bool = True) -> str:
    opportunity = OpportunityService(root).add(
        OpportunityCapture(
            company="Example Labs",
            title="Senior Product Manager",
            location="Remote",
            url="https://jobs.example.test/roles/42",
            captured_at=NOW,
            posting_text=POSTING_TEXT,
            posting_complete=complete,
            requisition_id="REQ-42",
        ),
        idempotency_key="capture-42",
    )
    return opportunity.opportunity_id


def confirmed_fact(root: Path) -> str:
    source = root.parent / "profile.txt"
    source.write_text("Current Title: Senior Product Manager\n")
    service = ProfileService(root)
    preview = service.preview_import([source])
    result = service.apply_import(preview.run_id)
    proposal = result.proposed_facts[0]
    fact = service.confirm_fact(
        proposal.fact_id or "",
        proposal.value,
        [proposal.sources[0].source_id],
    )
    return fact.fact_id


def posting_evidence(opportunity_id: str, excerpt: str) -> EvidenceReference:
    start = POSTING_TEXT.index(excerpt)
    return EvidenceReference(
        source=EvidenceSource.POSTING,
        reference_id=opportunity_id,
        excerpt=excerpt,
        start=start,
        end=start + len(excerpt),
    )


def profile_evidence(fact_id: str) -> EvidenceReference:
    return EvidenceReference(
        source=EvidenceSource.PROFILE,
        reference_id=fact_id,
        excerpt="Senior Product Manager",
    )


def test_evaluation_draft_rejects_model_supplied_score() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EvaluationDraft.model_validate(
            {
                "mode": "preliminary",
                "score": "100",
                "hard_constraints": [],
                "weighted_preferences": [],
                "supporting_evidence": [],
                "opposing_evidence": [],
            }
        )


def test_preliminary_evaluation_computes_weighted_score_and_recommendation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    draft = EvaluationDraft(
        mode=EvaluationMode.PRELIMINARY,
        hard_constraints=(ConstraintFinding(name="location", satisfied=True),),
        weighted_preferences=(
            PreferenceFinding(name="scope", weight=Decimal("3"), rating=Decimal("1")),
            PreferenceFinding(name="travel", weight=Decimal("1"), rating=Decimal("0")),
        ),
        supporting_evidence=(posting_evidence(opportunity_id, "Lead measurement products"),),
    )

    evaluation = EvaluationService(root).evaluate(
        opportunity_id,
        draft,
        idempotency_key="evaluation-42",
    )

    assert evaluation.score == Decimal("75.00")
    assert evaluation.recommendation == "pursue"


def test_authoritative_evaluation_requires_complete_posting(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root, complete=False)
    fact_id = confirmed_fact(root)
    draft = EvaluationDraft(
        mode=EvaluationMode.AUTHORITATIVE,
        supporting_evidence=(profile_evidence(fact_id),),
        opposing_evidence=(posting_evidence(opportunity_id, "Travel is required"),),
    )

    with pytest.raises(CareerError) as error:
        EvaluationService(root).evaluate(opportunity_id, draft, idempotency_key="auth-42")

    assert error.value.code is ErrorCode.INVALID_INPUT


def test_authoritative_evaluation_requires_both_evidence_directions(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    fact_id = confirmed_fact(root)
    draft = EvaluationDraft(
        mode=EvaluationMode.AUTHORITATIVE,
        supporting_evidence=(profile_evidence(fact_id),),
    )

    with pytest.raises(CareerError, match="opposing"):
        EvaluationService(root).evaluate(opportunity_id, draft, idempotency_key="auth-42")


def test_authoritative_evaluation_rejects_unknown_profile_fact(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    draft = EvaluationDraft(
        mode=EvaluationMode.AUTHORITATIVE,
        supporting_evidence=(profile_evidence("FACT-9999"),),
        opposing_evidence=(posting_evidence(opportunity_id, "Travel is required"),),
    )

    with pytest.raises(CareerError) as error:
        EvaluationService(root).evaluate(opportunity_id, draft, idempotency_key="auth-42")

    assert error.value.code is ErrorCode.INVALID_INPUT


def test_posting_evidence_excerpt_must_exist_in_captured_posting(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    draft = EvaluationDraft(
        mode=EvaluationMode.PRELIMINARY,
        supporting_evidence=(
            EvidenceReference(
                source=EvidenceSource.POSTING,
                reference_id=opportunity_id,
                excerpt="Invented requirement",
                start=0,
                end=20,
            ),
        ),
    )

    with pytest.raises(CareerError, match="excerpt"):
        EvaluationService(root).evaluate(opportunity_id, draft, idempotency_key="prelim-42")


def test_replay_finishes_evaluation_journal_after_state_write(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    service = EvaluationService(root)
    draft = EvaluationDraft(
        mode=EvaluationMode.PRELIMINARY,
        supporting_evidence=(posting_evidence(opportunity_id, "Lead measurement products"),),
    )
    real_commit = service.journal.commit
    service.journal.commit = lambda run_id, result: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("interrupt before commit")
    )

    with pytest.raises(RuntimeError, match="interrupt before commit"):
        service.evaluate(opportunity_id, draft, idempotency_key="eval-42")

    service.journal.commit = real_commit  # type: ignore[method-assign]
    replayed = service.evaluate(opportunity_id, draft, idempotency_key="eval-42")
    operation = service.journal.operation_for_key("opportunity-evaluate:eval-42")
    assert replayed.evaluation_id == "EVAL-0001"
    assert operation is not None
    assert service.journal.recover(operation.run_id).status.value == "committed"


def test_evaluation_idempotency_key_cannot_cross_opportunities(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    first_id = add_opportunity(root)
    second = OpportunityService(root).add(
        OpportunityCapture(
            company="Another Labs",
            title="Product Manager",
            location="Remote",
            url="https://jobs.example.test/roles/99",
            captured_at=NOW,
            posting_text=POSTING_TEXT,
            posting_complete=True,
            requisition_id="REQ-99",
        ),
        idempotency_key="capture-99",
    )
    service = EvaluationService(root)
    first_draft = EvaluationDraft(
        mode=EvaluationMode.PRELIMINARY,
        supporting_evidence=(posting_evidence(first_id, "Lead measurement products"),),
    )
    second_draft = EvaluationDraft(
        mode=EvaluationMode.PRELIMINARY,
        supporting_evidence=(posting_evidence(second.opportunity_id, "Lead measurement products"),),
    )
    service.evaluate(first_id, first_draft, idempotency_key="shared-key")

    with pytest.raises(CareerError) as error:
        service.evaluate(second.opportunity_id, second_draft, idempotency_key="shared-key")

    assert error.value.code is ErrorCode.CONFLICT
