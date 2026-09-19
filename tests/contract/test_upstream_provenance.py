from __future__ import annotations

import json
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROVENANCE_PATH = REPOSITORY_ROOT / "provenance" / "upstream.json"
PARITY_PATH = REPOSITORY_ROOT / "docs" / "upstream-parity.md"

EXPECTED_CAPABILITIES = {
    "workflow.setup",
    "workflow.scrape",
    "workflow.rank",
    "workflow.apply",
    "workflow.interview",
    "workflow.outcome",
    "workflow.gmail_sync",
    "workflow.notion_sync",
    "workflow.expand",
    "workflow.upskill",
    "workflow.html_report",
    "workflow.add_template",
    "workflow.add_portal",
    "workflow.reset",
    "portal.linkedin",
    "portal.freehire",
    "portal.jobindex",
    "portal.jobnet",
    "portal.jobdanmark",
    "portal.akademikernes_jobbank",
    "tool.job_key",
    "tool.rank_state",
    "tool.verify_pdf",
    "tool.verify_layout",
    "tool.robots_check",
    "tool.salary_lookup",
    "tool.convert_salary_excel",
    "tool.lint_skills",
    "tool.security_guards",
    "tool.check_framework_version",
    "tool.check_upstream_updates",
    "tool.upstream_triage",
}
ALLOWED_DISPOSITIONS = {"preserve_v1", "redesign_v1", "defer", "remove"}


def load_provenance() -> dict[str, object]:
    return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))


def test_upstream_baseline_is_pinned() -> None:
    provenance = load_provenance()

    assert provenance["repository"] == "https://github.com/MadsLorentzen/ai-job-search"
    assert provenance["commit"] == "27eb57ae93498cddba6268d3dd84d721daa1fa0c"
    assert provenance["audited_at"] == "2026-09-15"


def test_every_audited_capability_has_one_valid_disposition_and_owner() -> None:
    provenance = load_provenance()
    capabilities = provenance["capabilities"]
    assert isinstance(capabilities, list)

    names = [item["name"] for item in capabilities]
    assert set(names) == EXPECTED_CAPABILITIES
    assert len(names) == len(set(names))
    assert all(item["disposition"] in ALLOWED_DISPOSITIONS for item in capabilities)
    assert all(re.fullmatch(r"\d{2}|post-v1", item["owner"]) for item in capabilities)


def test_parity_document_matches_machine_readable_inventory() -> None:
    provenance = load_provenance()
    parity = PARITY_PATH.read_text(encoding="utf-8")

    for capability in provenance["capabilities"]:
        expected_row = (
            f"| `{capability['name']}` | `{capability['disposition']}` | "
            f"`{capability['owner']}` |"
        )
        assert expected_row in parity


def test_provenance_contains_no_candidate_or_absolute_user_data() -> None:
    serialized = PROVENANCE_PATH.read_text(encoding="utf-8").lower()

    assert "/users/" not in serialized
    assert "candidate_name" not in serialized
    assert "candidate_email" not in serialized
    assert "candidate_phone" not in serialized
