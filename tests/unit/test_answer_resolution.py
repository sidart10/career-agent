from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.models.answer import RetentionClass, ReusePolicy
from career_agent.services.answers import (
    AnswerResolutionStatus,
    AnswerService,
    QuestionContext,
    SetAnswerCommand,
)

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)


def set_answer(
    root: Path,
    *,
    question_id: str,
    value: object,
    retention_class: RetentionClass = RetentionClass.ORDINARY,
    reuse_policy: ReusePolicy = ReusePolicy.STABLE,
    scope: dict[str, str] | None = None,
) -> None:
    AnswerService(root).set(
        SetAnswerCommand(
            question_id=question_id,
            value=value,
            exact_user_response=value,
            source_reference="user:fixture",
            retention_class=retention_class,
            reuse_policy=reuse_policy,
            confirmed_at=NOW,
            scope=scope or {},
        )
    )


def test_registered_low_risk_alias_resolves_automatically(tmp_path: Path) -> None:
    set_answer(tmp_path, question_id="contact.email", value="candidate@example.test")

    resolution = AnswerService(tmp_path).resolve(QuestionContext(wording="  E-MAIL   address "))

    assert resolution.status is AnswerResolutionStatus.RESOLVED
    assert resolution.question_id == "contact.email"
    assert resolution.value == "candidate@example.test"
    assert resolution.requires_final_review is False


def test_high_risk_wording_requires_confirmation_and_surfaces_final_review(
    tmp_path: Path,
) -> None:
    set_answer(
        tmp_path,
        question_id="sponsorship.future_us",
        value=False,
        retention_class=RetentionClass.HIGH_RISK,
        reuse_policy=ReusePolicy.VERIFY_PER_APPLICATION,
        scope={"application_id": "APP-2026-0001"},
    )

    resolution = AnswerService(tmp_path).resolve(
        QuestionContext(
            wording="Will you now or in the future require sponsorship?",
            application_id="APP-2026-0001",
        )
    )

    assert resolution.status is AnswerResolutionStatus.NEEDS_CONFIRMATION
    assert resolution.question_id == "sponsorship.future_us"
    assert resolution.value is None
    assert resolution.requires_final_review is True


def test_reversed_or_compound_authorization_question_never_reuses_answer(
    tmp_path: Path,
) -> None:
    set_answer(
        tmp_path,
        question_id="authorization.current_us",
        value=True,
        retention_class=RetentionClass.HIGH_RISK,
        reuse_policy=ReusePolicy.VERIFY_PER_JURISDICTION,
        scope={"jurisdiction": "US"},
    )

    resolution = AnswerService(tmp_path).resolve(
        QuestionContext(
            wording="Do you need work authorization or sponsorship?",
            jurisdiction="US",
        )
    )

    assert resolution.status is AnswerResolutionStatus.UNKNOWN
    assert resolution.value is None


def test_contextual_answer_requires_exact_scope_match(tmp_path: Path) -> None:
    set_answer(
        tmp_path,
        question_id="location.willing_to_relocate",
        value=True,
        retention_class=RetentionClass.CONTEXTUAL,
        reuse_policy=ReusePolicy.VERIFY_PER_JURISDICTION,
        scope={"jurisdiction": "US-CA"},
    )
    service = AnswerService(tmp_path)

    matching = service.resolve(
        QuestionContext(
            question_id="location.willing_to_relocate",
            wording="Are you willing to relocate?",
            jurisdiction="US-CA",
        )
    )
    mismatching = service.resolve(
        QuestionContext(
            question_id="location.willing_to_relocate",
            wording="Are you willing to relocate?",
            jurisdiction="US-NY",
        )
    )

    assert matching.status is AnswerResolutionStatus.RESOLVED
    assert mismatching.status is AnswerResolutionStatus.NEEDS_CONFIRMATION
    assert mismatching.value is None


def test_user_confirmed_alias_is_resolved_but_high_risk_alias_still_gates(
    tmp_path: Path,
) -> None:
    service = AnswerService(tmp_path)
    service.set(
        SetAnswerCommand(
            question_id="sponsorship.future_us",
            value=False,
            exact_user_response=False,
            source_reference="user:fixture",
            retention_class=RetentionClass.HIGH_RISK,
            reuse_policy=ReusePolicy.VERIFY_PER_APPLICATION,
            confirmed_at=NOW,
            scope={"application_id": "APP-2026-0001"},
            aliases=("Will visa support ever be needed?",),
            confirm_aliases=True,
        )
    )

    resolution = service.resolve(
        QuestionContext(
            wording="Will visa support ever be needed?",
            application_id="APP-2026-0001",
        )
    )

    assert resolution.question_id == "sponsorship.future_us"
    assert resolution.status is AnswerResolutionStatus.NEEDS_CONFIRMATION


def test_compensation_scope_requires_matching_currency_and_period(tmp_path: Path) -> None:
    service = AnswerService(tmp_path)
    service.set(
        SetAnswerCommand(
            question_id="compensation.expectation",
            value={
                "minimum": 180000,
                "maximum": 220000,
                "currency": "USD",
                "period": "annual",
                "location_context": "US-CA",
                "flexible": True,
            },
            exact_user_response="$180,000 annually",
            source_reference="user:fixture",
            retention_class=RetentionClass.CONTEXTUAL,
            reuse_policy=ReusePolicy.VERIFY_PER_JURISDICTION,
            confirmed_at=NOW,
            scope={"jurisdiction": "US-CA", "currency": "USD", "period": "annual"},
        )
    )

    matching = service.resolve(
        QuestionContext(
            question_id="compensation.expectation",
            wording="Annual salary expectation in USD",
            jurisdiction="US-CA",
            scope={"currency": "USD", "period": "annual"},
        )
    )
    hourly = service.resolve(
        QuestionContext(
            question_id="compensation.expectation",
            wording="Hourly pay expectation in USD",
            jurisdiction="US-CA",
            scope={"currency": "USD", "period": "hourly"},
        )
    )

    assert matching.status is AnswerResolutionStatus.RESOLVED
    assert hourly.status is AnswerResolutionStatus.NEEDS_CONFIRMATION


def test_application_specific_override_wins_over_stable_default(tmp_path: Path) -> None:
    service = AnswerService(tmp_path)
    set_answer(tmp_path, question_id="location.willing_to_relocate", value=False)
    service.set(
        SetAnswerCommand(
            question_id="location.willing_to_relocate",
            value=True,
            exact_user_response=True,
            source_reference="user:fixture",
            retention_class=RetentionClass.CONTEXTUAL,
            reuse_policy=ReusePolicy.APPLICATION_ONLY,
            confirmed_at=NOW,
            scope={"application_id": "APP-2026-0001"},
        )
    )

    resolution = service.resolve(
        QuestionContext(
            question_id="location.willing_to_relocate",
            wording="Are you willing to relocate for this role?",
            application_id="APP-2026-0001",
        )
    )

    assert resolution.status is AnswerResolutionStatus.RESOLVED
    assert resolution.value is True
