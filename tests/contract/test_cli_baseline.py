from __future__ import annotations

import json

from typer.testing import CliRunner

from career_agent.cli import app

runner = CliRunner()


def test_help_exits_successfully() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "career" in result.output.lower()
    assert "doctor" in result.output.lower()


def test_doctor_json_uses_response_envelope() -> None:
    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "data": {
            "capabilities": [
                "governed_cli_mutation",
                "approval_binding",
                "pdf_rendering",
                "persisted_state_validation",
            ],
            "platform": payload["data"]["platform"],
            "python_version": payload["data"]["python_version"],
            "workspace_path": payload["data"]["workspace_path"],
        },
        "error": None,
    }


def test_invalid_command_is_concise_and_has_no_traceback() -> None:
    result = runner.invoke(app, ["does-not-exist"])

    assert result.exit_code != 0
    assert "No such command" in result.output
    assert "Traceback" not in result.output
