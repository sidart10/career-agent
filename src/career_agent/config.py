"""Workspace discovery and baseline capability reporting."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Literal

from platformdirs import user_config_path, user_data_path

from career_agent.errors import CareerError, ErrorCode
from career_agent.project import project_root
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.paths import WorkspacePaths, check_filesystem_readiness, safe_resolve

BASELINE_CAPABILITIES = (
    "governed_cli_mutation",
    "approval_binding",
    "pdf_rendering",
    "persisted_state_validation",
)
_CLI_WORKSPACE: ContextVar[Path | None] = ContextVar("career_cli_workspace", default=None)


@dataclass(frozen=True)
class WorkspaceSelection:
    path: Path
    source: Literal[
        "cli", "environment", "project", "user_config", "project_default", "platform_default"
    ]


@dataclass(frozen=True)
class WorkspaceIdentity:
    path: Path
    workspace_id: str
    schema_version: int


def set_cli_workspace(path: Path | None) -> None:
    """Set the per-invocation CLI override before command dispatch."""

    _CLI_WORKSPACE.set(path)


def _config_path() -> Path:
    return user_config_path("career-agent", appauthor=False) / "config.json"


def _default_workspace() -> Path:
    return user_data_path("career-agent", appauthor=False) / "workspace"


def _configured_workspace() -> Path | None:
    path = _config_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise CareerError(
            ErrorCode.INTEGRITY_ERROR,
            "Career Agent user configuration is unreadable or invalid",
            {"path": str(path)},
        ) from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise CareerError(
            ErrorCode.INTEGRITY_ERROR,
            "Career Agent user configuration has an unsupported schema",
            {"path": str(path)},
        )
    configured = payload.get("active_workspace")
    if not isinstance(configured, str) or not configured:
        raise CareerError(
            ErrorCode.INTEGRITY_ERROR,
            "Career Agent user configuration has no active workspace",
            {"path": str(path)},
        )
    expected_workspace_id = payload.get("workspace_id")
    if not isinstance(expected_workspace_id, str):
        raise CareerError(
            ErrorCode.INTEGRITY_ERROR,
            "Career Agent user configuration has no workspace identity",
            {"path": str(path)},
        )
    identity = workspace_identity(Path(configured))
    if identity.workspace_id != expected_workspace_id:
        raise CareerError(
            ErrorCode.CONFLICT,
            "Selected workspace identity changed at the configured path",
            {
                "path": str(identity.path),
                "configured_workspace_id": expected_workspace_id,
                "observed_workspace_id": identity.workspace_id,
            },
        )
    return identity.path


def workspace_selection(
    explicit: Path | None = None,
    *,
    environment: dict[str, str] | None = None,
) -> WorkspaceSelection:
    """Resolve the active workspace with one stable, documented precedence."""

    cli_path = explicit if explicit is not None else _CLI_WORKSPACE.get()
    if cli_path is not None:
        expanded = cli_path.expanduser()
        if expanded.is_symlink():
            raise CareerError(
                ErrorCode.UNSAFE_PATH,
                "Workspace cannot be selected through a symbolic link",
                {"path": str(expanded)},
            )
        return WorkspaceSelection(expanded.resolve(strict=False), "cli")
    env = os.environ if environment is None else environment
    configured_environment = env.get("CAREER_WORKSPACE", "").strip()
    if configured_environment:
        expanded = Path(configured_environment).expanduser()
        if expanded.is_symlink():
            raise CareerError(
                ErrorCode.UNSAFE_PATH,
                "Workspace cannot be selected through a symbolic link",
                {"path": str(expanded)},
            )
        return WorkspaceSelection(
            expanded.resolve(strict=False),
            "environment",
        )
    project = project_root()
    if project is not None:
        binding = safe_resolve(project, PurePath(".career-agent/workspace.json"))
        if binding.exists():
            try:
                selected = json.loads(binding.read_text(encoding="utf-8"))
                if not isinstance(selected, dict) or selected.get("schema_version") != 1:
                    raise ValueError("Unsupported project binding")
                if not isinstance(selected.get("path"), str) or not selected["path"]:
                    raise ValueError("Missing binding path")
                path = Path(selected["path"])
                if not path.is_absolute():
                    path = safe_resolve(project, PurePath(path))
                if path.is_symlink():
                    raise CareerError(ErrorCode.UNSAFE_PATH, "Workspace binding is a symlink")
                identity = workspace_identity(path)
                if identity.workspace_id != selected["workspace_id"]:
                    raise CareerError(ErrorCode.CONFLICT, "Project workspace identity changed")
                return WorkspaceSelection(identity.path, "project")
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR, "Project workspace binding is invalid"
                ) from error
    configured = _configured_workspace()
    if configured is not None:
        return WorkspaceSelection(configured.expanduser().resolve(strict=False), "user_config")
    if project is not None:
        return WorkspaceSelection(safe_resolve(project, PurePath("workspace")), "project_default")
    return WorkspaceSelection(
        _default_workspace().expanduser().resolve(strict=False),
        "platform_default",
    )


def workspace_root(explicit: Path | None = None) -> Path:
    """Return the configured personal workspace without creating it."""

    return workspace_selection(explicit).path


def validate_project_workspace(root: Path) -> None:
    """Protect source files and detect already-tracked private workspace content."""
    project = project_root()
    if project is None or not root.is_relative_to(project):
        return
    if root != project / "workspace":
        raise CareerError(
            ErrorCode.UNSAFE_PATH, "Inside the project, use the dedicated workspace/ folder"
        )
    safe_resolve(project, PurePath("workspace"))
    if not (project / ".git").exists():
        return  # A downloaded archive has no Git index to inspect.
    if shutil.which("git") is None:
        raise CareerError(ErrorCode.NOT_READY, "Git is needed to verify this checkout's privacy")
    result = subprocess.run(
        ["git", "-C", str(project), "ls-files", "-z", "--", "workspace"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise CareerError(ErrorCode.NOT_READY, "Could not verify workspace Git tracking")
    if result.stdout:
        raise CareerError(
            ErrorCode.UNSAFE_PATH,
            "Personal workspace files are already tracked by Git; review tracking before setup",
        )


def workspace_identity(root: Path) -> WorkspaceIdentity:
    """Read and validate the stable versioned identity of an initialized workspace."""

    resolved = root.expanduser().resolve(strict=False)
    marker = safe_resolve(resolved, PurePath("workspace.json"))
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CareerError(
            ErrorCode.NOT_READY,
            "Workspace is not initialized",
            {"path": str(resolved)},
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise CareerError(
            ErrorCode.INTEGRITY_ERROR,
            "Workspace marker is unreadable or invalid",
            {"path": str(marker)},
        ) from error
    if not isinstance(payload, dict):
        raise CareerError(ErrorCode.INTEGRITY_ERROR, "Workspace marker is invalid")
    workspace_id = payload.get("workspace_id")
    try:
        parsed_id = uuid.UUID(str(workspace_id))
    except (ValueError, AttributeError) as error:
        raise CareerError(
            ErrorCode.INTEGRITY_ERROR,
            "Workspace marker has an invalid identity",
            {"path": str(marker)},
        ) from error
    if (
        payload.get("schema_version") not in {1, 2}
        or payload.get("workspace_kind") != "single_candidate"
    ):
        raise CareerError(
            ErrorCode.CONFLICT,
            "Workspace marker has an unsupported version or kind",
            {"path": str(marker)},
        )
    return WorkspaceIdentity(
        path=resolved,
        workspace_id=str(parsed_id),
        schema_version=payload["schema_version"],
    )


def select_workspace(root: Path) -> WorkspaceIdentity:
    """Bind an initialized workspace to this project, or legacy user config outside it."""

    expanded = root.expanduser()
    if expanded.is_symlink():
        raise CareerError(
            ErrorCode.UNSAFE_PATH,
            "Active workspace cannot be selected through a symbolic link",
            {"path": str(expanded)},
        )
    identity = workspace_identity(expanded)
    validate_project_workspace(identity.path)
    project = project_root()
    if project is not None:
        path_text = (
            identity.path.relative_to(project).as_posix()
            if identity.path.is_relative_to(project)
            else str(identity.path)
        )
        atomic_write_json(
            safe_resolve(project, PurePath(".career-agent/workspace.json")),
            {
                "schema_version": 1,
                "path": path_text,
                "workspace_id": identity.workspace_id,
            },
        )
        return identity
    atomic_write_json(
        _config_path(),
        {
            "schema_version": 1,
            "active_workspace": str(identity.path),
            "workspace_id": identity.workspace_id,
        },
    )
    return identity


def doctor_report() -> dict[str, object]:
    """Describe baseline runtime facts without authenticating or mutating state."""

    return {
        "capabilities": list(BASELINE_CAPABILITIES),
        "platform": platform.system().lower(),
        "python_version": platform.python_version(),
        "workspace_path": str(workspace_root()),
        "workspace_source": workspace_selection().source,
    }


def initialize_workspace(root: Path) -> dict[str, object]:
    """Create the versioned single-candidate workspace layout idempotently."""

    expanded = root.expanduser()
    if expanded.is_symlink():
        raise CareerError(ErrorCode.UNSAFE_PATH, "Workspace root cannot be a symbolic link")
    resolved = expanded.resolve(strict=False)
    if resolved in {Path(resolved.anchor), Path.home().resolve()}:
        raise CareerError(ErrorCode.UNSAFE_PATH, "Choose a dedicated career workspace folder")
    validate_project_workspace(resolved)
    check_filesystem_readiness(resolved)
    marker = safe_resolve(resolved, PurePath("workspace.json"))
    created = not marker.exists()
    if marker.exists():
        identity = workspace_identity(resolved)
    else:
        identity = WorkspaceIdentity(
            path=resolved,
            workspace_id=str(uuid.uuid4()),
            schema_version=2,
        )

    paths = WorkspacePaths.from_root(resolved)
    directories = (
        paths.profile,
        paths.resources,
        paths.opportunities,
        paths.applications,
        paths.runs,
        paths.journals,
        resolved / "inbox",
    )
    # Validate every destination before creating any directory or identity marker.
    for directory in (*directories, resolved / "README.md"):
        safe_resolve(resolved, directory.relative_to(resolved))
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    if created:
        atomic_write_json(
            marker,
            {
                "schema_version": 2,
                "workspace_id": identity.workspace_id,
                "workspace_kind": "single_candidate",
            },
        )
    guide = resolved / "README.md"
    if not guide.exists():
        from career_agent.storage.atomic import atomic_write_bytes

        atomic_write_bytes(
            guide,
            (
                "# Your career workspace\n\n"
                "Put résumés and career-history files in inbox/. Ask your agent to import them.\n"
                "profile/ holds facts and preferences; resources/ holds preserved evidence.\n"
                "opportunities/ holds jobs; applications/ holds per-job drafts and releases.\n"
                "pipeline.md is generated. runs/, journals/ and maintenance/ support recovery.\n"
                "Edit sources and ordinary drafts. Ask the agent to change governed records.\n"
                "Local plaintext: back up the whole workspace. Git ignore is not encryption.\n"
            ).encode(),
        )
    return {
        "workspace_path": str(resolved),
        "workspace_id": identity.workspace_id,
        "schema_version": identity.schema_version,
        "created": created,
    }
