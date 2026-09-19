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


def test_doctor_json_uses_response_envelope(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["doctor", "--json"],
        env={"CAREER_WORKSPACE": str(tmp_path / "workspace")},
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
    assert data["recovery"]["recovered_run_ids"] == []
    assert data["recovery"]["quarantined_run_ids"] == []
    assert data["cleanup"]["deleted_paths"] == []
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
