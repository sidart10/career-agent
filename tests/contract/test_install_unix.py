from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from career_agent.services.capabilities import CapabilityService, CapabilityStatus

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Unix installer contract")

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install.sh"


def clean_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    shutil.copytree(REPOSITORY_ROOT / ".agents" / "skills", source / ".agents" / "skills")
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


def install(source: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(INSTALLER),
            "--source",
            str(source),
            "--target",
            str(source),
            "--skip-python-install",
            "--skip-doctor",
            *extra,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_repo_local_install_is_rerunnable_and_preserves_unrelated_skills(tmp_path: Path) -> None:
    source = clean_source(tmp_path)
    unrelated = source / ".claude" / "skills" / "unrelated" / "SKILL.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep me")

    first = install(source)
    assert first.returncode == 0, first.stderr
    manifest_path = source / ".career-agent" / "install-manifest.json"
    first_manifest = json.loads(manifest_path.read_text())
    second = install(source)
    assert second.returncode == 0, second.stderr
    second_manifest = json.loads(manifest_path.read_text())

    assert first_manifest["installed_modes"] == {
        "claude_code": "link",
        "codex": "canonical",
    }
    assert first_manifest["source_checksum"] == second_manifest["source_checksum"]
    assert first_manifest["created_at"] == second_manifest["created_at"]
    assert first_manifest["source_revision"]
    assert first_manifest["skill_bundle_version"] == "0.1.0"
    assert unrelated.read_text() == "keep me"
    canonical = source / ".agents" / "skills" / "career-onboard"
    assert canonical.is_dir() and not canonical.is_symlink()
    installed = source / ".claude" / "skills" / "career-onboard"
    assert installed.is_symlink()
    assert not Path(os.readlink(installed)).is_absolute()
    assert installed.resolve() == canonical.resolve()


def test_forced_mirror_recovers_staging_and_doctor_detects_drift(tmp_path: Path) -> None:
    source = clean_source(tmp_path)
    interrupted = source / ".career-agent" / "install-staging" / "abandoned"
    interrupted.mkdir(parents=True)
    (interrupted / "partial").write_text("partial")

    result = install(source, "--force-mirror")
    assert result.returncode == 0, result.stderr
    manifest_path = source / ".career-agent" / "install-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["installed_modes"]["claude_code"] == "mirror"
    assert not (source / ".career-agent" / "install-staging").exists()

    installed = source / ".claude" / "skills" / "career-onboard" / "SKILL.md"
    installed.write_text(installed.read_text() + "\nDRIFT\n")
    report = CapabilityService(tmp_path / "workspace", source).report(
        environment={
            "CAREER_RUNTIME": "claude_code",
            "CAREER_INSTALL_MANIFEST": str(manifest_path),
            "PATH": os.environ.get("PATH", ""),
        }
    )
    check = next(item for item in report.capabilities if item.name == "skill_installation")
    assert check.status is CapabilityStatus.MISSING_REQUIRED
    assert check.provider == "skill-mirror-drift"


def test_failed_reinstall_rolls_back_every_managed_skill(tmp_path: Path) -> None:
    source = clean_source(tmp_path)
    assert install(source).returncode == 0
    before = {
        path.name: os.readlink(path) for path in (source / ".claude" / "skills").glob("career-*")
    }

    failed = install(source, "--simulate-failure-after", "2")

    assert failed.returncode != 0
    after = {
        path.name: os.readlink(path) for path in (source / ".claude" / "skills").glob("career-*")
    }
    assert after == before
    assert not (source / ".career-agent" / "install-staging").exists()


def test_failed_post_install_validation_restores_prior_install(tmp_path: Path) -> None:
    source = clean_source(tmp_path)
    assert install(source).returncode == 0
    manifest_path = source / ".career-agent" / "install-manifest.json"
    manifest_before = manifest_path.read_bytes()
    links_before = {
        path.name: os.readlink(path) for path in (source / ".claude" / "skills").glob("career-*")
    }

    failed = install(
        source,
        "--force-mirror",
        "--simulate-validation-failure",
    )

    assert failed.returncode != 0
    assert "simulated post-install validation failure" in failed.stderr.lower()
    assert manifest_path.read_bytes() == manifest_before
    links_after = {
        path.name: os.readlink(path) for path in (source / ".claude" / "skills").glob("career-*")
    }
    assert links_after == links_before
    assert not (source / ".career-agent" / "install-staging").exists()


def test_uninstall_removes_only_manifest_owned_paths(tmp_path: Path) -> None:
    source = clean_source(tmp_path)
    unrelated = source / ".claude" / "skills" / "unrelated" / "SKILL.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep me")
    assert install(source).returncode == 0

    result = install(source, "--uninstall")

    assert result.returncode == 0, result.stderr
    assert unrelated.read_text() == "keep me"
    assert not list((source / ".claude" / "skills").glob("career-*"))
    assert not (source / ".career-agent" / "install-manifest.json").exists()
    assert (source / ".agents" / "skills" / "career-onboard" / "SKILL.md").is_file()


def test_dirty_canonical_source_is_rejected(tmp_path: Path) -> None:
    source = clean_source(tmp_path)
    skill = source / ".agents" / "skills" / "career-onboard" / "SKILL.md"
    skill.write_text(skill.read_text() + "\nlocal mutation\n")

    result = install(source)

    assert result.returncode != 0
    assert "dirty canonical source" in result.stderr.lower()
    assert not (source / ".career-agent" / "install-manifest.json").exists()
