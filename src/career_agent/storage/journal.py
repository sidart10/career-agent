"""Append-only operation journals with hash chaining and idempotent replay."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any, cast

import portalocker

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.paths import safe_resolve


@dataclass(frozen=True)
class JournalReplay:
    run_id: str
    result: dict[str, object]


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _integrity_error(message: str, **details: object) -> CareerError:
    return CareerError(ErrorCode.INTEGRITY_ERROR, message, dict(details))


class OperationJournal:
    def __init__(self, root: Path, *, timeout: float = 10) -> None:
        self.path = safe_resolve(root, PurePath("journals", "operations.ndjson"))
        self._guard_path = safe_resolve(root, PurePath(".locks", "journal.guard"))
        self.timeout = timeout

    def _lock(self) -> portalocker.Lock:
        self._guard_path.parent.mkdir(parents=True, exist_ok=True)
        return portalocker.Lock(self._guard_path, mode="a+", timeout=self.timeout)

    def _entries_unlocked(self) -> list[dict[str, Any]]:
        try:
            content = self.path.read_bytes()
        except FileNotFoundError:
            return []
        lines = content.splitlines(keepends=True)
        if lines and not lines[-1].endswith((b"\n", b"\r")):
            lines.pop()

        entries: list[dict[str, Any]] = []
        previous_hash: str | None = None
        for index, raw_line in enumerate(lines, start=1):
            try:
                value = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise _integrity_error("Journal contains invalid JSON", line=index) from error
            if not isinstance(value, dict):
                raise _integrity_error("Journal entry must be an object", line=index)
            entry = cast(dict[str, Any], value)
            recorded_hash = entry.get("entry_hash")
            if not isinstance(recorded_hash, str):
                raise _integrity_error("Journal entry is missing its hash", line=index)
            hash_input = {key: item for key, item in entry.items() if key != "entry_hash"}
            actual_hash = hashlib.sha256(_canonical_json(hash_input)).hexdigest()
            if recorded_hash != actual_hash:
                raise _integrity_error("Journal entry hash mismatch", line=index)
            if entry.get("previous_hash") != previous_hash:
                raise _integrity_error("Journal hash chain is broken", line=index)
            previous_hash = recorded_hash
            entries.append(entry)
        return entries

    def _repair_incomplete_tail_unlocked(self) -> None:
        try:
            content = self.path.read_bytes()
        except FileNotFoundError:
            return
        if not content or content.endswith((b"\n", b"\r")):
            return
        complete_end = content.rfind(b"\n") + 1
        with self.path.open("r+b") as stream:
            stream.truncate(complete_end)
            stream.flush()
            os.fsync(stream.fileno())

    def _append_unlocked(
        self,
        entries: list[dict[str, Any]],
        *,
        event_type: str,
        run_id: str,
        data: Mapping[str, object],
    ) -> None:
        previous_hash = entries[-1]["entry_hash"] if entries else None
        entry: dict[str, object] = {
            "event_type": event_type,
            "run_id": run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": dict(data),
            "previous_hash": previous_hash,
        }
        entry["entry_hash"] = hashlib.sha256(_canonical_json(entry)).hexdigest()
        payload = _canonical_json(entry) + b"\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    def begin(self, operation: OperationRecord) -> None:
        if operation.status is not OperationStatus.STARTED:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "A journal operation must begin in started status",
                {"run_id": operation.run_id},
            )
        with self._lock():
            self._repair_incomplete_tail_unlocked()
            entries = self._entries_unlocked()
            for entry in entries:
                if entry["event_type"] != "begin":
                    continue
                existing = OperationRecord.model_validate(entry["data"]["operation"])
                if existing.idempotency_key != operation.idempotency_key:
                    continue
                if existing.run_id == operation.run_id and existing == operation:
                    return
                terminal = any(
                    candidate["event_type"] in {"commit", "failure"}
                    and candidate["run_id"] == existing.run_id
                    for candidate in entries
                )
                if terminal:
                    return
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Idempotency key belongs to an in-progress operation",
                    {
                        "idempotency_key": operation.idempotency_key,
                        "owner_run_id": existing.run_id,
                    },
                )
            self._append_unlocked(
                entries,
                event_type="begin",
                run_id=operation.run_id,
                data={"operation": operation.model_dump(mode="json")},
            )

    def checkpoint(self, run_id: str, name: str, data: Mapping[str, object]) -> None:
        with self._lock():
            self._repair_incomplete_tail_unlocked()
            entries = self._entries_unlocked()
            self._require_started(entries, run_id)
            for entry in entries:
                if (
                    entry["event_type"] == "checkpoint"
                    and entry["run_id"] == run_id
                    and entry["data"].get("name") == name
                ):
                    if entry["data"].get("value") == dict(data):
                        return
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Checkpoint name already has different data",
                        {"run_id": run_id, "checkpoint": name},
                    )
            if self._is_committed(entries, run_id) or self._is_failed(entries, run_id):
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Cannot checkpoint a terminal operation",
                    {"run_id": run_id},
                )
            self._append_unlocked(
                entries,
                event_type="checkpoint",
                run_id=run_id,
                data={"name": name, "value": dict(data)},
            )

    def commit(self, run_id: str, result: Mapping[str, object]) -> None:
        with self._lock():
            self._repair_incomplete_tail_unlocked()
            entries = self._entries_unlocked()
            self._require_started(entries, run_id)
            for entry in entries:
                if entry["event_type"] == "commit" and entry["run_id"] == run_id:
                    if entry["data"].get("result") == dict(result):
                        return
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Operation already committed with a different result",
                        {"run_id": run_id},
                    )
            if self._is_failed(entries, run_id):
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Cannot commit a failed operation",
                    {"run_id": run_id},
                )
            self._append_unlocked(
                entries,
                event_type="commit",
                run_id=run_id,
                data={"result": dict(result)},
            )

    def fail(self, run_id: str, details: Mapping[str, object]) -> None:
        """Mark an operation terminally failed without treating it as replayable success."""

        with self._lock():
            self._repair_incomplete_tail_unlocked()
            entries = self._entries_unlocked()
            self._require_started(entries, run_id)
            for entry in entries:
                if entry["event_type"] == "failure" and entry["run_id"] == run_id:
                    if entry["data"].get("details") == dict(details):
                        return
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Operation already failed with different details",
                        {"run_id": run_id},
                    )
            if self._is_committed(entries, run_id):
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Cannot fail a committed operation",
                    {"run_id": run_id},
                )
            self._append_unlocked(
                entries,
                event_type="failure",
                run_id=run_id,
                data={"details": dict(details)},
            )

    def recover(self, run_id: str) -> OperationRecord:
        with self._lock():
            entries = self._entries_unlocked()
        begin = next(
            (
                entry
                for entry in entries
                if entry["event_type"] == "begin" and entry["run_id"] == run_id
            ),
            None,
        )
        if begin is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Unknown operation run ID",
                {"run_id": run_id},
            )
        operation = OperationRecord.model_validate(begin["data"]["operation"])
        checkpoints = tuple(
            str(entry["data"]["name"])
            for entry in entries
            if entry["event_type"] == "checkpoint" and entry["run_id"] == run_id
        )
        commit = next(
            (
                entry
                for entry in entries
                if entry["event_type"] == "commit" and entry["run_id"] == run_id
            ),
            None,
        )
        failure = next(
            (
                entry
                for entry in entries
                if entry["event_type"] == "failure" and entry["run_id"] == run_id
            ),
            None,
        )
        if commit is None:
            if failure is None:
                return operation.model_copy(update={"checkpoints": checkpoints})
            return operation.model_copy(
                update={
                    "status": OperationStatus.FAILED,
                    "checkpoints": checkpoints,
                    "updated_at": datetime.fromisoformat(failure["timestamp"]),
                }
            )
        result = commit["data"]["result"]
        references = tuple(str(item) for item in result.get("result_references", []))
        return operation.model_copy(
            update={
                "status": OperationStatus.COMMITTED,
                "checkpoints": checkpoints,
                "result_references": references,
                "updated_at": datetime.fromisoformat(commit["timestamp"]),
            }
        )

    def replay(self, idempotency_key: str) -> JournalReplay | None:
        with self._lock():
            entries = self._entries_unlocked()
        for entry in entries:
            if entry["event_type"] != "begin":
                continue
            operation = OperationRecord.model_validate(entry["data"]["operation"])
            if operation.idempotency_key != idempotency_key:
                continue
            commit = next(
                (
                    candidate
                    for candidate in entries
                    if candidate["event_type"] == "commit"
                    and candidate["run_id"] == operation.run_id
                ),
                None,
            )
            if commit is None:
                return None
            return JournalReplay(
                run_id=operation.run_id,
                result=cast(dict[str, object], commit["data"]["result"]),
            )
        return None

    def operation_for_key(self, idempotency_key: str) -> OperationRecord | None:
        """Return the original record for an in-progress or committed idempotency key."""

        with self._lock():
            entries = self._entries_unlocked()
        for entry in entries:
            if entry["event_type"] != "begin":
                continue
            operation = OperationRecord.model_validate(entry["data"]["operation"])
            if operation.idempotency_key == idempotency_key:
                return operation
        return None

    def operations(self) -> tuple[OperationRecord, ...]:
        """Return every journaled operation with its current durable status."""

        with self._lock():
            entries = self._entries_unlocked()
        operations: list[OperationRecord] = []
        for begin in entries:
            if begin["event_type"] != "begin":
                continue
            operation = OperationRecord.model_validate(begin["data"]["operation"])
            checkpoints = tuple(
                str(entry["data"]["name"])
                for entry in entries
                if entry["event_type"] == "checkpoint" and entry["run_id"] == operation.run_id
            )
            commit = next(
                (
                    entry
                    for entry in entries
                    if entry["event_type"] == "commit" and entry["run_id"] == operation.run_id
                ),
                None,
            )
            failure = next(
                (
                    entry
                    for entry in entries
                    if entry["event_type"] == "failure" and entry["run_id"] == operation.run_id
                ),
                None,
            )
            if commit is None:
                if failure is None:
                    operations.append(operation.model_copy(update={"checkpoints": checkpoints}))
                else:
                    operations.append(
                        operation.model_copy(
                            update={
                                "status": OperationStatus.FAILED,
                                "checkpoints": checkpoints,
                                "updated_at": datetime.fromisoformat(failure["timestamp"]),
                            }
                        )
                    )
                continue
            result = commit["data"]["result"]
            operations.append(
                operation.model_copy(
                    update={
                        "status": OperationStatus.COMMITTED,
                        "checkpoints": checkpoints,
                        "result_references": tuple(
                            str(item) for item in result.get("result_references", [])
                        ),
                        "updated_at": datetime.fromisoformat(commit["timestamp"]),
                    }
                )
            )
        return tuple(operations)

    def checkpoint_data(self, run_id: str, name: str) -> dict[str, object] | None:
        """Read the immutable payload for a named checkpoint."""

        with self._lock():
            entries = self._entries_unlocked()
        for entry in entries:
            if (
                entry["event_type"] == "checkpoint"
                and entry["run_id"] == run_id
                and entry["data"].get("name") == name
            ):
                return cast(dict[str, object], entry["data"]["value"])
        return None

    @staticmethod
    def _is_committed(entries: list[dict[str, Any]], run_id: str) -> bool:
        return any(
            entry["event_type"] == "commit" and entry["run_id"] == run_id for entry in entries
        )

    @staticmethod
    def _is_failed(entries: list[dict[str, Any]], run_id: str) -> bool:
        return any(
            entry["event_type"] == "failure" and entry["run_id"] == run_id for entry in entries
        )

    @staticmethod
    def _require_started(entries: list[dict[str, Any]], run_id: str) -> None:
        if not any(
            entry["event_type"] == "begin" and entry["run_id"] == run_id for entry in entries
        ):
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Operation has not begun",
                {"run_id": run_id},
            )
