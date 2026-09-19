"""Cross-platform workspace and application locks with auditable ownership."""

from __future__ import annotations

import json
import os
import re
import socket
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePath
from types import TracebackType
from typing import Any

import portalocker

from career_agent.errors import CareerError, ErrorCode
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.paths import safe_resolve

_APPLICATION_ID = re.compile(r"^APP-\d{4}-\d{4}$")


def _read_metadata(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class _OwnedLock(AbstractContextManager[None]):
    def __init__(
        self,
        root: Path,
        relative_path: PurePath,
        *,
        run_id: str,
        scope: str,
        timeout: float,
        stale_after: timedelta,
    ) -> None:
        self.path = safe_resolve(root, relative_path)
        self._guard_path = self.path.with_suffix(f"{self.path.suffix}.guard")
        self.run_id = run_id
        self.scope = scope
        self.timeout = timeout
        self.stale_after = stale_after
        self.recovered_stale = False
        self._lock: portalocker.Lock | None = None

    def _recoverable_owner(self, owner: dict[str, Any]) -> dict[str, Any] | None:
        if not owner or owner.get("released_at") is not None:
            return None
        if owner.get("host") != socket.gethostname():
            return None
        heartbeat_text = owner.get("heartbeat_at")
        pid = owner.get("pid")
        if not isinstance(heartbeat_text, str) or not isinstance(pid, int):
            return None
        try:
            heartbeat = datetime.fromisoformat(heartbeat_text)
        except ValueError:
            return None
        if heartbeat.tzinfo is None:
            return None
        if datetime.now(UTC) - heartbeat.astimezone(UTC) <= self.stale_after:
            return None
        if _process_exists(pid):
            return None
        return owner

    def __enter__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._guard_path.touch(mode=0o600, exist_ok=True)
        lock = portalocker.Lock(
            self._guard_path,
            mode="r+",
            timeout=self.timeout,
            fail_when_locked=False,
        )
        try:
            lock.acquire()
        except portalocker.exceptions.LockException as error:
            owner = _read_metadata(self.path)
            raise CareerError(
                ErrorCode.CONFLICT,
                f"The {self.scope} is locked by another operation",
                {
                    "scope": self.scope,
                    "owner_run_id": owner.get("run_id"),
                    "owner_pid": owner.get("pid"),
                    "owner_host": owner.get("host"),
                },
            ) from error

        self._lock = lock
        prior_owner = _read_metadata(self.path)
        recovered_owner = self._recoverable_owner(prior_owner)
        self.recovered_stale = recovered_owner is not None
        now = datetime.now(UTC).isoformat()
        metadata: dict[str, object] = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "run_id": self.run_id,
            "scope": self.scope,
            "acquired_at": now,
            "heartbeat_at": now,
        }
        if recovered_owner is not None:
            metadata["recovered_owner"] = recovered_owner
        try:
            atomic_write_json(self.path, metadata)
        except BaseException:
            lock.release()
            self._lock = None
            raise
        return None

    def heartbeat(self) -> None:
        if self._lock is None:
            raise RuntimeError("Cannot heartbeat a lock that is not held")
        metadata = _read_metadata(self.path)
        metadata["heartbeat_at"] = datetime.now(UTC).isoformat()
        atomic_write_json(self.path, metadata)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._lock is None:
            return None
        try:
            metadata = _read_metadata(self.path)
            metadata["released_at"] = datetime.now(UTC).isoformat()
            atomic_write_json(self.path, metadata)
        finally:
            self._lock.release()
            self._lock = None
        return None


class WorkspaceLock(_OwnedLock):
    def __init__(
        self,
        root: Path,
        *,
        run_id: str,
        timeout: float = 10,
        stale_after: timedelta = timedelta(minutes=5),
    ) -> None:
        super().__init__(
            root,
            PurePath(".locks", "workspace.lock"),
            run_id=run_id,
            scope="workspace",
            timeout=timeout,
            stale_after=stale_after,
        )


class ApplicationLock(_OwnedLock):
    def __init__(
        self,
        root: Path,
        application_id: str,
        *,
        run_id: str,
        timeout: float = 10,
        stale_after: timedelta = timedelta(minutes=5),
    ) -> None:
        if _APPLICATION_ID.fullmatch(application_id) is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Invalid application ID for lock scope",
                {"application_id": application_id},
            )
        super().__init__(
            root,
            PurePath(".locks", "applications", f"{application_id}.lock"),
            run_id=run_id,
            scope=application_id,
            timeout=timeout,
            stale_after=stale_after,
        )
