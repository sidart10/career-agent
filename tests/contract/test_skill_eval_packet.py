from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_every_public_skill_has_versioned_trigger_and_nontrigger_cases() -> None:
    packet = json.loads(
        (REPOSITORY_ROOT / "evals" / "skill-cases.json").read_text(encoding="utf-8")
    )
    skills = {
        path.parent.name for path in (REPOSITORY_ROOT / ".agents" / "skills").glob("*/SKILL.md")
    }

    assert packet["schema_version"] == 1
    assert packet["prompt_set_revision"]
    assert len({case["id"] for case in packet["cases"]}) == len(packet["cases"])
    for skill in skills:
        cases = [case for case in packet["cases"] if case["skill"] == skill]
        assert {case["kind"] for case in cases} == {"positive", "ambiguous", "negative"}
        assert all(case["expected_trigger"] is (case["kind"] != "negative") for case in cases)
