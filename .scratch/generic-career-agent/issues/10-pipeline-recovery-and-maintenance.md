# 10 — Pipeline, Recovery, Migration, Cleanup, and Reset

Type: task
Status: resolved
Blocked by: 03, 09

## Outcome

The local pipeline is a deterministic disposable projection. Startup recovery, cleanup, schema migration, and scoped reset operate through previewed, journaled plans and cannot erase releases, submission evidence, imports, or remote data accidentally.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Disposable pipeline | `career pipeline build` | generated Markdown only | Regeneration from manifests/journals is deterministic | `test_pipeline_projection.py` |
| Crash recovery | implicit startup recovery | recovery report and journals | Unsafe ambiguity is quarantined instead of guessed | `test_recovery_cli.py` |
| Expiring temporary data | `career cleanup` | `CleanupPlan` | Protected history and symlink targets are excluded | `test_cleanup.py` |
| Recoverable schema change | `career migrate plan|apply` | `MigrationPlan` and backup manifest | Digest change or validation failure aborts/restores | `test_migrations.py` |
| Scoped destruction | `career reset preview|apply` | `ResetPlan` | Exact unchanged scope required; remote/protected deletion separate | `test_reset.py` |

## Files

- Create: `src/career_agent/projections/pipeline.py`
- Create: `src/career_agent/services/recovery.py`
- Create: `src/career_agent/services/cleanup.py`
- Create: `src/career_agent/services/migrations.py`
- Create: `src/career_agent/services/reset.py`
- Modify: `src/career_agent/cli.py`
- Create: `tests/unit/test_pipeline_projection.py`
- Create: `tests/unit/test_cleanup.py`
- Create: `tests/unit/test_migrations.py`
- Create: `tests/unit/test_reset.py`
- Create: `tests/contract/test_recovery_cli.py`

## Interfaces

```python
def build_pipeline(workspace: WorkspaceRepository) -> str: ...

class MaintenanceService:
    def recover(self) -> RecoveryReport: ...
    def cleanup_plan(self, now: datetime) -> CleanupPlan: ...
    def apply_cleanup(self, plan_digest: str) -> CleanupResult: ...
    def migration_plan(self, target_version: int) -> MigrationPlan: ...
    def apply_migration(self, plan_digest: str) -> MigrationResult: ...
    def reset_plan(self, scopes: frozenset[ResetScope]) -> ResetPlan: ...
    def apply_reset(self, plan_digest: str) -> ResetResult: ...
```

## Steps

- [x] Write a golden pipeline fixture and a test proving deletion plus regeneration produces byte-equivalent Markdown from the same manifests and journals.
- [x] Write failing cleanup tests for successful run directories, failed bundles younger and older than seven days, releases, submission evidence, imported originals, symlinked directories, and clock-skewed timestamps.
- [x] Write migration fixtures for shared resume folders, duplicate final files, date-based application directories, missing manifests, temporary LaTeX files, competing CSV/JSON state, uncertain submissions, and Google Sheet metadata.
- [x] Write reset tests proving a changed plan digest, widened scope, remote deletion, imported source deletion, release deletion, and submission-evidence deletion require distinct plans and cannot piggyback on a local generated-drafts reset.
- [x] Run `uv run pytest tests/unit/test_pipeline_projection.py tests/unit/test_cleanup.py tests/unit/test_migrations.py tests/unit/test_reset.py -q` and confirm failure.
- [x] Implement sorted pipeline generation containing IDs, readable labels, derived display phase, submission status, outcome, next action, and evidence limitations, with no independent editable fields.
- [x] Implement startup recovery that detects incomplete journals, verifies idempotency keys and checksums, resumes safe checkpoints, and quarantines operations requiring human resolution.
- [x] Implement opportunistic cleanup on CLI startup and doctor runs; cleanup never follows symlinks and applies only a digest-bound plan.
- [x] Implement copy-first migrations with a recoverable backup, schema validation before replacement, transactional commit, and uncertainty preservation.
- [x] Implement reset scopes for generated drafts, temporary files, integrations, and all personal workspace data; remote deletion and protected historical deletion remain separate operations.
- [x] Run focused tests, the accumulated suite, Ruff, and mypy.
- [x] Commit with `git commit -m "feat: add deterministic pipeline and safe maintenance"`.

## Acceptance Criteria

- `pipeline.md` can be deleted without losing state.
- Cleanup cannot touch releases, submission evidence, or imports.
- Migration failure restores the exact pre-migration workspace.
- Every destructive maintenance action requires an unchanged preview digest and exact scope.

## Comments

## Answer

Resolved in `5b4f8ee`. `pipeline.md` is now an atomic, sorted projection rebuilt directly from authoritative manifests and opportunity state, including derived display phase, submission status, next action, and evidence limitations; deleting both the projection and the rebuildable application index does not change its bytes. CLI startup performs conservative journal recovery and opportunistic cleanup: checksum-proven manifest writes are committed, ambiguous operations receive durable quarantine records and terminal failed status, completed run directories are removable immediately, and failed/orphan bundles expire only after seven days without following symlinks or crossing into releases, submissions, or imports. Migration plans bind exact checksums, inventory legacy ambiguity without guessing, create and verify copy-first backup manifests, validate all staged schema output before replacement, and restore from backups on replacement failure. Reset previews bind exact fingerprints and separate generated drafts, temporary files, integrations, imported sources, releases, submission evidence, all personal data, and remote data; incompatible protected scopes cannot piggyback, and remote deletion is refused without its own integration-specific operation. Final verification: 14 focused maintenance tests and 278 accumulated tests pass, along with schema drift, Ruff, formatting, mypy, and diff checks.
