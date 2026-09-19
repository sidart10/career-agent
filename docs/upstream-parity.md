# Upstream Capability Parity

Pinned source: `MadsLorentzen/ai-job-search@27eb57ae93498cddba6268d3dd84d721daa1fa0c`.

Disposition meanings:

- `preserve_v1`: retain the upstream behavior and adapt it to V1 paths and contracts.
- `redesign_v1`: deliver the user outcome through the governed V1 architecture.
- `defer`: retain as planned post-V1 work; it cannot block the initial release.
- `remove`: deliberately exclude the capability from the product.

`post-v1` is a roadmap owner, not an implementation ticket in the current issue set.

| Capability | Disposition | Owner | V1 decision |
|---|---|---|---|
| `workflow.setup` | `preserve_v1` | `04` | Preserve three-path onboarding through immutable imports and confirmed facts. |
| `workflow.scrape` | `defer` | `post-v1` | V1 accepts governed opportunity capture; automated multi-portal search is deferred. |
| `workflow.rank` | `redesign_v1` | `05` | Separate preliminary ranking from authoritative full-posting evaluation. |
| `workflow.apply` | `redesign_v1` | `09` | Replace prompt-driven files with releases, trusted approval, attempts, and qualified evidence. |
| `workflow.interview` | `defer` | `post-v1` | The schema supports events; the preparation workflow is outside V1. |
| `workflow.outcome` | `defer` | `post-v1` | V1 has outcome contracts; messaging and feedback workflows are deferred. |
| `workflow.gmail_sync` | `defer` | `post-v1` | Optional connector work cannot block the local application loop. |
| `workflow.notion_sync` | `defer` | `post-v1` | Optional presentation sync cannot block V1. |
| `workflow.expand` | `defer` | `post-v1` | V1 imports evidence locally; public-profile expansion is deferred. |
| `workflow.upskill` | `defer` | `post-v1` | Cross-role learning aggregation is outside V1. |
| `workflow.html_report` | `defer` | `post-v1` | V1 ships the generated Markdown pipeline only. |
| `workflow.add_template` | `defer` | `post-v1` | V1 ships one governed default document template. |
| `workflow.add_portal` | `defer` | `post-v1` | Executable adapter extension is outside V1. |
| `workflow.reset` | `redesign_v1` | `10` | Replace broad reset with digest-bound scoped previews. |
| `portal.linkedin` | `defer` | `post-v1` | Retain upstream source provenance; automated adapter shipping is deferred. |
| `portal.freehire` | `defer` | `post-v1` | Retain upstream source provenance; automated adapter shipping is deferred. |
| `portal.jobindex` | `defer` | `post-v1` | Market-specific adapter remains opt-in post-V1 work. |
| `portal.jobnet` | `defer` | `post-v1` | Market-specific adapter remains opt-in post-V1 work. |
| `portal.jobdanmark` | `defer` | `post-v1` | Market-specific adapter remains opt-in post-V1 work. |
| `portal.akademikernes_jobbank` | `defer` | `post-v1` | Market-specific adapter remains opt-in post-V1 work. |
| `tool.job_key` | `redesign_v1` | `03` | Stable application IDs and safe slugs move into the storage kernel. |
| `tool.rank_state` | `redesign_v1` | `05` | Evaluation ingestion and scoring operate on typed opportunity contracts. |
| `tool.verify_pdf` | `preserve_v1` | `08` | Port PDF text validation and preserve raw ATS extraction. |
| `tool.verify_layout` | `preserve_v1` | `08` | Port mechanical layout signals into the release gate. |
| `tool.robots_check` | `defer` | `post-v1` | Required when automated portal discovery returns after V1. |
| `tool.salary_lookup` | `defer` | `post-v1` | Salary analysis is explicitly outside V1. |
| `tool.convert_salary_excel` | `defer` | `post-v1` | Salary dataset conversion is outside V1. |
| `tool.lint_skills` | `preserve_v1` | `11` | Adapt linting to canonical portable career skills. |
| `tool.security_guards` | `redesign_v1` | `11` | Enforce V1 permissions, mirror integrity, and protected paths. |
| `tool.check_framework_version` | `defer` | `post-v1` | Runtime schema and CLI compatibility cover V1; framework update UX is deferred. |
| `tool.check_upstream_updates` | `defer` | `post-v1` | Upstream update automation is outside V1. |
| `tool.upstream_triage` | `defer` | `post-v1` | Manual pinned-source review remains sufficient for V1. |
