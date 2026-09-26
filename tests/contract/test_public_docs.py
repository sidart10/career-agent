from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DOCS = {
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
    assert "career onboarding status" in onboarding
    assert "career privacy acknowledge" in onboarding


def test_upstream_notice_is_shipped_without_becoming_the_project_license() -> None:
    notice = (REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "Copyright (c) 2026 Mads Lorentzen" in notice
    assert "27eb57ae93498cddba6268d3dd84d721daa1fa0c" in notice
    assert not (REPOSITORY_ROOT / "LICENSE").exists()
