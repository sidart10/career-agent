# 05 — Opportunities, Deduplication, and Evaluation

Type: task
Status: resolved
Blocked by: 02, 03, 04

## Outcome

The CLI captures lightweight opportunities with complete source provenance, performs only exact automatic merges, produces reversible metadata-similarity candidates, and stores schema-validated preliminary and authoritative fit evaluations with supporting and opposing evidence.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Lightweight opportunity capture | `career opportunity add|list` | `Opportunity` | Capture cannot create an application implicitly | `test_opportunity_cli.py` |
| Safe deduplication | `career opportunity merge|unmerge` | `MergeRecord` | Only exact requisition/URL matches auto-merge; every merge is reversible | `test_deduplication.py` |
| Explainable evaluation | `career opportunity evaluate` | `FitEvaluation` | Authoritative mode requires complete posting and opposing evidence | `test_evaluation.py` |

## Files

- Create: `src/career_agent/services/opportunities.py`
- Create: `src/career_agent/services/evaluation.py`
- Create: `src/career_agent/security/urls.py`
- Modify: `src/career_agent/cli.py`
- Create: `tests/fixtures/postings/`
- Create: `tests/unit/test_opportunities.py`
- Create: `tests/unit/test_deduplication.py`
- Create: `tests/unit/test_evaluation.py`
- Create: `tests/contract/test_opportunity_cli.py`

## Interfaces

```python
class OpportunityService:
    def add(self, capture: OpportunityCapture, idempotency_key: str) -> Opportunity: ...
    def duplicate_candidates(self, opportunity_id: str) -> tuple[DuplicateCandidate, ...]: ...
    def merge(self, primary_id: str, duplicate_id: str) -> MergeRecord: ...
    def unmerge(self, merge_id: str) -> tuple[Opportunity, Opportunity]: ...

class FitEvaluation(BaseModel):
    mode: Literal["preliminary", "authoritative"]
    hard_constraints: tuple[ConstraintFinding, ...]
    weighted_preferences: tuple[PreferenceFinding, ...]
    supporting_evidence: tuple[EvidenceReference, ...]
    opposing_evidence: tuple[EvidenceReference, ...]
    score: Decimal
    recommendation: Literal["pursue", "review", "dismiss"]
```

## Steps

- [ ] Write failing tests for exact requisition-ID merge, canonical-URL merge, tracking-parameter normalization, two distinct requisitions with the same title/location, non-Latin titles, closed deadlines, and reversible merge provenance.
- [ ] Write failing tests that reject an authoritative evaluation without the complete captured posting or without both supporting and opposing evidence arrays.
- [ ] Run `uv run pytest tests/unit/test_opportunities.py tests/unit/test_deduplication.py tests/unit/test_evaluation.py -q` and confirm failure.
- [ ] Implement URL canonicalization that removes known tracking parameters without changing employer path identity and rejects non-HTTP(S), local-network, credential-bearing, or unsafe redirect targets.
- [ ] Implement automatic merge only for exact normalized requisition IDs or canonical URLs. Compute metadata similarity solely to create reviewable candidates.
- [ ] Implement immutable merge records carrying both original opportunity snapshots and all discovery sources; `unmerge` restores both records with their stable IDs.
- [ ] Implement evaluation ingestion as schema-validated model output referencing posting spans and confirmed profile fact IDs. The CLI computes the configured weighted score; the model does not write it directly.
- [ ] Run focused tests, `uv run pytest -q`, Ruff, and mypy.
- [ ] Commit with `git commit -m "feat: add governed opportunity capture and evaluation"`.

## Acceptance Criteria

- Similar metadata alone never destroys or merges an opportunity.
- Every discovery source remains queryable after merge and unmerge.
- Hard constraints and weighted preferences are stored separately.
- Authoritative evaluation requires the complete posting and confirmed profile evidence.

## Comments

- 2026-09-18 — Implemented on `feature/generic-career-agent-v1` in commit `87df615`.
- RED evidence: opportunity and URL tests failed because the services did not exist; evaluation tests failed because the schema-validated scoring service did not exist; CLI contracts failed because the opportunity command group did not exist. Pressure tests then exposed missing raw-URL provenance, path-identity loss, unjournaled merge operations, interrupted journal replay, missing posting spans, and cross-opportunity idempotency reuse.
- GREEN evidence: 25 focused opportunity/deduplication/evaluation/CLI tests and 146 accumulated tests pass; deterministic schema checking, Ruff, formatting, and strict mypy all pass.
- Design note: only case-normalized exact requisition IDs or canonical public URLs auto-merge. Metadata similarity creates review candidates only. Merge records keep both originals plus the merged snapshot, and unmerge is an idempotent journaled restore.
- Design note: URL canonicalization removes only known tracking parameters, preserves employer path identity and original source URLs, and rejects non-HTTP(S), credentialed, local/private, and unsafe redirect targets.
- Design note: evaluation drafts cannot supply their score. The service validates posting spans and confirmed profile fact references, computes weighted scores, and requires complete postings plus supporting, opposing, and confirmed-profile evidence for authoritative mode.
