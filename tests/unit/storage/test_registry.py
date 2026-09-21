from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.storage.registry import SequenceRegistry


def _allocate_application_ids(root: str, count: int, output: multiprocessing.Queue[str]) -> None:
    registry = SequenceRegistry(Path(root))
    for _ in range(count):
        output.put(registry.allocate_application_id(2026))


def test_application_ids_are_monotonic_and_year_scoped(tmp_path: Path) -> None:
    registry = SequenceRegistry(tmp_path)

    assert registry.allocate_application_id(2026) == "APP-2026-0001"
    assert registry.allocate_application_id(2026) == "APP-2026-0002"
    assert registry.allocate_application_id(2027) == "APP-2027-0001"


def test_local_ids_are_monotonic_per_application_and_kind(tmp_path: Path) -> None:
    registry = SequenceRegistry(tmp_path)

    assert registry.allocate_local_id("APP-2026-0001", "release") == "REL-0001"
    assert registry.allocate_local_id("APP-2026-0001", "release") == "REL-0002"
    assert registry.allocate_local_id("APP-2026-0001", "submission") == "SUB-0001"
    assert registry.allocate_local_id("APP-2026-0002", "release") == "REL-0001"


def test_concurrent_application_allocators_return_unique_ids(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    output: multiprocessing.Queue[str] = context.Queue()
    workers = [
        context.Process(target=_allocate_application_ids, args=(str(tmp_path), 10, output))
        for _ in range(2)
    ]

    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0

    allocated = sorted(output.get(timeout=1) for _ in range(20))
    assert allocated == [f"APP-2026-{number:04d}" for number in range(1, 21)]
    persisted = json.loads((tmp_path / "registry.json").read_text())
    assert persisted["application_sequences"] == {"2026": 20}


def test_exhausted_application_sequence_fails_without_changing_registry(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "application_sequences": {"2026": 9999},
                "local_sequences": {},
            }
        )
    )
    registry = SequenceRegistry(tmp_path)

    with pytest.raises(CareerError) as error:
        registry.allocate_application_id(2026)

    assert error.value.code is ErrorCode.CONFLICT
    assert json.loads(path.read_text())["application_sequences"]["2026"] == 9999


def test_exhausted_local_sequence_fails_without_changing_registry(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "application_sequences": {},
                "local_sequences": {"APP-2026-0001": {"release": 9999}},
            }
        )
    )
    registry = SequenceRegistry(tmp_path)

    with pytest.raises(CareerError) as error:
        registry.allocate_local_id("APP-2026-0001", "release")

    assert error.value.code is ErrorCode.CONFLICT
    assert json.loads(path.read_text())["local_sequences"]["APP-2026-0001"]["release"] == 9999
