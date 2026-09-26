from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app

runner = CliRunner()


def test_help_exits_successfully() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "career" in result.output.lower()
    assert "doctor" in result.output.lower()


def test_version_reports_public_compatibility_contract() -> None:
    result = runner.invoke(app, ["version", "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data == {
        "api_version": "1.0",
        "cli_version": "0.1.0",
        "skill_bundle_version": "0.1.0",
        "supported_skill_api": ">=1.0,<2.0",
        "supported_workspace_schemas": [1],
    }


def test_init_creates_an_idempotent_versioned_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    environment = {"CAREER_WORKSPACE": str(workspace)}

    first = runner.invoke(app, ["init", "--json"], env=environment)
    second = runner.invoke(app, ["init", "--json"], env=environment)

    assert first.exit_code == second.exit_code == 0
    payload = json.loads(second.stdout)
    assert payload["data"]["workspace_path"] == str(workspace.resolve())
    assert payload["data"]["schema_version"] == 1
    assert payload["data"]["created"] is False
    marker = json.loads((workspace / "workspace.json").read_text())
    assert marker["schema_version"] == 1
    assert marker["workspace_kind"] == "single_candidate"
    assert marker["workspace_id"] == payload["data"]["workspace_id"]
    assert {
        "applications",
        "journals",
        "opportunities",
        "profile",
        "resources",
        "runs",
    }.issubset({path.name for path in workspace.iterdir() if path.is_dir()})


def test_doctor_json_uses_response_envelope(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["doctor", "--json"],
        env={
            "CAREER_WORKSPACE": str(tmp_path / "workspace"),
            "CAREER_RUNTIME": "",
            "CODEX_HOME": "",
            "CLAUDE_PROJECT_DIR": "",
        },
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["error"] is None
    data = payload["data"]
    assert data["capabilities"] == [
        "governed_cli_mutation",
        "approval_binding",
        "pdf_rendering",
        "persisted_state_validation",
    ]
    assert data["workspace_path"] == str((tmp_path / "workspace").resolve())
    assert data["recovery"]["recoverable_run_ids"] == []
    assert data["recovery"]["quarantine_run_ids"] == []
    report = data["capability_report"]
    assert report["schema_version"] == 1
    assert report["runtime"] == "unknown"
    assert report["release_ready"] is False
    assert {check["name"] for check in report["capabilities"]} >= {
        "runtime_detection",
        "skill_installation",
        "approval_authority",
    }


def test_invalid_command_is_concise_and_has_no_traceback() -> None:
    result = runner.invoke(app, ["does-not-exist"])

    assert result.exit_code != 0
    assert "No such command" in result.output
    assert "Traceback" not in result.output
