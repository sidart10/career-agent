# 04 — Profile Import and Evidence

Type: task
Status: ready-for-agent
Blocked by: 02, 03

## Outcome

Users can preview and apply copy-first imports, preserve originals by checksum, propose structured profile facts from synthetic PDF/DOCX/text fixtures, resolve conflicts explicitly, and promote only confirmed facts into the canonical profile.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Reversible import | `career import preview|apply` | `ImportPreview`, `ImportResult` | Preview is non-mutating; apply preserves source bytes | `test_imports.py`, `test_import_cli.py` |
| Canonical grounded profile | `career profile conflicts|confirm` | `ProfileFact`, `FactConflict` | Conflicts and unsupported proposals cannot self-confirm | `test_profile_service.py` |
| Untrusted imported content | same commands | sanitized source metadata | Embedded instructions cannot alter policy, paths, or permissions | `test_imports.py` |

## Files

- Create: `src/career_agent/services/imports.py`
- Create: `src/career_agent/services/profile.py`
- Create: `src/career_agent/security/content.py`
- Modify: `src/career_agent/cli.py`
- Create: `tests/fixtures/imports/`
- Create: `tests/unit/test_imports.py`
- Create: `tests/unit/test_profile_service.py`
- Create: `tests/contract/test_import_cli.py`

## Interfaces

```python
class ImportPreview(BaseModel):
    run_id: str
    source_files: tuple[ImportSource, ...]
    duplicates: tuple[DuplicateSource, ...]
    proposed_facts: tuple[ProposedFact, ...]
    conflicts: tuple[FactConflict, ...]

class ProfileService:
    def preview_import(self, sources: Sequence[Path]) -> ImportPreview: ...
    def apply_import(self, run_id: str) -> ImportResult: ...
    def confirm_fact(self, fact_id: str, value: JsonValue, source_ids: Sequence[str]) -> ProfileFact: ...
```

A `ProfileFact` has a stable fact ID, typed value, source IDs with page/section locators when available, confirmation state, confirmer, and confirmation time. Imported bytes are never rewritten.

## Steps

- [ ] Create synthetic text, PDF, and DOCX fixtures containing consistent facts, conflicting dates, conflicting titles, unsupported metrics, duplicate bytes, malformed documents, and embedded adversarial instructions.
- [ ] Write failing tests proving preview is non-mutating, duplicate bytes collapse by checksum without losing source paths, malformed files remain preserved, and embedded instructions are treated as data.
- [ ] Run `uv run pytest tests/unit/test_imports.py tests/unit/test_profile_service.py -q` and confirm failure.
- [ ] Implement run-scoped staging, MIME detection by content, SHA-256 identification, copy-first application, and owner-only permissions where the platform supports them.
- [ ] Implement deterministic extraction adapters that return proposed facts with source locators; model-assisted extraction is accepted only through schema validation and never directly confirms a fact.
- [ ] Implement conflict records and `career profile confirm` so a user choice creates the canonical fact while preserving rejected alternatives and provenance.
- [ ] Implement claim lookup by stable fact ID for later document releases.
- [ ] Run `uv run career import preview tests/fixtures/imports --json`, focused tests, the accumulated suite, Ruff, and mypy.
- [ ] Commit with `git commit -m "feat: import career evidence into a confirmed profile"`.

## Acceptance Criteria

- Preview performs no governed mutation.
- Every imported original survives byte-for-byte and is addressable by checksum.
- Conflicts never auto-resolve.
- Unsupported claims remain proposals and cannot be referenced by a release as confirmed evidence.
- Prompt-like document text cannot change paths, permissions, policy, or executable configuration.

## Comments
