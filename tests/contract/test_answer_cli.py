from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app
from career_agent.config import initialize_workspace

runner = CliRunner()


def write_command(path: Path, *, sensitive_opt_in: bool = False) -> None:
    path.write_text(
        json.dumps(
            {
                "question_id": "demographic.disability",
                "value": "prefer_not_to_answer",
                "exact_user_response": "Prefer not to answer",
                "source_reference": "user:cli",
                "retention_class": "sensitive",
                "reuse_policy": "verify_per_application",
                "confirmed_at": datetime.now(UTC).isoformat(),
                "scope": {"application_id": "APP-2026-0001"},
                "sensitive_retention_opt_in": sensitive_opt_in,
                "idempotency_key": "cli-answer-1",
            }
        )
    )


def test_answer_cli_set_list_resolve_and_consent_gated_export(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    initialize_workspace(workspace)
    environment = {"CAREER_WORKSPACE": str(workspace)}
    command_path = tmp_path / "answer.json"
    write_command(command_path, sensitive_opt_in=True)

    created = runner.invoke(
        app,
        ["answer", "set", "--input", str(command_path), "--json"],
        env=environment,
    )
    assert created.exit_code == 0, created.output
    answer_id = json.loads(created.stdout)["data"]["answer_id"]

    listed = runner.invoke(app, ["answer", "list", "--json"], env=environment)
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.stdout)["data"][0]["value"] == "[REDACTED]"
    assert "prefer_not_to_answer" not in listed.stdout

    context = tmp_path / "question.json"
    context.write_text(
        json.dumps(
            {
                "question_id": "demographic.disability",
                "wording": "Voluntary self-identification of disability",
                "application_id": "APP-2026-0001",
            }
        )
    )
    resolved = runner.invoke(
        app,
        ["answer", "resolve", "--input", str(context), "--json"],
        env=environment,
    )
    assert resolved.exit_code == 0, resolved.output
    assert json.loads(resolved.stdout)["data"]["status"] == "needs_confirmation"
    assert "prefer_not_to_answer" not in resolved.stdout

    denied = runner.invoke(
        app,
        ["answer", "export", "--include-sensitive", "--json"],
        env=environment,
    )
    assert denied.exit_code == 6
    assert "prefer_not_to_answer" not in denied.stdout

    exported = runner.invoke(
        app,
        [
            "answer",
            "export",
            "--include-sensitive",
            "--owner-confirmed",
            "--json",
        ],
        env=environment,
    )
    assert exported.exit_code == 0, exported.output
    assert json.loads(exported.stdout)["data"][0]["value"] == "prefer_not_to_answer"
    assert answer_id in exported.stdout


def test_delete_is_digest_bound_and_reports_surviving_history(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    initialize_workspace(workspace)
    environment = {"CAREER_WORKSPACE": str(workspace)}
    command_path = tmp_path / "answer.json"
    write_command(command_path, sensitive_opt_in=True)
    created = runner.invoke(
        app,
        ["answer", "set", "--input", str(command_path), "--json"],
        env=environment,
    )
    answer_id = json.loads(created.stdout)["data"]["answer_id"]
    history = workspace / "applications" / "APP-2026-0001" / "submissions" / "SUB-0001.json"
    history.parent.mkdir(parents=True)
    history.write_text(
        json.dumps(
            {
                "answer_id": answer_id,
                "observed_value": "prefer_not_to_answer",
            }
        )
    )

    previewed = runner.invoke(
        app,
        ["answer", "delete", answer_id, "--preview", "--json"],
        env=environment,
    )
    assert previewed.exit_code == 0, previewed.output
    preview = json.loads(previewed.stdout)["data"]
    assert preview["surviving_references"][0]["representation"] == "exact_value"

    stale = runner.invoke(
        app,
        ["answer", "delete", answer_id, "--preview-digest", "0" * 64, "--json"],
        env=environment,
    )
    assert stale.exit_code == 4

    deleted = runner.invoke(
        app,
        [
            "answer",
            "delete",
            answer_id,
            "--preview-digest",
            preview["preview_digest"],
            "--json",
        ],
        env=environment,
    )
    assert deleted.exit_code == 0, deleted.output
    result = json.loads(deleted.stdout)["data"]
    assert result["deleted"] is True
    assert result["surviving_references"] == preview["surviving_references"]
    assert history.is_file()
