from __future__ import annotations

import json
from datetime import UTC, datetime

from career_agent.models.answer import RetentionClass, ReusePolicy
from career_agent.security.redaction import REDACTED, sanitize
from career_agent.services.answers import AnswerService, SetAnswerCommand

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)


def test_recursive_redaction_removes_sensitive_keys_and_inline_secrets() -> None:
    secret = "sk-example_secret_1234567890"
    sanitized = sanitize(
        {
            "run_id": "RUN-0001",
            "value": secret,
            "nested": {
                "exact_user_response": "private",
                "observed_value": "private-too",
                "message": f"token {secret}",
            },
        }
    )
    encoded = json.dumps(sanitized)

    assert sanitized["value"] == REDACTED
    assert sanitized["nested"]["exact_user_response"] == REDACTED
    assert sanitized["nested"]["observed_value"] == REDACTED
    assert secret not in encoded
    assert "RUN-0001" in encoded


def test_sensitive_values_are_absent_from_audit_and_default_views(tmp_path) -> None:
    secret = "Prefer not to answer"
    service = AnswerService(tmp_path)
    answer = service.set(
        SetAnswerCommand(
            question_id="demographic.disability",
            value="prefer_not_to_answer",
            exact_user_response=secret,
            source_reference="user:fixture",
            retention_class=RetentionClass.SENSITIVE,
            reuse_policy=ReusePolicy.VERIFY_PER_APPLICATION,
            confirmed_at=NOW,
            sensitive_retention_opt_in=True,
            scope={"application_id": "APP-2026-0001"},
        )
    )

    default_view = json.dumps(service.list())
    audit = json.dumps(
        [event.model_dump(mode="json") for event in service.load_state().audit_events]
    )

    assert answer.answer_id in default_view
    assert secret not in default_view
    assert "prefer_not_to_answer" not in default_view
    assert secret not in audit
    assert "prefer_not_to_answer" not in audit


def test_user_idempotency_material_is_hashed_before_journaling(tmp_path) -> None:
    secret_key = "sk-idempotency_secret_1234567890"
    AnswerService(tmp_path).set(
        SetAnswerCommand(
            question_id="contact.email",
            value="candidate@example.test",
            exact_user_response="candidate@example.test",
            source_reference="user:fixture",
            retention_class=RetentionClass.ORDINARY,
            reuse_policy=ReusePolicy.STABLE,
            confirmed_at=NOW,
            idempotency_key=secret_key,
        )
    )

    assert secret_key not in (tmp_path / "journals" / "operations.ndjson").read_text()
    assert secret_key not in (tmp_path / "answers" / "state.json").read_text()
