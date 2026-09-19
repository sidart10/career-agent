from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.atomic import atomic_write_bytes, atomic_write_json


def test_atomic_write_json_persists_deterministic_mapping(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "record.json"

    atomic_write_json(target, {"z": 1, "a": "value"})

    assert target.read_bytes() == b'{"a":"value","z":1}\n'
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_json_serializes_pydantic_model_in_json_mode(tmp_path: Path) -> None:
    target = tmp_path / "operation.json"
    operation = OperationRecord(
        run_id="RUN-0001",
        operation="application.create",
        idempotency_key="application-42",
        status=OperationStatus.STARTED,
    )

    atomic_write_json(target, operation)

    assert json.loads(target.read_text()) == operation.model_dump(mode="json")


def test_atomic_write_json_keeps_old_valid_value_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "record.json"
    target.write_text('{"state":"old"}\n')

    def fail_replace(source: str | bytes | Path, destination: str | bytes | Path) -> None:
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        atomic_write_json(target, {"state": "new"})

    assert json.loads(target.read_text()) == {"state": "old"}
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_json_does_not_touch_target_when_value_is_not_serializable(
    tmp_path: Path,
) -> None:
    target = tmp_path / "record.json"
    target.write_text('{"state":"old"}\n')

    with pytest.raises(TypeError):
        atomic_write_json(target, {"invalid": object()})

    assert json.loads(target.read_text()) == {"state": "old"}
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_bytes_replaces_content_and_applies_requested_mode(tmp_path: Path) -> None:
    target = tmp_path / "imports" / "resume.pdf"

    atomic_write_bytes(target, b"immutable source bytes", mode=0o600)

    assert target.read_bytes() == b"immutable source bytes"
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600
