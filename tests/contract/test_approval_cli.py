from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app

from ..unit.test_approval_service import prepare_submission

runner = CliRunner()


def test_submission_approval_has_no_boolean_bypass_and_requires_tty(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    application_id, submission_id = prepare_submission(workspace)
    environment = {"CAREER_WORKSPACE": str(workspace)}

    help_result = runner.invoke(app, ["submission", "approve", "--help"])
    result = runner.invoke(
        app,
        ["submission", "approve", application_id, submission_id, "--json"],
        env=environment,
    )

    assert help_result.exit_code == 0
    assert "--yes" not in help_result.stdout
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "not_ready"
    approvals = workspace / "applications" / application_id / "submissions" / submission_id
    assert not (approvals / "approvals").exists()
