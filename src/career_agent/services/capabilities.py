"""Runtime-neutral capability reporting and installed-skill drift detection."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from career_agent import API_VERSION, SKILL_BUNDLE_VERSION, __version__
from career_agent.errors import CareerError
from career_agent.models.base import PersistedModel
from career_agent.storage.paths import check_filesystem_readiness


class CapabilityStatus(StrEnum):
    READY = "ready"
    MISSING_REQUIRED = "missing_required"
    DISABLED_OPTIONAL = "disabled_optional"
    NEEDS_HUMAN_SETUP = "needs_human_setup"


class CapabilityCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    readiness_layer: Literal["core", "document", "submission", "optional"]
    required: bool
    status: CapabilityStatus
    provider: str = Field(min_length=1)
    degraded_workflow: str = Field(min_length=1)


class CapabilityReport(PersistedModel):
    runtime: Literal["claude_code", "codex", "unknown"]
    cli_version: str = Field(min_length=1)
    schema_version_supported: Literal[1] = 1
    capabilities: tuple[CapabilityCheck, ...]
    core_ready: bool
    document_ready: bool
    submission_ready: bool
    release_ready: bool
    degraded_workflows: tuple[str, ...]


class SkillInstallManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    product_version: str = Field(min_length=1)
    skill_bundle_version: str = Field(min_length=1)
    skill_api_version: str = Field(min_length=1)
    supported_cli_range: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    canonical_source: str = Field(min_length=1)
    source_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    installed_targets: dict[str, str] = Field(min_length=1)
    installed_modes: dict[str, Literal["canonical", "link", "mirror"]] = Field(min_length=1)
    managed_paths: tuple[str, ...]


def hash_skill_tree(root: Path) -> str:
    """Hash relative names and bytes from one canonical or mirrored skill tree."""

    resolved = root.resolve(strict=False)
    digest = hashlib.sha256()
    for path in sorted(resolved.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(resolved).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


class CapabilityService:
    def __init__(self, workspace_root: Path, repository_root: Path) -> None:
        self.workspace_root = workspace_root.resolve(strict=False)
        self.repository_root = repository_root.resolve(strict=False)
        self.skills_root = self.repository_root / ".agents" / "skills"

    @staticmethod
    def _runtime(environment: Mapping[str, str]) -> Literal["claude_code", "codex", "unknown"]:
        declared = environment.get("CAREER_RUNTIME", "").casefold()
        if declared in {"claude_code", "codex"}:
            return cast(Literal["claude_code", "codex"], declared)
        if environment.get("CODEX_HOME"):
            return "codex"
        if environment.get("CLAUDE_PROJECT_DIR"):
            return "claude_code"
        return "unknown"

    @staticmethod
    def _check(
        name: str,
        *,
        readiness_layer: Literal["core", "document", "submission", "optional"],
        required: bool,
        ready: bool,
        provider: str,
        degraded_workflow: str,
        needs_human_setup: bool = False,
    ) -> CapabilityCheck:
        if ready:
            status = CapabilityStatus.READY
        elif needs_human_setup:
            status = CapabilityStatus.NEEDS_HUMAN_SETUP
        elif required:
            status = CapabilityStatus.MISSING_REQUIRED
        else:
            status = CapabilityStatus.DISABLED_OPTIONAL
        return CapabilityCheck(
            name=name,
            readiness_layer=readiness_layer,
            required=required,
            status=status,
            provider=provider,
            degraded_workflow=degraded_workflow,
        )

    def _skill_installation(
        self,
        environment: Mapping[str, str],
        runtime: str,
    ) -> tuple[bool, str]:
        configured = environment.get("CAREER_INSTALL_MANIFEST")
        if configured:
            manifest_path = Path(configured).expanduser().resolve(strict=False)
        else:
            repository_manifest = self.repository_root / ".career-agent" / "install-manifest.json"
            workspace_manifest = self.workspace_root / ".career-agent" / "install-manifest.json"
            manifest_path = (
                repository_manifest if repository_manifest.is_file() else workspace_manifest
            )
        try:
            manifest = SkillInstallManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError):
            return False, "install-manifest-missing-or-invalid"
        if (
            manifest.product_version != __version__
            or manifest.skill_bundle_version != SKILL_BUNDLE_VERSION
            or manifest.skill_api_version != API_VERSION
            or manifest.supported_cli_range != ">=0.1.0,<0.2.0"
        ):
            return False, "skill-cli-version-incompatible"
        if Path(manifest.canonical_source).resolve(strict=False) != self.skills_root.resolve(
            strict=False
        ):
            return False, "canonical-skill-source-mismatch"
        source_checksum = hash_skill_tree(self.skills_root)
        if source_checksum != manifest.source_checksum:
            return False, "canonical-skill-source-changed"
        if runtime not in manifest.installed_targets or runtime not in manifest.installed_modes:
            return False, "runtime-skill-target-missing"
        expected_skills = tuple(
            sorted(
                path
                for path in self.skills_root.glob("career-*")
                if path.is_dir() and (path / "SKILL.md").is_file()
            )
        )
        for installed_runtime, target_text in manifest.installed_targets.items():
            target = Path(target_text).expanduser()
            mode = manifest.installed_modes.get(installed_runtime)
            if mode == "canonical":
                if target.resolve(strict=False) != self.skills_root.resolve(strict=False):
                    return False, "canonical-skill-target-mismatch"
                if hash_skill_tree(target) != source_checksum:
                    return False, "canonical-skill-source-changed"
            elif mode == "link":
                whole_tree_linked = (
                    target.is_symlink() and target.resolve() == self.skills_root.resolve()
                )
                child_links_valid = target.is_dir() and all(
                    (target / source_skill.name).is_symlink()
                    and (target / source_skill.name).resolve() == source_skill.resolve()
                    for source_skill in expected_skills
                )
                if not whole_tree_linked and not child_links_valid:
                    return False, "skill-link-invalid"
            elif mode == "mirror":
                if not target.is_dir() or any(
                    not (target / source_skill.name).is_dir()
                    or hash_skill_tree(target / source_skill.name) != hash_skill_tree(source_skill)
                    for source_skill in expected_skills
                ):
                    return False, "skill-mirror-drift"
            else:
                return False, "install-mode-invalid"
        return True, f"skill-{manifest.installed_modes[runtime]}"

    def report(
        self,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> CapabilityReport:
        env = dict(os.environ if environment is None else environment)
        runtime = self._runtime(env)
        installation_ready, installation_provider = self._skill_installation(env, runtime)
        try:
            filesystem = check_filesystem_readiness(self.workspace_root)
            writable_parent = next(
                parent
                for parent in (self.workspace_root, *self.workspace_root.parents)
                if parent.exists()
            )
            workspace_ready = os.access(writable_parent, os.W_OK)
            workspace_provider = f"local-{filesystem.filesystem_type}"
        except (CareerError, StopIteration):
            workspace_ready = False
            workspace_provider = "unsupported-filesystem"
        latex = shutil.which("lualatex", path=env.get("PATH")) or shutil.which(
            "xelatex", path=env.get("PATH")
        )
        checks = (
            self._check(
                "runtime_detection",
                readiness_layer="core",
                required=True,
                ready=runtime != "unknown",
                provider=runtime,
                degraded_workflow="all",
                needs_human_setup=runtime == "unknown",
            ),
            self._check(
                "skill_installation",
                readiness_layer="core",
                required=True,
                ready=installation_ready,
                provider=installation_provider,
                degraded_workflow="all",
            ),
            self._check(
                "workspace_mutation",
                readiness_layer="core",
                required=True,
                ready=workspace_ready,
                provider=workspace_provider,
                degraded_workflow="all",
            ),
            self._check(
                "persisted_state_validation",
                readiness_layer="core",
                required=True,
                ready=True,
                provider="pydantic-v2",
                degraded_workflow="all",
            ),
            self._check(
                "checksum_verification",
                readiness_layer="core",
                required=True,
                ready=True,
                provider="sha256-v1",
                degraded_workflow="all",
            ),
            self._check(
                "pdf_inspection",
                readiness_layer="core",
                required=True,
                ready=(
                    importlib.util.find_spec("pymupdf") is not None
                    and importlib.util.find_spec("pypdf") is not None
                ),
                provider="pymupdf+pypdf",
                degraded_workflow="documents",
            ),
            self._check(
                "latex_rendering",
                readiness_layer="document",
                required=True,
                ready=latex is not None,
                provider=latex or "no-supported-engine",
                degraded_workflow="documents",
            ),
            self._check(
                "browser_control",
                readiness_layer="submission",
                required=True,
                ready=env.get("CAREER_BROWSER_CAPABILITY") == "1",
                provider="runtime-capability-declaration",
                degraded_workflow="submission",
            ),
            self._check(
                "approval_authority",
                readiness_layer="submission",
                required=True,
                ready=env.get("CAREER_APPROVAL_CAPABILITY") == "1",
                provider="trusted-runtime-or-interactive-terminal",
                degraded_workflow="submission",
            ),
            self._check(
                "web_research",
                readiness_layer="optional",
                required=False,
                ready=env.get("CAREER_WEB_CAPABILITY") == "1",
                provider="runtime-capability-declaration",
                degraded_workflow="automated_discovery",
            ),
            self._check(
                "gmail",
                readiness_layer="optional",
                required=False,
                ready=env.get("CAREER_GMAIL_CAPABILITY") == "1",
                provider="optional-connector",
                degraded_workflow="gmail_sync",
            ),
            self._check(
                "notion",
                readiness_layer="optional",
                required=False,
                ready=env.get("CAREER_NOTION_CAPABILITY") == "1",
                provider="optional-connector",
                degraded_workflow="notion_sync",
            ),
            self._check(
                "collaboration",
                readiness_layer="optional",
                required=False,
                ready=env.get("CAREER_COLLABORATION_CAPABILITY") == "1",
                provider="runtime-capability-declaration",
                degraded_workflow="delegation",
            ),
        )
        core_ready = all(
            check.status is CapabilityStatus.READY
            for check in checks
            if check.readiness_layer == "core"
        )
        document_ready = core_ready and all(
            check.status is CapabilityStatus.READY
            for check in checks
            if check.readiness_layer == "document"
        )
        submission_ready = core_ready and all(
            check.status is CapabilityStatus.READY
            for check in checks
            if check.readiness_layer == "submission"
        )
        release_ready = core_ready and document_ready and submission_ready
        degraded = tuple(
            sorted(
                {
                    check.degraded_workflow
                    for check in checks
                    if check.status is not CapabilityStatus.READY
                }
            )
        )
        return CapabilityReport(
            runtime=runtime,
            cli_version=__version__,
            capabilities=checks,
            core_ready=core_ready,
            document_ready=document_ready,
            submission_ready=submission_ready,
            release_ready=release_ready,
            degraded_workflows=degraded,
        )
