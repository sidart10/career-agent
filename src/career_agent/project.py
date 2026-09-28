"""One project discovery contract; never infer a project from an arbitrary cwd."""

import tomllib
from contextvars import ContextVar
from pathlib import Path

from career_agent.errors import CareerError, ErrorCode

_PROJECT: ContextVar[Path | None] = ContextVar("career_project", default=None)


def set_project(path: Path | None) -> None:
    _PROJECT.set(path)


def is_project(path: Path) -> bool:
    try:
        metadata = tomllib.loads((path / "pyproject.toml").read_text(encoding="utf-8"))
        return (
            metadata.get("project", {}).get("name") == "career-agent"
            and (path / ".agents/skills").is_dir()
        )
    except (OSError, ValueError):
        return False


def project_root(start: Path | None = None, *, required: bool = False) -> Path | None:
    explicit = _PROJECT.get() if start is None else None
    if explicit is not None:
        root = explicit.expanduser().resolve()
        if not is_project(root):
            raise CareerError(ErrorCode.INVALID_INPUT, "--project must name a Career Agent folder")
        return root
    location = (start or Path.cwd()).resolve()
    for candidate in (location, *location.parents):
        if is_project(candidate):
            return candidate
    if required:
        raise CareerError(ErrorCode.NOT_READY, "Open the Career Agent folder or supply --project")
    return None
