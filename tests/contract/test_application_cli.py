from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app
from career_agent.config import initialize_workspace

runner = CliRunner()


def add_opportunity(workspace: Path, posting: Path) -> str:
    initialize_workspace(workspace)
    result = runner.invoke(
        app,
        [
            "opportunity",
            "add",
            "--company",
            "Example Labs",
            "--title",
            "Product Manager",
            "--location",
            "Remote",
            "--url",
            "https://jobs.example.test/roles/42",
            "--posting",
            str(posting),
            "--posting-complete",
            "--idempotency-key",
            "capture-42",
            "--json",
        ],
        env={"CAREER_WORKSPACE": str(workspace)},
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)["data"]["opportunity_id"]


def test_pursue_show_transition_and_posting_check_json_contract(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    posting = tmp_path / "posting.txt"
    posting.write_text("Build measurement products.")
    opportunity_id = add_opportunity(workspace, posting)
    environment = {"CAREER_WORKSPACE": str(workspace)}

    pursued = runner.invoke(
        app,
        [
            "opportunity",
            "pursue",
            opportunity_id,
            "--idempotency-key",
            "pursue-42",
            "--json",
        ],
        env=environment,
    )
    assert pursued.exit_code == 0, pursued.output
    application_id = json.loads(pursued.stdout)["data"]["application_id"]

    shown = runner.invoke(
        app,
        ["application", "show", application_id, "--json"],
        env=environment,
    )
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["data"]["opportunity_id"] == opportunity_id

    transitioned = runner.invoke(
        app,
        [
            "application",
            "transition",
            application_id,
            "ready_for_review",
            "--reason",
            "drafts complete",
            "--json",
        ],
        env=environment,
    )
    assert transitioned.exit_code == 0, transitioned.output
    assert json.loads(transitioned.stdout)["data"]["stage"] == "ready_for_review"

    capture = tmp_path / "freshness.json"
    capture.write_text(
        json.dumps(
            {
                "raw_text": "Build measurement products from New York.",
                "source_url": "https://jobs.example.test/roles/42?utm_source=email",
                "retrieved_at": datetime.now(UTC).isoformat(),
                "source_adapter": "manual",
                "source_adapter_metadata": {"operator": "test"},
                "availability": "open",
                "responsibilities": ["Build measurement products."],
                "location": "New York, NY",
                "compensation": None,
                "eligibility": None,
                "deadline": None,
                "requisition_id": None,
            }
        )
    )
    checked = runner.invoke(
        app,
        [
            "application",
            "posting-check",
            application_id,
            "--input",
            str(capture),
            "--json",
        ],
        env=environment,
    )
    assert checked.exit_code == 0, checked.output
    data = json.loads(checked.stdout)["data"]
    assert data["change_set"]["classification"] == "material"
    assert data["application"]["stage"] == "preparing"
    assert data["snapshot"]["snapshot_id"] == "PST-0002"


def test_application_cli_returns_structured_error_for_unknown_record(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path / "workspace")
    result = runner.invoke(
        app,
        ["application", "show", "APP-2026-9999", "--json"],
        env={"CAREER_WORKSPACE": str(tmp_path / "workspace")},
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"
