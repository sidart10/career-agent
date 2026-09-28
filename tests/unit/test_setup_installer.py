import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import install_support


def test_installer_rejects_failed_readiness(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {"ok": True, "data": {"capability_report": {"installation_ready": False}}}
            ),
            stderr="",
        ),
    )
    with pytest.raises(install_support.InstallError):
        install_support._run_doctor(Path("python"), tmp_path, tmp_path / "manifest.json")


def test_archive_source_revision_does_not_require_git(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("git"))
    )
    assert install_support._source_revision(tmp_path, "a" * 64) == "tree:" + "a" * 64


def test_install_lock_excludes_another_process(tmp_path):
    with install_support._installation_lock(tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from scripts.install_support import _installation_lock; "
                    "from pathlib import Path; "
                    f"\nwith _installation_lock(Path({str(tmp_path)!r})): pass"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode != 0
    assert "Another setup or uninstall" in result.stderr
    with install_support._installation_lock(tmp_path):
        pass
