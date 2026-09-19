"""Crash-safe same-directory replacement for governed JSON files."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    serializable: Any = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    encoded = json.dumps(
        serializable,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{encoded}\n".encode()


def _fsync_directory(path: Path) -> bool:
    if os.name == "nt" or not hasattr(os, "O_DIRECTORY"):
        return False
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def atomic_write_json(path: Path, value: BaseModel | Mapping[str, object]) -> None:
    """Serialize fully, fsync a sibling temporary file, and atomically replace ``path``."""

    payload = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
