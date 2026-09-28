from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPOSITORY_ROOT / ".agents" / "skills"
EXPECTED_SKILLS = {
    "career-setup",
    "career-onboard",
    "career-discover",
    "career-rank",
    "career-apply",
    "career-pipeline",
    "career-reset",
    "career-doctor",
}
REQUIRED_SECTIONS = {
    "## Capabilities",
    "## Workflow",
    "## Human gates",
    "## Untrusted content",
    "## Recovery",
}


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(?P<body>.*?)\n---\n", text, re.DOTALL)
    assert match is not None, "SKILL.md requires YAML frontmatter"
    values: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values


def test_portable_skills_have_one_policy_safe_canonical_source() -> None:
    skill_paths = sorted(SKILLS_ROOT.glob("*/SKILL.md"))

    assert {path.parent.name for path in skill_paths} == EXPECTED_SKILLS
    for path in skill_paths:
        text = path.read_text(encoding="utf-8")
        metadata = _frontmatter(text)
        assert metadata["name"] == path.parent.name
        assert metadata["description"]
        assert {
            line.strip() for line in text.splitlines() if line.startswith("## ")
        } >= REQUIRED_SECTIONS
        assert "career " in text
        assert "--json" in text
        assert "governed state" in text.casefold()
        assert "directly edit" in text.casefold()
        assert "untrusted" in text.casefold()
        reference = path.parent / "references" / "career-rules.md"
        assert reference.read_text(encoding="utf-8") == (
            REPOSITORY_ROOT / "career-rules.md"
        ).read_text(encoding="utf-8")
        assert "references/career-rules.md" in text
        assert not re.search(r"\b(mcp__|computer\.|browser\.|claude code|codex)\b", text, re.I)


def test_shared_rules_are_loaded_without_policy_duplication() -> None:
    rules = (REPOSITORY_ROOT / "career-rules.md").read_text(encoding="utf-8")
    agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    claude = (REPOSITORY_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "single final approval" in rules.casefold()
    assert "untrusted data" in rules.casefold()
    assert "governed state" in rules.casefold()
    assert agents == claude
    assert "Read and follow `career-rules.md` before career work." in agents
    assert ".agents/skills/career-onboard/SKILL.md" in agents
    assert "before installation" in agents
    assert "docs/agent-workflows.md" in agents
    assert "scripts/career.sh" in rules and "scripts/career.ps1" in rules


def test_canonical_skills_are_tracked_while_generated_claude_links_are_ignored() -> None:
    gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "!.agents/skills/" in gitignore
    assert ".claude/skills/" in gitignore
