from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app

runner = CliRunner()


def add_command(posting: Path, requisition_id: str, url: str) -> list[str]:
    return [
        "opportunity",
        "add",
        "--company",
        "Example Labs",
        "--title",
        "Product Manager",
        "--location",
        "Remote",
        "--url",
        url,
        "--posting",
        str(posting),
        "--posting-complete",
        "--requisition-id",
        requisition_id,
        "--idempotency-key",
        f"capture-{requisition_id}",
        "--json",
    ]


def test_opportunity_add_and_list_do_not_create_application(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    posting = tmp_path / "posting.txt"
    posting.write_text("Lead measurement products. Travel is required.")
    environment = {"CAREER_WORKSPACE": str(workspace)}

    added_result = runner.invoke(
        app,
        add_command(
            posting,
            "REQ-42",
            "https://jobs.example.test/roles/42?utm_source=email",
        ),
        env=environment,
    )
    added = json.loads(added_result.stdout)
    assert added_result.exit_code == 0
    assert added["data"]["opportunity_id"] == "OPP-2026-0001"
    assert added["data"]["canonical_url"] == "https://jobs.example.test/roles/42"

    listed_result = runner.invoke(
        app,
        ["opportunity", "list", "--json"],
        env=environment,
    )
    listed = json.loads(listed_result.stdout)
    assert listed_result.exit_code == 0
    assert [item["opportunity_id"] for item in listed["data"]] == ["OPP-2026-0001"]
    assert not (workspace / "applications").exists()


def test_opportunity_merge_and_unmerge_are_exposed_by_cli(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    posting = tmp_path / "posting.txt"
    posting.write_text("Lead measurement products.")
    environment = {"CAREER_WORKSPACE": str(workspace)}
    for requisition, path in [("REQ-100", "100"), ("REQ-101", "101")]:
        result = runner.invoke(
            app,
            add_command(posting, requisition, f"https://jobs.example.test/roles/{path}"),
            env=environment,
        )
        assert result.exit_code == 0

    merge_result = runner.invoke(
        app,
        [
            "opportunity",
            "merge",
            "OPP-2026-0001",
            "OPP-2026-0002",
            "--json",
        ],
        env=environment,
    )
    merge = json.loads(merge_result.stdout)
    assert merge_result.exit_code == 0

    unmerge_result = runner.invoke(
        app,
        ["opportunity", "unmerge", merge["data"]["merge_id"], "--json"],
        env=environment,
    )
    restored = json.loads(unmerge_result.stdout)
    assert unmerge_result.exit_code == 0
    assert [item["opportunity_id"] for item in restored["data"]] == [
        "OPP-2026-0001",
        "OPP-2026-0002",
    ]


def test_opportunity_evaluate_ingests_schema_validated_json(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    posting = tmp_path / "posting.txt"
    posting.write_text("Lead measurement products. Travel is required.")
    environment = {"CAREER_WORKSPACE": str(workspace)}
    add_result = runner.invoke(
        app,
        add_command(posting, "REQ-42", "https://jobs.example.test/roles/42"),
        env=environment,
    )
    assert add_result.exit_code == 0
    draft = tmp_path / "evaluation.json"
    draft.write_text(
        json.dumps(
            {
                "mode": "preliminary",
                "hard_constraints": [{"name": "location", "satisfied": True}],
                "weighted_preferences": [{"name": "scope", "weight": "1", "rating": "0.8"}],
                "supporting_evidence": [
                    {
                        "source": "posting",
                        "reference_id": "OPP-2026-0001",
                        "excerpt": "Lead measurement products",
                        "start": 0,
                        "end": 25,
                    }
                ],
                "opposing_evidence": [],
            }
        )
    )

    result = runner.invoke(
        app,
        [
            "opportunity",
            "evaluate",
            "OPP-2026-0001",
            "--input",
            str(draft),
            "--idempotency-key",
            "eval-42",
            "--json",
        ],
        env=environment,
    )

    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert payload["data"]["score"] == "80.00"
    assert payload["data"]["recommendation"] == "pursue"
