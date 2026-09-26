"""Workspace discovery and baseline capability reporting."""

from __future__ import annotations

import json
import os
import platform
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from platformdirs import user_config_path, user_data_path

from career_agent.errors import CareerError, ErrorCode
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.paths import WorkspacePaths, check_filesystem_readiness

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
    source: Literal["cli", "environment", "user_config", "platform_default"]


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
    configured = _configured_workspace()
    if configured is not None:
        return WorkspaceSelection(configured.expanduser().resolve(strict=False), "user_config")
    return WorkspaceSelection(
        _default_workspace().expanduser().resolve(strict=False),
        "platform_default",
    )


def workspace_root(explicit: Path | None = None) -> Path:
    """Return the configured personal workspace without creating it."""

    return workspace_selection(explicit).path


def workspace_identity(root: Path) -> WorkspaceIdentity:
    """Read and validate the stable versioned identity of an initialized workspace."""

    resolved = root.expanduser().resolve(strict=False)
    marker = resolved / "workspace.json"
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
    if payload.get("schema_version") != 1 or payload.get("workspace_kind") != "single_candidate":
        raise CareerError(
            ErrorCode.CONFLICT,
            "Workspace marker has an unsupported version or kind",
            {"path": str(marker)},
        )
    return WorkspaceIdentity(
        path=resolved,
        workspace_id=str(parsed_id),
        schema_version=1,
    )


def select_workspace(root: Path) -> WorkspaceIdentity:
    """Persist one already initialized workspace as the user-level active workspace."""

    expanded = root.expanduser()
    if expanded.is_symlink():
        raise CareerError(
            ErrorCode.UNSAFE_PATH,
            "Active workspace cannot be selected through a symbolic link",
            {"path": str(expanded)},
        )
    identity = workspace_identity(expanded)
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

    resolved = root.expanduser().resolve(strict=False)
    check_filesystem_readiness(resolved)
    marker = resolved / "workspace.json"
    created = not marker.exists()
    if marker.exists():
        identity = workspace_identity(resolved)
    else:
        identity = WorkspaceIdentity(
            path=resolved,
            workspace_id=str(uuid.uuid4()),
            schema_version=1,
        )

    paths = WorkspacePaths.from_root(resolved)
    for directory in (
        paths.profile,
        paths.resources,
        paths.opportunities,
        paths.applications,
        paths.runs,
        paths.journals,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    if created:
        atomic_write_json(
            marker,
            {
                "schema_version": 1,
                "workspace_id": identity.workspace_id,
                "workspace_kind": "single_candidate",
            },
        )
    return {
        "workspace_path": str(resolved),
        "workspace_id": identity.workspace_id,
        "schema_version": 1,
        "created": created,
    }
