"""Workspace discovery and baseline capability reporting."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from career_agent.errors import CareerError, ErrorCode
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.paths import WorkspacePaths, check_filesystem_readiness

BASELINE_CAPABILITIES = (
    "governed_cli_mutation",
    "approval_binding",
    "pdf_rendering",
    "persisted_state_validation",
)


def workspace_root(explicit: Path | None = None) -> Path:
    """Return the configured personal workspace without creating it."""

    if explicit is not None:
        return explicit.expanduser().resolve()

    configured = os.environ.get("CAREER_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()

    return (Path.cwd() / ".career").resolve()


def doctor_report() -> dict[str, object]:
    """Describe baseline runtime facts without authenticating or mutating state."""

    return {
        "capabilities": list(BASELINE_CAPABILITIES),
        "platform": platform.system().lower(),
        "python_version": platform.python_version(),
        "workspace_path": str(workspace_root()),
    }


def initialize_workspace(root: Path) -> dict[str, object]:
    """Create the versioned single-candidate workspace layout idempotently."""

    resolved = root.expanduser().resolve(strict=False)
    check_filesystem_readiness(resolved)
    marker = resolved / "workspace.json"
    expected: dict[str, object] = {
        "schema_version": 1,
        "workspace_kind": "single_candidate",
    }
    created = not marker.exists()
    if marker.exists():
        try:
            current = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Workspace marker is unreadable or invalid",
                {"path": str(marker)},
            ) from error
        if current != expected:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Workspace marker has an unsupported version or kind",
                {"path": str(marker)},
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
        atomic_write_json(marker, expected)
    return {
        "workspace_path": str(resolved),
        "schema_version": 1,
        "created": created,
    }
