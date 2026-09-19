from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.answer import RetentionClass, ReusePolicy
from career_agent.models.operation import OperationStatus
from career_agent.services.answers import AnswerService, SetAnswerCommand

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)


def command(**updates: object) -> SetAnswerCommand:
    values: dict[str, object] = {
        "question_id": "contact.email",
        "value": "candidate@example.test",
        "exact_user_response": "candidate@example.test",
        "source_reference": "user:fixture",
        "retention_class": RetentionClass.ORDINARY,
        "reuse_policy": ReusePolicy.STABLE,
        "confirmed_at": NOW,
    }
    values.update(updates)
    return SetAnswerCommand.model_validate(values)


@pytest.mark.parametrize(
    ("question_id", "value"),
    [
        ("credential.password", "correct-horse-battery-staple"),
        ("authentication.mfa_code", "123456"),
        ("identity.national_identifier", "123-45-6789"),
        ("banking.account_number", "000123456789"),
        ("identity_document.passport", "P12345678"),
    ],
)
def test_prohibited_fields_are_rejected_before_any_persistence(
    tmp_path: Path,
    question_id: str,
    value: str,
) -> None:
    service = AnswerService(tmp_path)

    with pytest.raises(CareerError) as error:
        service.set(
            command(
                question_id=question_id,
                value=value,
                exact_user_response=value,
                retention_class=RetentionClass.PROHIBITED,
                reuse_policy=ReusePolicy.APPLICATION_ONLY,
            )
        )

    assert error.value.code is ErrorCode.INVALID_INPUT
    assert value not in str(error.value)
    assert not (tmp_path / "answers" / "state.json").exists()
    journal = tmp_path / "journals" / "operations.ndjson"
    assert not journal.exists() or value not in journal.read_text()


def test_prohibited_pattern_is_rejected_even_if_mislabeled_ordinary(tmp_path: Path) -> None:
    secret = "123-45-6789"

    with pytest.raises(CareerError):
        AnswerService(tmp_path).set(command(value=secret, exact_user_response=secret))

    assert secret not in "\n".join(
        path.read_text(errors="ignore") for path in tmp_path.rglob("*") if path.is_file()
    )


def test_sensitive_retention_requires_explicit_opt_in(tmp_path: Path) -> None:
    service = AnswerService(tmp_path)
    sensitive = command(
        question_id="demographic.disability",
        value="prefer_not_to_answer",
        exact_user_response="Prefer not to answer",
        retention_class=RetentionClass.SENSITIVE,
        reuse_policy=ReusePolicy.VERIFY_PER_APPLICATION,
        scope={"application_id": "APP-2026-0001"},
    )

    with pytest.raises(CareerError) as error:
        service.set(sensitive)
    stored = service.set(sensitive.model_copy(update={"sensitive_retention_opt_in": True}))

    assert error.value.code is ErrorCode.APPROVAL_REQUIRED
    assert stored.retention_class is RetentionClass.SENSITIVE
    assert stored.value == "prefer_not_to_answer"


def test_set_is_idempotent_and_conflict_requires_explicit_override(tmp_path: Path) -> None:
    service = AnswerService(tmp_path)
    first = service.set(command(idempotency_key="answer-1"))

    replayed = service.set(command(idempotency_key="answer-1"))
    with pytest.raises(CareerError) as error:
        service.set(
            command(
                value="other@example.test",
                exact_user_response="other@example.test",
                idempotency_key="answer-2",
            )
        )

    assert replayed == first
    assert error.value.code is ErrorCode.CONFLICT


def test_idempotency_key_cannot_be_reused_for_another_answer(tmp_path: Path) -> None:
    service = AnswerService(tmp_path)
    service.set(command(idempotency_key="shared-key"))

    with pytest.raises(CareerError) as error:
        service.set(
            command(
                question_id="contact.phone",
                value="+1-555-0100",
                exact_user_response="+1-555-0100",
                idempotency_key="shared-key",
            )
        )

    assert error.value.code is ErrorCode.CONFLICT


def test_concurrent_conflicting_defaults_cannot_create_duplicate_scope(
    tmp_path: Path,
) -> None:
    barrier = Barrier(2)

    def store(value: str) -> str:
        barrier.wait()
        try:
            return (
                AnswerService(tmp_path)
                .set(
                    command(
                        value=value,
                        exact_user_response=value,
                        idempotency_key=f"set-{value}",
                    )
                )
                .answer_id
            )
        except CareerError as error:
            return error.code.value

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(store, ["one@example.test", "two@example.test"]))

    state = AnswerService(tmp_path).load_state()
    assert len(state.answers) == 1
    assert sorted(outcomes).count(ErrorCode.CONFLICT.value) == 1


def test_set_repairs_journal_when_state_writes_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AnswerService(tmp_path)
    real_commit = service.journal.commit
    interrupted = False

    def interrupt_commit(run_id: str, result: object) -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise OSError("simulated journal interruption")
        real_commit(run_id, result)  # type: ignore[arg-type]

    monkeypatch.setattr(service.journal, "commit", interrupt_commit)
    answer_command = command(idempotency_key="repair-me")
    with pytest.raises(OSError, match="journal interruption"):
        service.set(answer_command)
    run_id = service.load_state().audit_events[-1].run_id

    recovered = service.set(answer_command)

    assert recovered.answer_id == "ANS-0001"
    assert service.journal.recover(run_id).status is OperationStatus.COMMITTED


def test_delete_repairs_journal_when_state_writes_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AnswerService(tmp_path)
    answer = service.set(command(idempotency_key="delete-repair"))
    preview = service.delete_preview(answer.answer_id)
    real_commit = service.journal.commit
    interrupted = False

    def interrupt_commit(run_id: str, result: object) -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise OSError("simulated delete journal interruption")
        real_commit(run_id, result)  # type: ignore[arg-type]

    monkeypatch.setattr(service.journal, "commit", interrupt_commit)
    with pytest.raises(OSError, match="delete journal interruption"):
        service.delete(answer.answer_id, preview.preview_digest)
    run_id = service.load_state().audit_events[-1].run_id

    recovered = service.delete(answer.answer_id, preview.preview_digest)

    assert recovered.deleted is True
    assert service.journal.recover(run_id).status is OperationStatus.COMMITTED


@pytest.mark.parametrize(
    "question_id",
    ["authorization.current_us", "sponsorship.future_us", "legal.criminal_history"],
)
def test_known_high_risk_questions_cannot_be_mislabeled_ordinary(
    tmp_path: Path,
    question_id: str,
) -> None:
    with pytest.raises(CareerError) as error:
        AnswerService(tmp_path).set(command(question_id=question_id, value=True))

    assert error.value.code is ErrorCode.INVALID_INPUT
    assert not (tmp_path / "answers" / "state.json").exists()


def test_compensation_requires_typed_units_and_context(tmp_path: Path) -> None:
    with pytest.raises(CareerError) as error:
        AnswerService(tmp_path).set(
            command(
                question_id="compensation.expectation",
                value=180000,
                exact_user_response="$180k",
                retention_class=RetentionClass.HIGH_RISK,
                reuse_policy=ReusePolicy.STABLE,
            )
        )

    assert error.value.code is ErrorCode.INVALID_INPUT
    assert not (tmp_path / "answers" / "state.json").exists()


def test_employer_specific_narrative_is_not_admitted_to_answer_bank(tmp_path: Path) -> None:
    with pytest.raises(CareerError) as error:
        AnswerService(tmp_path).set(
            command(
                question_id="narrative.why_this_company",
                value="Because this employer is unique.",
                exact_user_response="Because this employer is unique.",
                reuse_policy=ReusePolicy.APPLICATION_ONLY,
            )
        )

    assert error.value.code is ErrorCode.INVALID_INPUT


def test_set_reuses_reserved_answer_identity_after_interrupted_state_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AnswerService(tmp_path)
    from career_agent.services import answers as answer_module

    real_write = answer_module.atomic_write_json
    interrupted = False

    def interrupt_state_once(path: Path, value: object) -> None:
        nonlocal interrupted
        if path.name == "state.json" and not interrupted:
            interrupted = True
            raise OSError("simulated answer state interruption")
        real_write(path, value)  # type: ignore[arg-type]

    monkeypatch.setattr(answer_module, "atomic_write_json", interrupt_state_once)
    answer_command = command(idempotency_key="stable-identity")
    with pytest.raises(OSError, match="answer state interruption"):
        service.set(answer_command)

    recovered = service.set(answer_command)

    assert recovered.answer_id == "ANS-0001"


@pytest.mark.parametrize(
    ("reuse_policy", "scope", "expires_at"),
    [
        (ReusePolicy.APPLICATION_ONLY, {}, None),
        (ReusePolicy.VERIFY_PER_APPLICATION, {}, None),
        (ReusePolicy.VERIFY_PER_JURISDICTION, {}, None),
        (ReusePolicy.EXPIRES_AFTER, {}, None),
    ],
)
def test_reuse_policy_requires_its_matching_scope_or_expiry(
    tmp_path: Path,
    reuse_policy: ReusePolicy,
    scope: dict[str, str],
    expires_at: datetime | None,
) -> None:
    with pytest.raises(CareerError) as error:
        AnswerService(tmp_path).set(
            command(
                reuse_policy=reuse_policy,
                scope=scope,
                expires_at=expires_at,
            )
        )

    assert error.value.code is ErrorCode.INVALID_INPUT


def test_deletion_preview_becomes_stale_when_answer_changes(tmp_path: Path) -> None:
    service = AnswerService(tmp_path)
    answer = service.set(command(idempotency_key="before-delete-preview"))
    preview = service.delete_preview(answer.answer_id)
    service.set(
        command(
            value="updated@example.test",
            exact_user_response="updated@example.test",
            allow_override=True,
            idempotency_key="answer-updated",
        )
    )

    with pytest.raises(CareerError) as error:
        service.delete(answer.answer_id, preview.preview_digest)

    assert error.value.code is ErrorCode.CONFLICT
