from __future__ import annotations

from pathlib import Path

from scripts import install_support


def test_python_tool_snapshot_restores_environment_and_executable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    environment = tmp_path / "tools" / "career-agent"
    executable = tmp_path / "bin" / "career"
    environment.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    (environment / "receipt.toml").write_text("version = 'old'\n")
    executable.write_text("old executable")
    monkeypatch.setattr(
        install_support,
        "_uv_tool_paths",
        lambda: (environment, executable),
    )

    snapshot = install_support._snapshot_python_install()
    (environment / "receipt.toml").write_text("version = 'new'\n")
    executable.write_text("new executable")

    install_support._restore_python_install(snapshot)
    install_support._discard_python_snapshot(snapshot)

    assert (environment / "receipt.toml").read_text() == "version = 'old'\n"
    assert executable.read_text() == "old executable"
    assert not snapshot.backup_root.exists()


def test_python_tool_snapshot_removes_failed_fresh_install(
    tmp_path: Path,
    monkeypatch,
) -> None:
    environment = tmp_path / "tools" / "career-agent"
    executable = tmp_path / "bin" / "career"
    monkeypatch.setattr(
        install_support,
        "_uv_tool_paths",
        lambda: (environment, executable),
    )

    snapshot = install_support._snapshot_python_install()
    environment.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    (environment / "receipt.toml").write_text("version = 'partial'\n")
    executable.write_text("partial executable")

    install_support._restore_python_install(snapshot)
    install_support._discard_python_snapshot(snapshot)

    assert not environment.exists()
    assert not executable.exists()
    assert not snapshot.backup_root.exists()
