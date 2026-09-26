from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app
from career_agent.config import initialize_workspace

from ..unit.documents.test_release import request, setup_workspace

runner = CliRunner()


def test_release_create_list_and_verify_cli_contract(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    initialize_workspace(workspace)
    application_id, _ = setup_workspace(workspace)
    request_path = tmp_path / "release.json"
    request_path.write_text(request().model_dump_json())
    environment = {"CAREER_WORKSPACE": str(workspace)}

    created = runner.invoke(
        app,
        ["release", "create", application_id, "--input", str(request_path), "--json"],
        env=environment,
    )
    assert created.exit_code == 0, created.output
    assert json.loads(created.stdout)["data"]["release_id"] == "REL-0001"

    listed = runner.invoke(
        app,
        ["release", "list", application_id, "--json"],
        env=environment,
    )
    assert listed.exit_code == 0, listed.output
    assert len(json.loads(listed.stdout)["data"]) == 1

    verified = runner.invoke(
        app,
        ["release", "verify", application_id, "REL-0001", "--json"],
        env=environment,
    )
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.stdout)["data"]["verified"] is True

    upload = runner.invoke(
        app,
        [
            "release",
            "upload-copy",
            application_id,
            "REL-0001",
            "--artifact-type",
            "resume_pdf",
            "--json",
        ],
        env=environment,
    )
    assert upload.exit_code == 0, upload.output
    upload_data = json.loads(upload.stdout)["data"]
    assert upload_data["filename"].startswith("Avery_Candidate_Example_Labs")
    assert (workspace / upload_data["relative_path"]).is_file()


def test_release_cli_rejects_invalid_request_without_content_leak(tmp_path: Path) -> None:
    initialize_workspace(tmp_path / "workspace")
    request_path = tmp_path / "bad.json"
    secret = "unsupported private resume content"
    request_path.write_text(secret)

    result = runner.invoke(
        app,
        [
            "release",
            "create",
            "APP-2026-0001",
            "--input",
            str(request_path),
            "--json",
        ],
        env={"CAREER_WORKSPACE": str(tmp_path / "workspace")},
    )

    assert result.exit_code == 2
    assert secret not in result.stdout
