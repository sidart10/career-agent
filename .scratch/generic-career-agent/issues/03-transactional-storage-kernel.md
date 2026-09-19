# 03 — Transactional Storage Kernel

Type: task
Status: ready-for-agent
Blocked by: 01, 02

## Outcome

All governed writes flow through a cross-platform storage kernel with safe path resolution, one workspace registry lock, application-scoped locks, atomic replacement, append-only journals, checksum verification, monotonic IDs, stale-lock recovery, and deterministic replay.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Safe governed mutation | internal to every mutating command | `OperationRecord` journal | Traversal, symlink escape, unsupported filesystem, or lock conflict fails before mutation | `test_paths.py`, `test_locks.py` |
| Atomic and resumable operations | rerun original command with idempotency key | journal plus checkpoint chain | Recovery yields old-valid or new-valid state, never partial state | `test_interruption_recovery.py` |
| Stable non-recycled IDs | internal allocation | sequence registry | Allocation is locked, unique, monotonic, and gap-tolerant | `test_registry.py` |

## Files

- Create: `src/career_agent/storage/paths.py`
- Create: `src/career_agent/storage/locks.py`
- Create: `src/career_agent/storage/atomic.py`
- Create: `src/career_agent/storage/checksums.py`
- Create: `src/career_agent/storage/journal.py`
- Create: `src/career_agent/storage/registry.py`
- Create: `src/career_agent/storage/repository.py`
- Create: `tests/unit/storage/test_paths.py`
- Create: `tests/unit/storage/test_locks.py`
- Create: `tests/unit/storage/test_atomic.py`
- Create: `tests/unit/storage/test_journal.py`
- Create: `tests/unit/storage/test_registry.py`
- Create: `tests/contract/test_interruption_recovery.py`

## Interfaces

```python
@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    profile: Path
    resources: Path
    opportunities: Path
    applications: Path
    runs: Path
    journals: Path

def safe_resolve(root: Path, relative: PurePath, *, allow_symlink: bool = False) -> Path: ...
def sha256_file(path: Path) -> str: ...
def atomic_write_json(path: Path, value: BaseModel | Mapping[str, object]) -> None: ...

class WorkspaceLock(AbstractContextManager[None]): ...
class ApplicationLock(AbstractContextManager[None]): ...
class OperationJournal:
    def begin(self, operation: OperationRecord) -> None: ...
    def checkpoint(self, run_id: str, name: str, data: Mapping[str, object]) -> None: ...
    def commit(self, run_id: str, result: Mapping[str, object]) -> None: ...
    def recover(self, run_id: str) -> OperationRecord: ...

class SequenceRegistry:
    def allocate_application_id(self, year: int) -> str: ...
    def allocate_local_id(self, application_id: str, kind: Literal["release", "submission"]) -> str: ...
```

## Steps

- [ ] Write failing tests for absolute paths, `..` traversal, symlink escapes, case-folding collisions, Windows reserved names, and paths that leave the workspace after resolution.
- [ ] Write multiprocessing tests for two ID allocators and two writers targeting one application; assert unique IDs, valid JSON, and no lost journal entries.
- [ ] Write interruption tests that terminate after temporary-file fsync, before replacement, after replacement, and before journal commit.
- [ ] Run `uv run pytest tests/unit/storage tests/contract/test_interruption_recovery.py -q` and confirm failure because the kernel does not exist.
- [ ] Implement root-relative path validation before any filesystem access and reject unsupported network or synchronization filesystems during readiness checks.
- [ ] Implement portalocker-based locks carrying PID, host, acquisition time, run ID, and heartbeat; stale recovery requires an expired heartbeat and proof that the owning local process is absent.
- [ ] Implement same-directory temporary writes, file fsync, atomic replacement, parent-directory fsync where supported, and explicit degradation metadata where the platform lacks directory fsync.
- [ ] Implement append-only newline-delimited JSON journals with hash chaining and idempotency keys.
- [ ] Implement non-recycling, gap-tolerant application and local sequence allocation under the appropriate lock.
- [ ] Run focused tests, then `uv run pytest -q`, `uv run ruff check .`, and `uv run mypy src`.
- [ ] Commit with `git commit -m "feat: add transactional career workspace storage"`.

## Acceptance Criteria

- Traversal and symlink escape attempts fail before mutation.
- Concurrent allocators cannot return the same ID.
- Every simulated crash recovers to the old valid state or the new valid state, never partial JSON.
- Replaying a committed idempotency key returns the existing result without duplicating IDs or journal events.

## Comments
