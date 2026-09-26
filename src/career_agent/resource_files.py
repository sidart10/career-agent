"""Stable access to schemas and templates shipped in the installed package."""

from __future__ import annotations

from importlib.resources import files
from pathlib import PurePosixPath

from career_agent.errors import CareerError, ErrorCode

_RESOURCE_PACKAGE = "career_agent.resources"


def _validated_relative_path(relative_path: str) -> PurePosixPath:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise CareerError(
            ErrorCode.INVALID_INPUT,
            "Runtime resource path must stay inside the installed package",
            {"path": relative_path},
        )
    return path


def read_text_resource(relative_path: str) -> str:
    """Read one UTF-8 package resource without relying on repository ancestry."""

    path = _validated_relative_path(relative_path)
    resource = files(_RESOURCE_PACKAGE).joinpath(*path.parts)
    if not resource.is_file():
        raise CareerError(
            ErrorCode.NOT_READY,
            "Required runtime resource is missing from the installed package",
            {"path": relative_path},
        )
    return resource.read_text(encoding="utf-8")


def read_schema(name: str) -> str:
    """Read one exported JSON Schema by basename."""

    if PurePosixPath(name).name != name or not name.endswith(".schema.json"):
        raise CareerError(
            ErrorCode.INVALID_INPUT,
            "Schema name must be a .schema.json basename",
            {"name": name},
        )
    return read_text_resource(f"schemas/{name}")
