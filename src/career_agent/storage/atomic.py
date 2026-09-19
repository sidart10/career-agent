"""Crash-safe same-directory replacement for governed JSON files."""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_REPLACE_ATTEMPTS = 20 if os.name == "nt" else 1


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


def _replace_with_retry(source: Path, destination: Path) -> None:
    delay = 0.005
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt + 1 == _REPLACE_ATTEMPTS:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.05)


def atomic_write_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Fsync bytes in a sibling temporary file and atomically replace ``path``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _replace_with_retry(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, value: BaseModel | Mapping[str, object]) -> None:
    """Serialize fully, then atomically replace ``path`` with owner-only JSON."""

    atomic_write_bytes(path, _json_bytes(value))
