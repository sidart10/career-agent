from __future__ import annotations

import json
import re
from pathlib import Path

from career_agent.services.preferences import PreferenceInput

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DOCS = {
    "agent-workflows.md",
    "architecture.md",
    "compatibility.md",
    "configuration.md",
    "contributing.md",
    "evidence-and-approval.md",
    "first-application.md",
    "installation.md",
    "onboarding.md",
    "release.md",
    "security-and-privacy.md",
    "support.md",
    "troubleshooting.md",
    "workspace-and-state.md",
}


def test_public_documentation_surface_is_complete_and_truthful() -> None:
    docs = REPOSITORY_ROOT / "docs"
    assert REQUIRED_DOCS.issubset({path.name for path in docs.glob("*.md")})

    package_readme = (docs / "package-readme.md").read_text(encoding="utf-8")
    security = (docs / "security-and-privacy.md").read_text(encoding="utf-8")
    installation = (docs / "installation.md").read_text(encoding="utf-8")
    onboarding = (docs / "onboarding.md").read_text(encoding="utf-8")

    assert "repository-local early access" in package_readme
    assert "experimental" in package_readme
    assert "not open source" in package_readme
    assert "plaintext" in security
    assert "model provider" in security
    assert "scripts/install.sh" in installation
    assert "scripts/install.ps1" in installation
    assert "onboarding status --json" in onboarding
    assert "consent" in onboarding
    assert "agent-workflows.md" in onboarding
    assert "<release-tag>" not in installation
    assert "scripts/career.sh" in installation
    assert "scripts/career.ps1" in installation


def test_public_docs_have_resolving_local_links_and_valid_preferences_example() -> None:
    paths = [REPOSITORY_ROOT / "README.md", *sorted((REPOSITORY_ROOT / "docs").glob("*.md"))]
    for path in paths:
        body = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            local = target.split("#")[0]
            assert (path.parent / local).exists(), f"Broken link in {path.name}: {target}"
    examples = (REPOSITORY_ROOT / "docs/agent-workflows.md").read_text(encoding="utf-8")
    request = re.search(r"```json\n(.*?)\n```", examples, re.DOTALL)
    assert request is not None
    PreferenceInput.model_validate(json.loads(request.group(1)))


def test_upstream_notice_is_shipped_without_becoming_the_project_license() -> None:
    notice = (REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "Copyright (c) 2026 Mads Lorentzen" in notice
    assert "27eb57ae93498cddba6268d3dd84d721daa1fa0c" in notice
    assert not (REPOSITORY_ROOT / "LICENSE").exists()
