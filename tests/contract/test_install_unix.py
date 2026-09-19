from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from career_agent.services.capabilities import CapabilityService, CapabilityStatus

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install.sh"


def clean_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    shutil.copytree(REPOSITORY_ROOT / "skills", source / "skills")
    for name in ("career-rules.md", "AGENTS.md", "CLAUDE.md"):
        shutil.copy2(REPOSITORY_ROOT / name, source / name)
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Contract Test",
            "-c",
            "user.email=contract@example.test",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    return source


def install(source: Path, target: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(INSTALLER),
            "--source",
            str(source),
            "--target",
            str(target),
            "--skip-python-install",
            "--skip-doctor",
            *extra,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_link_install_is_rerunnable_and_preserves_other_skills(tmp_path: Path) -> None:
    source = clean_source(tmp_path)
    target = tmp_path / "consumer"
    unrelated = target / ".agents" / "skills" / "unrelated" / "SKILL.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep me")

    first = install(source, target)
    assert first.returncode == 0, first.stderr
    manifest_path = target / ".career-agent" / "install-manifest.json"
    first_manifest = json.loads(manifest_path.read_text())
    second = install(source, target)
    assert second.returncode == 0, second.stderr
    second_manifest = json.loads(manifest_path.read_text())

    assert first_manifest["mode"] == second_manifest["mode"] == "link"
    assert first_manifest["source_checksum"] == second_manifest["source_checksum"]
    assert first_manifest["created_at"] == second_manifest["created_at"]
    assert unrelated.read_text() == "keep me"
    for runtime_dir in (".agents", ".claude"):
        installed = target / runtime_dir / "skills" / "career-setup"
        assert installed.is_symlink()
        assert installed.resolve() == (source / "skills" / "career-setup").resolve()
    assert (target / "career-rules.md").is_file()


def test_forced_mirror_recovers_staging_and_doctor_detects_drift(tmp_path: Path) -> None:
    source = clean_source(tmp_path)
    target = tmp_path / "consumer"
    interrupted = target / ".career-agent" / "install-staging" / "abandoned"
    interrupted.mkdir(parents=True)
    (interrupted / "partial").write_text("partial")
    partially_installed = target / ".agents" / "skills" / "career-setup"
    shutil.copytree(source / "skills" / "career-setup", partially_installed)

    result = install(source, target, "--force-mirror")
    assert result.returncode == 0, result.stderr
    manifest_path = target / ".career-agent" / "install-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["mode"] == "mirror"
    assert not (target / ".career-agent" / "install-staging").exists()

    installed = target / ".agents" / "skills" / "career-setup" / "SKILL.md"
    installed.write_text(installed.read_text() + "\nDRIFT\n")
    report = CapabilityService(target, source).report(
        environment={
            "CAREER_RUNTIME": "codex",
            "CAREER_INSTALL_MANIFEST": str(manifest_path),
            "CAREER_BROWSER_CAPABILITY": "1",
            "PATH": os.environ.get("PATH", ""),
        }
    )
    check = next(item for item in report.capabilities if item.name == "skill_installation")
    assert check.status is CapabilityStatus.MISSING_REQUIRED
    assert check.provider == "skill-mirror-drift"
    assert report.release_ready is False


def test_dirty_canonical_source_is_rejected(tmp_path: Path) -> None:
    source = clean_source(tmp_path)
    target = tmp_path / "consumer"
    skill = source / "skills" / "career-setup" / "SKILL.md"
    skill.write_text(skill.read_text() + "\nlocal mutation\n")

    result = install(source, target)

    assert result.returncode != 0
    assert "dirty canonical source" in result.stderr.lower()
    assert not (target / ".career-agent" / "install-manifest.json").exists()
