"""Bounded LaTeX rendering into application-owned editable drafts."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path, PurePath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import ApplicationId, PersistedModel
from career_agent.storage.atomic import atomic_write_bytes, atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry


class StructuredDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_type: Literal["resume", "cover_letter"]
    latex_source: str = Field(min_length=1)


class RenderResult(PersistedModel):
    application_id: ApplicationId
    document_type: Literal["resume", "cover_letter"]
    engine: Literal["lualatex", "xelatex"]
    source_path: str
    source_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_path: str
    artifact_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")


class DocumentRenderer:
    def __init__(self, root: Path, *, timeout: float = 60) -> None:
        self.root = root.resolve(strict=False)
        self.timeout = timeout
        self.registry = SequenceRegistry(self.root)

    @staticmethod
    def _engine() -> tuple[Literal["lualatex", "xelatex"], str]:
        for name in ("lualatex", "xelatex"):
            executable = shutil.which(name)
            if executable is not None:
                return name, executable
        raise CareerError(
            ErrorCode.NOT_READY,
            "Document rendering requires lualatex or xelatex; install one explicitly",
        )

    @staticmethod
    def _environment() -> dict[str, str]:
        allowed = ("PATH", "LANG", "LC_ALL", "TMPDIR", "TEXMFHOME", "TEXMFVAR")
        environment = {key: os.environ[key] for key in allowed if key in os.environ}
        environment["SOURCE_DATE_EPOCH"] = "0"
        return environment

    def render_draft(
        self,
        application_id: str,
        draft: StructuredDocument,
    ) -> RenderResult:
        engine, executable = self._engine()
        run_id = self.registry.allocate_run_id()
        source_path = safe_resolve(
            self.root,
            PurePath(
                "applications",
                application_id,
                "drafts",
                f"{draft.document_type}.tex",
            ),
        )
        artifact_path = source_path.with_suffix(".pdf")
        atomic_write_bytes(source_path, draft.latex_source.encode())
        run_dir = safe_resolve(self.root, PurePath("runs", run_id, "render"))
        run_source = safe_resolve(run_dir, PurePath("document.tex"))
        atomic_write_bytes(run_source, draft.latex_source.encode())
        try:
            completed = subprocess.run(
                [
                    executable,
                    "-no-shell-escape",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "document.tex",
                ],
                cwd=run_dir,
                env=self._environment(),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            rendered = safe_resolve(run_dir, PurePath("document.pdf"))
            if completed.returncode != 0 or not rendered.is_file():
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "LaTeX compilation failed; the editable source remains a draft",
                    {"application_id": application_id, "engine": engine},
                )
            atomic_write_bytes(artifact_path, rendered.read_bytes())
        except subprocess.TimeoutExpired as error:
            raise CareerError(
                ErrorCode.NOT_READY,
                "LaTeX compilation exceeded its bounded timeout",
                {"application_id": application_id, "engine": engine},
            ) from error
        finally:
            shutil.rmtree(run_dir.parent, ignore_errors=True)
        relative_source = source_path.relative_to(self.root).as_posix()
        relative_artifact = artifact_path.relative_to(self.root).as_posix()
        result = RenderResult(
            application_id=application_id,
            document_type=draft.document_type,
            engine=engine,
            source_path=relative_source,
            source_checksum=sha256_file(source_path),
            artifact_path=relative_artifact,
            artifact_checksum=sha256_file(artifact_path),
        )
        atomic_write_json(artifact_path.with_suffix(".render.json"), result)
        return result
