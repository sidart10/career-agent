from __future__ import annotations

import json
from pathlib import Path

from click.testing import Result
from typer.testing import CliRunner

from career_agent.cli import app

runner = CliRunner()


def _payload(result: Result) -> dict[str, object]:
    return json.loads(result.stdout)


def _invoke(workspace: Path, arguments: list[str]) -> Result:
    return runner.invoke(
        app,
        [*arguments, "--json"],
        env={"CAREER_WORKSPACE": str(workspace)},
    )


def test_model_proposals_require_privacy_acknowledgement_and_exact_evidence(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    assert _invoke(workspace, ["init"]).exit_code == 0
    before = {path.relative_to(workspace) for path in workspace.rglob("*")}

    privacy = _invoke(workspace, ["privacy", "status"])

    assert privacy.exit_code == 0, privacy.output
    disclosure = _payload(privacy)["data"]
    assert disclosure["policy_version"] == "2026-09-26.v1"
    assert disclosure["acknowledged"] is False
    assert disclosure["workspace_path"] == str(workspace.resolve())
    assert "model provider" in str(disclosure["disclosure"]).casefold()
    assert "plaintext" in str(disclosure["disclosure"]).casefold()
    assert {path.relative_to(workspace) for path in workspace.rglob("*")} == before

    resume = tmp_path / "resume.txt"
    resume.write_text(
        "Avery Example\nProduct Manager\n\nExperience\nBuilt reliable measurement systems.\n"
    )
    preview_result = _invoke(workspace, ["import", "preview", str(resume)])
    preview = _payload(preview_result)["data"]
    run_id = str(preview["run_id"])
    applied_result = _invoke(workspace, ["import", "apply", run_id])
    applied = _payload(applied_result)["data"]
    source = applied["imported_sources"][0]
    extracted_text = (workspace / source["extracted_text_path"]).read_text()
    exact = "Avery Example"
    start = extracted_text.index(exact)
    proposal_path = tmp_path / "proposal.json"
    proposal = {
        "proposals": [
            {
                "key": "identity.display_name",
                "value": exact,
                "source": {
                    "source_id": source["source_id"],
                    "source_checksum": source["checksum"],
                    "normalized_text_checksum": source["normalized_text_checksum"],
                    "extractor": source["extractor"],
                    "extractor_version": source["extractor_version"],
                    "block_id": "document",
                    "page_number": None,
                    "start_offset": start,
                    "end_offset": start + len(exact),
                    "exact_text": exact,
                },
            }
        ]
    }
    proposal_path.write_text(json.dumps(proposal))

    blocked = _invoke(workspace, ["profile", "propose", "--input", str(proposal_path)])
    assert blocked.exit_code != 0
    assert _payload(blocked)["error"]["code"] == "approval_required"

    acknowledged = _invoke(
        workspace,
        [
            "privacy",
            "acknowledge",
            "--policy-version",
            "2026-09-26.v1",
            "--provider",
            "configured-test-provider",
        ],
    )
    assert acknowledged.exit_code == 0, acknowledged.output

    bad_proposal = json.loads(json.dumps(proposal))
    bad_proposal["proposals"][0]["source"]["exact_text"] = "Wrong Person"
    proposal_path.write_text(json.dumps(bad_proposal))
    rejected = _invoke(workspace, ["profile", "propose", "--input", str(proposal_path)])
    assert rejected.exit_code != 0
    assert _payload(rejected)["error"]["code"] == "invalid_input"

    proposal_path.write_text(json.dumps(proposal))
    accepted = _invoke(workspace, ["profile", "propose", "--input", str(proposal_path)])
    assert accepted.exit_code == 0, accepted.output
    proposed = _payload(accepted)["data"][0]
    assert proposed["key"] == "identity.display_name"
    assert proposed["sources"][0]["exact_text"] == exact

    registry_before_replay = (workspace / "registry.json").read_bytes()
    replayed = _invoke(workspace, ["profile", "propose", "--input", str(proposal_path)])
    assert replayed.exit_code == 0, replayed.output
    assert _payload(replayed)["data"] == [proposed]
    assert (workspace / "registry.json").read_bytes() == registry_before_replay

    listed = _invoke(workspace, ["profile", "list"])
    assert listed.exit_code == 0, listed.output
    assert _payload(listed)["data"]["proposals"][0]["fact_id"] == proposed["fact_id"]

    confirmed = _invoke(
        workspace,
        [
            "profile",
            "confirm",
            proposed["fact_id"],
            "--value",
            json.dumps(exact),
            "--source-id",
            source["source_id"],
        ],
    )
    assert confirmed.exit_code == 0, confirmed.output

    needs_preferences = _invoke(workspace, ["onboarding", "status"])
    assert needs_preferences.exit_code == 0, needs_preferences.output
    status = _payload(needs_preferences)["data"]
    assert status["first_incomplete_phase"] == "preferences"
    assert status["preference_missing_fields"] == ["target_roles"]
    assert status["pending_proposals"] == 0
    assert status["unresolved_conflicts"] == 0
    assert status["document_ready"] in {True, False}
    assert status["submission_ready"] is False

    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "target_roles": ["Senior Product Manager"],
                "locations": ["San Francisco Bay Area"],
                "work_modes": ["hybrid", "remote"],
                "relocation": "not_willing",
                "travel_max_percent": 20,
                "hard_exclusions": ["gambling"],
                "weighted_priorities": [
                    {"name": "mission_alignment", "weight": 5},
                    {"name": "compensation", "weight": 3},
                ],
            }
        )
    )
    saved = _invoke(workspace, ["preferences", "set", "--input", str(preferences_path)])
    assert saved.exit_code == 0, saved.output
    preference = _payload(saved)["data"]
    assert preference["hard_exclusions"] == ["gambling"]
    assert preference["weighted_priorities"][0]["weight"] == 5
    assert set(preference["defaulted_fields"]) == {"industries", "seniority"}

    shown = _invoke(workspace, ["preferences", "show"])
    assert shown.exit_code == 0, shown.output
    assert _payload(shown)["data"] == preference

    # A fresh CLI invocation derives completion from domain state; no phase ledger exists.
    completed = _invoke(workspace, ["onboarding", "status"])
    assert completed.exit_code == 0, completed.output
    completed_status = _payload(completed)["data"]
    assert completed_status["profile_review_complete"] is True
    assert completed_status["onboarding_ready"] == completed_status["core_ready"]
    assert completed_status["preference_missing_fields"] == []
    assert completed_status["preference_defaulted_fields"] == ["industries", "seniority"]
    assert not (workspace / "onboarding.json").exists()


def test_onboarding_does_not_mask_a_corrupt_workspace_marker(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "workspace.json").write_text("not-json")

    result = _invoke(workspace, ["onboarding", "status"])

    assert result.exit_code == 5
    assert _payload(result)["error"]["code"] == "integrity_error"


def test_onboarding_reports_a_corrupt_import_preview_without_a_traceback(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    assert _invoke(workspace, ["init"]).exit_code == 0
    preview = workspace / "runs" / "RUN-0001" / "import-preview.json"
    preview.parent.mkdir(parents=True)
    preview.write_text("not-json")

    result = _invoke(workspace, ["onboarding", "status"])

    assert result.exit_code == 5
    assert _payload(result)["error"]["code"] == "integrity_error"
    assert "Traceback" not in result.output
