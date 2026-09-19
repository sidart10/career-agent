"""Workspace discovery and baseline capability reporting."""

from __future__ import annotations

import os
import platform
from pathlib import Path

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
