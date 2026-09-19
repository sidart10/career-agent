from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from career_agent.documents.render import DocumentRenderer, StructuredDocument
from career_agent.errors import CareerError, ErrorCode


def test_missing_tex_engine_fails_readiness_without_creating_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("career_agent.documents.render.shutil.which", lambda _name: None)
    renderer = DocumentRenderer(tmp_path)

    with pytest.raises(CareerError) as error:
        renderer.render_draft(
            "APP-2026-0001",
            StructuredDocument(document_type="resume", latex_source="\\documentclass{article}"),
        )

    assert error.value.code is ErrorCode.NOT_READY
    assert not (tmp_path / "applications" / "APP-2026-0001" / "drafts").exists()


def test_render_uses_argument_array_sanitized_environment_and_managed_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "career_agent.documents.render.shutil.which",
        lambda name: f"/usr/local/bin/{name}" if name == "lualatex" else None,
    )
    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed.update(command=command, cwd=cwd, env=env, timeout=timeout, check=check)
        (cwd / "document.pdf").write_bytes(b"%PDF-1.7\nsynthetic")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("career_agent.documents.render.subprocess.run", fake_run)
    result = DocumentRenderer(tmp_path).render_draft(
        "APP-2026-0001",
        StructuredDocument(
            document_type="resume",
            latex_source="\\documentclass{article}\n\\begin{document}A\\end{document}",
        ),
    )

    assert observed["command"] == [
        "/usr/local/bin/lualatex",
        "-no-shell-escape",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "document.tex",
    ]
    assert isinstance(observed["cwd"], Path)
    assert str(observed["cwd"]).startswith(str(tmp_path / "runs"))
    assert "PYTHONPATH" not in observed["env"]
    assert result.engine == "lualatex"
    assert result.source_path == "applications/APP-2026-0001/drafts/resume.tex"
    assert result.artifact_path == "applications/APP-2026-0001/drafts/resume.pdf"
    assert (tmp_path / result.artifact_path).read_bytes().startswith(b"%PDF")
    assert (tmp_path / result.artifact_path).with_suffix(".render.json").is_file()
    assert not Path(observed["cwd"]).exists()


def test_compiler_failure_stays_in_drafts_and_returns_safe_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "career_agent.documents.render.shutil.which",
        lambda name: f"/usr/local/bin/{name}" if name == "xelatex" else None,
    )

    def fail(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, stdout="", stderr="Undefined control sequence")

    monkeypatch.setattr("career_agent.documents.render.subprocess.run", fail)

    with pytest.raises(CareerError) as error:
        DocumentRenderer(tmp_path).render_draft(
            "APP-2026-0001",
            StructuredDocument(document_type="resume", latex_source="bad source"),
        )

    assert error.value.code is ErrorCode.INVALID_INPUT
    assert "bad source" not in str(error.value)
    assert not list((tmp_path / "applications" / "APP-2026-0001").rglob("*.pdf"))
