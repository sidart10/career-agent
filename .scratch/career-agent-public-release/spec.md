# Career Agent V0.1 Repo-Local Early-Access Release Specification

Status: ready-for-decomposition

## Release Contract

V0.1 is a **supervised, repo-local early-access release for technically comfortable users**. It is not yet an install-once/use-anywhere agent plugin, a hosted product, or a production-ready autonomous application system.

The supported user path is deliberately narrow and must be documented and tested exactly as follows:

1. The user clones or checks out a tagged release of `sidart10/career-agent`.
2. From that checkout, the user runs the documented installer. The installer installs the `career` executable into an isolated `uv tool` environment, verifies that the executable is resolvable on `PATH`, and installs or validates only the agent-host discovery surfaces it owns.
3. The user launches Codex or Claude Code from the Career Agent checkout so the host discovers the repository-local skill bundle.
4. The skills call the installed `career` executable, while all personal career evidence and governed state live in a separately selected external workspace.

Every V0.1 guide and product claim must respect that boundary. Reusable skills-only plugin distribution, global skill installation, package-index publication, and launch-from-any-directory support are later milestones. No MCP server or bespoke runtime adapter is required for V0.1.

The supported functional claim is also narrow: Career Agent helps a user set up a workspace, import and verify career evidence, capture preferences, record and rank opportunities, and prepare an application package. Browser-assisted submission remains experimental and requires a separate proof before it can be promoted.

## Problem Statement

The Career Agent has a substantial deterministic core, seven Agent Skills, cross-platform test coverage, and strong safety rules for evidence, approvals, submissions, and recovery. However, those capabilities do not currently form a coherent product that a new user can understand, install, onboard into, and resume through public interfaces.

The repository mixes product implementation, runtime skill installation, internal planning history, public documentation, generated runtime state, and personal workspace data without a clear ownership model. Canonical skills live outside the Codex discovery surface and are copied or linked into ignored runtime directories. The Python package builds, but the complete product assets are not included in that package. The installer creates a source-local virtual environment while the skills assume a globally resolvable `career` command. The default personal workspace depends on the current working directory. Internal implementation tests sometimes bypass the public interface that users and skills are expected to use.

The public documentation layer is also incomplete. A clean clone has no tracked front-door README, no installation or onboarding guide, no complete first-application walkthrough, no consolidated security and privacy disclosure, no support or contribution guidance, and no open-source license. Existing planning documents contain stale or contradictory product claims. Consequently, implementation completeness is easy to overstate while actual user readiness remains uncertain.

First-run onboarding is especially weak. The setup skill does not initialize a workspace, gates basic imports on capabilities that are only needed later, cannot reliably resume after chat context is lost, and relies on fixture-oriented fact extraction that does not represent ordinary resumes. There is no governed preference profile, onboarding status interface, or complete public command path for every documented preparation step.

The user wants Career Agent restructured into a truthful, distributable, local-first product for technically comfortable early adopters. The deterministic Python engine must remain separate from the Agent Skills, personal career data must remain separate from product source, and one clean public interface must support installation, onboarding, recovery, and later career workflows. Public claims must be limited to behavior proven through that interface. “Local-first” describes where authoritative state is stored; it must not imply that model-assisted interpretation, host runtimes, or employer portals never transmit data.

The current baseline is not release-clean. At review time, the concurrent application-ID allocator test fails its timeout both in the full suite and in isolation; wheel contents omit required product assets; source distributions include internal cache/material that should not ship; skill discovery depends on ignored absolute links; and the diagnostic command can trigger recovery and cleanup mutations. These are release blockers, not documentation caveats.

## Solution

Restructure Career Agent around four deep modules with explicit interfaces:

1. **Python Engine** — the deterministic CLI and governed-state implementation. It owns validation, identifiers, storage, evidence, releases, approvals, recovery, migrations, and all exact mutations.
2. **Canonical Skill Bundle** — committed, self-contained Agent Skills under `.agents/skills/`, the repository-local Codex discovery surface. Skills provide judgment and orchestration while calling only the public CLI. Claude Code discovery under `.claude/skills/` is installer-generated: relative per-skill links where supported and checksum-verified mirrors where links are unavailable. Absolute machine-specific links are never committed.
3. **External Career Workspace** — a stable platform-specific user-data location containing one candidate's personal evidence and governed state. The product source tree contains no personal data. One small user configuration records the active workspace, and an environment override remains available for explicit automation.
4. **Public Documentation and Examples** — one tracked front door plus task-oriented installation, onboarding, architecture, security, reference, troubleshooting, and first-application guidance. Realistic synthetic examples and documentation commands are continuously verified.

The normal user installation will be a tagged source-clone early-access distribution installed through `uv tool`. This exposes a stable `career` executable instead of requiring activation of a repository-local virtual environment. Runtime templates, schemas, and other required resources will live inside the Python package, be included in both wheel and source distribution through explicit allowlists, and be resolved with `importlib.resources` rather than repository-relative paths. Contributor setup remains separate from user installation.

Replace the current setup checklist with a resumable `career-onboard` skill backed by governed CLI read models. Onboarding will initialize the workspace, run phase-scoped readiness checks, disclose model-processing and retention implications before model-assisted interpretation, import evidence through previewed copy-first operations, convert extracted document text into evidence-bound profile proposals, collect exact human confirmation, store career preferences separately from profile facts, optionally seed ordinary reusable answers, and report the next action.

Onboarding status is a derived projection over authoritative workspace state, not a second mutable phase ledger. Re-running onboarding recomputes the first incomplete phase from the workspace marker, imported evidence, proposal/conflict records, confirmed facts, preferences, and readiness results. Only facts that cannot be derived—such as a user’s privacy acknowledgement or an explicitly deferred human decision—may be persisted as onboarding metadata.

Readiness will be layered:

- **Core readiness** covers the executable, skill installation, workspace, local filesystem, schemas, checksums, persisted-state validation, and document text extraction.
- **Document readiness** adds supported document rendering and validation tooling.
- **Submission readiness** adds real browser control and trusted human approval authority.

Missing document or submission capabilities will not block core onboarding, evidence import, opportunity capture, ranking, or pipeline review.

Acceptance is split into two independent gates. A deterministic clean-user journey starts from a clean checkout and exercises tracked documentation, repository-discovered skills, the installed artifact, recorded or fixture-backed model-boundary output, and public CLI contracts on every supported operating system. A separate model-driven skill evaluation runs on a pinned host and model for release candidates; scheduled recurrence is enabled only after cost approval. It checks skill triggering, non-triggering, tool/command use, evidence discipline, and human gates. A flaky model evaluation cannot be disguised inside the deterministic cross-platform release test.

The first public release will make the supported preparation and onboarding workflow truthful and reproducible. Existing browser-submission machinery may remain available as experimental functionality, but the repository will not claim real-portal support or production-ready submission until a separate public-interface journey proves it.

## User Stories

1. As a new user, I want one clear repository front door, so that I can understand the product before installing it.
2. As a new user, I want the supported release posture stated prominently, so that I know whether I am using experimental or production-ready software.
3. As a job seeker, I want Career Agent's supported V0.1 capabilities listed separately from deferred capabilities, so that I do not mistake roadmap ideas for working behavior.
4. As a job seeker, I want the limits of real-portal support stated honestly, so that I do not entrust an irreversible application to an unproven workflow.
5. As a job seeker, I want personal data handling explained before onboarding, so that I can make an informed storage decision.
6. As a user, I want source visibility distinguished from open-source licensing, so that I understand my rights to use, modify, and redistribute the software.
7. As a user, I want an explicit license and any required upstream attribution, so that adoption is legally clear.
8. As a user, I want prerequisites listed before the install command, so that setup does not fail halfway through without explanation.
9. As a user, I want supported operating systems, Python versions, `uv` expectations, and runtime requirements documented, so that I can determine compatibility quickly.
10. As a user, I want one normal installation command to expose `career`, so that every skill and guide can rely on the same executable interface.
11. As a user, I want the installed executable isolated from my system Python environment, so that Career Agent does not destabilize unrelated projects.
12. As a contributor, I want contributor setup distinguished from user installation, so that development dependencies are not imposed on users.
13. As a user, I want the built artifact to include every runtime template and schema it needs, so that commands do not depend on the source checkout's physical layout.
14. As a user, I want installation verified from a built artifact, so that a successful source-tree test does not hide missing package resources.
15. As a Codex user, I want canonical Career Agent skills in the native project discovery surface, so that Codex finds them without running a duplicate skill-generation process.
16. As a Claude Code user on a link-capable platform, I want Claude to discover the same canonical skills through relative per-skill links, so that the two runtimes cannot drift.
17. As a Windows user, I want a checksum-verified mirror fallback when links are unavailable, so that runtime support does not depend on privileged symlink configuration.
18. As a user with unrelated skills, I want Career Agent installation to preserve them, so that installing this product does not replace my existing agent environment.
19. As a maintainer, I want one canonical skill source, so that behavioral fixes occur once.
20. As a maintainer, I want mirrored skill drift detected mechanically, so that stale runtime instructions cannot silently control a newer CLI.
21. As a maintainer, I want shared skill rules to resolve correctly after both link and mirror installation, so that safety policy cannot disappear because of directory depth.
22. As a user, I want installation failure to be distinguishable from workflow readiness, so that an installed product does not falsely claim every capability is available.
23. As a user, I want installer output to identify the exact next setup action, so that a successful install does not leave me guessing how to begin.
24. As a job seeker, I want my personal career workspace outside the product repository, so that source updates and Git operations do not touch personal data.
25. As a job seeker, I want onboarding to show and confirm the personal workspace location, so that sensitive files are not stored somewhere surprising.
26. As a job seeker, I want a stable active-workspace configuration, so that changing directories does not silently select a different career identity.
27. As an advanced user, I want an explicit workspace environment override, so that automation and isolated testing remain possible.
28. As a job seeker, I want every governed command to require a valid versioned workspace marker, so that partial accidental workspaces cannot form silently.
29. As a job seeker, I want one active candidate workspace in V0.1, so that another person's facts or documents cannot be mixed into my applications.
30. As an existing user, I want legacy repository-local workspace data detected without automatic movement, so that migration remains deliberate and recoverable.
31. As a new user, I want a `career-onboard` skill, so that first-run setup is expressed as one coherent workflow rather than unrelated commands.
32. As a returning user, I want onboarding progress derived from authoritative governed state, so that restarting the agent does not restart setup or create a second source of truth.
33. As a user, I want onboarding status to identify the first incomplete phase, so that the next action is deterministic.
34. As a user, I want onboarding status to report pending imports, unresolved facts, capability blockers, and preferences, so that interrupted work remains understandable.
35. As a user, I want setup completion to remain distinct from document and submission readiness, so that early progress is not blocked by later tools.
36. As a job seeker, I want to begin onboarding with one resume, a folder of evidence, or a guided conversation, so that existing materials and starting points are both supported.
37. As a job seeker, I want evidence import previewed before mutation, so that I can see what will be copied and proposed.
38. As a job seeker, I want imported originals preserved by checksum, so that Career Agent cannot silently rewrite my source evidence.
39. As a job seeker, I want exact duplicates identified, so that the workspace does not accumulate redundant copies.
40. As a job seeker, I want failed or unsupported documents shown individually, so that I can preserve, exclude, or repair each one deliberately.
41. As a job seeker, I want selective import application, so that one problematic file does not force an all-or-nothing decision.
42. As a job seeker, I want ordinary resumes understood without special fixture labels, so that onboarding works with documents people actually have.
43. As a maintainer, I want deterministic document copying and text extraction separated from agent interpretation, so that each module has a small, testable interface.
44. As a job seeker, I want the agent to produce structured fact proposals with exact, reproducible evidence locators, so that every proposed fact can be verified against the immutable imported source.
45. As a job seeker, I want the CLI to validate proposal structure, source and normalized-text checksums, extractor identity, page or block coordinates, character offsets, and the referenced substring, so that model output cannot directly become canonical state or cite text that is no longer present.
46. As a job seeker, I want proposed facts to remain unconfirmed until I approve them, so that the agent cannot promote plausible inferences into truth.
47. As a job seeker, I want all proposed, confirmed, and conflicted facts listable later, so that losing command output does not lose my onboarding state.
48. As a job seeker, I want conflicts presented one key at a time with source evidence, so that I can make precise choices.
49. As a job seeker, I want direct statements I provide to carry explicit user-statement provenance, so that manually supplied facts remain distinguishable from imported evidence.
50. As a job seeker, I want missing minimum profile information requested only when necessary, so that onboarding is useful without becoming an exhaustive interrogation.
51. As a job seeker, I want career preferences stored separately from resume facts, so that subjective goals are not misrepresented as historical evidence.
52. As a job seeker, I want to record target roles, seniority, industries, locations, work modes, and hard exclusions, so that discovery and ranking reflect my actual search.
53. As a job seeker, I want weighted priorities distinct from hard constraints, so that preferences do not silently become eligibility rules.
54. As a job seeker, I want preference completeness visible during onboarding, so that rankings reveal when they rely on defaults or missing information.
55. As a job seeker, I want ordinary reusable answers optionally seeded during onboarding, so that basic forms become less repetitive.
56. As a job seeker, I want high-risk and sensitive answers deferred until a real application asks, so that onboarding does not collect unnecessary personal data.
57. As a job seeker, I want an explicit retention and reuse choice when a sensitive answer is first encountered, so that convenience does not override privacy.
58. As a job seeker, I want onboarding completion to report redacted answer counts rather than values, so that status output is safe to share for diagnostics.
59. As a job seeker, I want the onboarding completion report to distinguish core, document, and submission readiness, so that I know exactly which workflows are available.
60. As a job seeker, I want the completion report to state the exact next command or skill, so that onboarding connects naturally to opportunity discovery.
61. As a user without LaTeX, I want core onboarding and ranking to remain available, so that document rendering can be configured later.
62. As a user without browser automation, I want preparation workflows to remain available, so that missing submission tooling does not make the product unusable.
63. As a user, I want manually declared capabilities labeled as declarations rather than verified facts, so that readiness reports do not overstate assurance.
64. As a user, I want `career doctor` to be strictly read-only and recovery or cleanup to require separate preview and apply commands, so that inspection cannot mutate governed state.
65. As a user, I want a task-oriented getting-started guide, so that I can progress from installation to verified onboarding without reading internal design documents.
66. As a user, I want a first-application guide, so that I understand how onboarding connects to opportunity capture, ranking, document preparation, and portal handoff.
67. As a user, I want an architecture explanation, so that I understand the relationship between the host runtime, skills, CLI, workspace, browser, and human approval.
68. As a user, I want a workspace and state explanation, so that I can distinguish authoritative records from disposable projections.
69. As a user, I want a security and privacy guide, so that I understand plaintext local storage, model-provider processing, Git risks, backups, redaction limits, and deletion behavior.
70. As a user, I want troubleshooting guidance keyed to readiness failures, so that missing tools and invalid configuration produce actionable recovery steps.
71. As a user, I want support and vulnerability-reporting instructions, so that ordinary bugs and sensitive reports reach the right channel.
72. As a contributor, I want development, testing, schema-change, and documentation expectations documented, so that contributions preserve product invariants.
73. As a maintainer, I want internal planning history clearly separated from living product documentation, so that completed design artifacts do not appear to be current instructions.
74. As a maintainer, I want stale and contradictory product claims removed or labeled historical, so that new users encounter one canonical truth.
75. As a maintainer, I want realistic synthetic examples validated in CI, so that published commands and request payloads cannot drift silently.
76. As a maintainer, I want the README quickstart executed by the release test, so that documentation is part of the verified product interface.
77. As a maintainer, I want the clean-user journey to use only the installed executable and public CLI, so that internal implementations cannot mask missing interfaces.
78. As a maintainer, I want a fresh runtime session to resume the synthetic onboarding journey, so that resumability is proven rather than described.
79. As a maintainer, I want the primary journey exercised on every declared supported platform, so that platform claims remain evidence-backed.
80. As a maintainer, I want release checks to inspect package contents, installed resources, skill discovery, and documentation commands, so that a green unit suite is not mistaken for a usable release.
81. As a maintainer, I want existing deterministic state, approval, recovery, and privacy tests preserved, so that restructuring does not weaken the safety kernel.
82. As a user, I want experimental submission functionality labeled separately from supported preparation workflows, so that I can choose the appropriate level of risk.
83. As a job seeker, I want no real employer contacted by automated release tests, so that verification cannot submit an application accidentally.
84. As a job seeker, I want onboarding to grant no submission authority, so that confirmed profile data cannot be confused with approval to act externally.
85. As a V0.1 user, I want the repo-local operating boundary stated before installation, so that I know to launch my agent host from the tagged checkout.
86. As a user, I want workspace resolution to follow `--workspace`, then `CAREER_WORKSPACE`, then user configuration, then a documented platform default, so that selection is predictable and never falls back silently to the current directory.
87. As a user, I want the workspace path and stable workspace identity shown before consequential operations, so that I do not mutate the wrong candidate workspace.
88. As a user, I want skill-bundle, CLI, API, and schema versions checked for compatibility, so that stale instructions cannot drive a newer or incompatible engine.
89. As a user, I want documented upgrade, rollback, repair, and uninstall procedures, so that early-access installation is reversible.
90. As a user, I want the installer to keep an ownership manifest and roll back incomplete work, so that it changes only paths it owns and does not leave a partial installation.
91. As a maintainer, I want every safety-critical skill instruction self-contained or stored in that skill’s local references, so that moving or mirroring a skill cannot remove evidence, approval, privacy, or submission rules.
92. As a job seeker, I want an explicit disclosure and acknowledgement before my resume text is sent to a model provider, so that local storage is not confused with local-only processing.
93. As a job seeker, I want extraction warnings and OCR status preserved with evidence, so that a proposal based on incomplete text cannot appear fully supported.
94. As a user with a scanned PDF, I want the release to state whether OCR is supported and to fail clearly when it is not, so that an empty extraction is never treated as a valid resume.
95. As a maintainer, I want the committed skills validated against the Agent Skills specification, so that malformed metadata or references fail before release.
96. As a maintainer, I want positive and negative trigger evaluations for every public skill, so that skills activate when relevant and stay quiet when irrelevant.
97. As a maintainer, I want model-driven evaluations pinned to an identified host, model, skill bundle, and CLI version, so that results are reproducible enough to compare across releases.
98. As a maintainer, I want recurring or paid evaluation cost disclosed and explicitly approved before activation, so that release automation cannot create silent spend.
99. As a maintainer, I want the upstream MIT notice preserved in the public distribution and a project license selected before publication, so that redistribution has a lawful, inspectable basis.
100. As a maintainer, I want the existing failing allocator test resolved or formally reclassified with evidence before decomposition is declared implemented, so that restructuring does not normalize a red baseline.
101. As a release owner, I want publication and repository-visibility changes to remain explicit human actions after all automated gates pass, so that technical readiness is not mistaken for authorization to publish.

## Implementation Decisions

### Product and ownership boundaries

- Retain `src/career_agent/` as the conventional source-layout Python package for the deterministic engine. The distribution name may use a hyphen while the importable package uses an underscore. The `src/` layout is intentional and is not replaced by a skill directory.
- The Python Engine is the only module authorized to mutate governed state. Agent Skills may interpret evidence and orchestrate public commands, but they may not write manifests, journals, releases, approvals, or submission evidence directly.
- The V0.1 public claim is setup, evidence-backed profile construction, preferences, opportunity capture/ranking, and application preparation. Browser-assisted submission is experimental.
- No MCP server, adapter layer, or host-specific reimplementation is introduced for V0.1. Skills call one versioned `career` CLI contract.

### Skill layout and compatibility

- Commit the canonical skill directories under `.agents/skills/` and update `.gitignore` so this source is tracked. Remove the former top-level canonical copies only after references, tests, documentation, and history links have migrated.
- Each skill is a self-contained Agent Skills directory with `SKILL.md` and only the `references/`, `scripts/`, or `assets/` it needs. Safety-critical instructions must live in the skill or its local references; `career-rules.md` at repository root cannot be the sole runtime source.
- Validate every canonical skill with `skills-ref validate` or an equivalently pinned standards validator. Keep descriptions concise and specific enough to support both trigger and non-trigger evaluation.
- Codex discovers `.agents/skills/` from the checkout. Claude Code discovery under `.claude/skills/` is generated by the installer using relative per-skill links on link-capable systems and checksum-verified mirrors otherwise. Generated links or mirrors are not committed, and absolute local paths are prohibited.
- The installer preserves unrelated user skills and refuses to replace unmanaged conflicts. For every managed path, its ownership manifest records the source revision, skill-bundle version, content checksum, installation mode, and destination.
- The CLI reports a product version and public API/schema compatibility version. Skills declare their bundle version and supported CLI range. The installer and `career doctor` report incompatibility as an actionable error rather than attempting best-effort execution.
- A later milestone may distribute the same skills as a reusable Codex/Claude plugin. That work is intentionally separate from the repository-local V0.1 contract.

### Installation and packaging

- The supported installation starts from a tagged checkout and uses `uv tool install` against the local project or built wheel. It must not depend on a repository-local virtual environment. Contributor installation continues to use the locked development environment and is documented separately.
- Documentation provides copy-paste commands for macOS/Linux shells and PowerShell, including `uv` installation prerequisites, `uv tool update-shell` or equivalent PATH guidance, version verification, upgrade/reinstall, rollback, repair, and uninstall.
- Installation is transactional. It computes a plan, validates conflicts, writes through temporary paths, records only paths it owns, verifies the installed CLI and skills, and rolls back its own changes if validation fails. Uninstall removes only manifest-owned paths.
- Runtime schemas, templates, and other data files live inside the Python package and are accessed with `importlib.resources`. Wheel and source-distribution contents use explicit allowlists and exclude `.hypothesis`, caches, scratch plans, personal data, and test-only material.
- Release verification uses `uv build --no-sources` where applicable, inspects both artifacts, installs the wheel into a clean external environment, and exercises required resources without access to the source tree.

### Workspace selection and diagnostics

- Personal career data lives outside the source checkout in a platform-appropriate user-data location selected with `platformdirs` or an equivalent cross-platform contract.
- Workspace resolution precedence is exactly: explicit `--workspace`; `CAREER_WORKSPACE`; atomically written user configuration; documented platform default. The current working directory is never an implicit workspace selector.
- Each initialized workspace has a stable random workspace ID and a versioned marker. Consequential previews, approvals, applies, migrations, recovery, cleanup, and resets show both canonical path and workspace ID.
- Workspace paths are normalized and checked for unsafe symlink traversal, overlap with the product checkout, unsupported marker versions, and ambiguous aliases before mutation. Configuration updates are atomic.
- V0.1 supports one active single-candidate workspace. Legacy repository-local data is detected but never moved or deleted automatically; migration is previewed, copy-first, separately approved, and recoverable.
- `career doctor` is strictly read-only. It may validate and recommend commands, but cannot recover, clean, migrate, or rewrite state. Recovery and cleanup use separate `plan`/`preview` and `apply` commands with explicit authority and idempotency.
- Readiness is split into core, document, and submission levels. Each workflow gates only on what it needs, and reports distinguish mechanically verified capabilities from user declarations.

### Onboarding, privacy, and evidence

- `career-onboard` replaces the setup checklist as the single maintained first-run skill. Any temporary old name is only a redirect with a removal date.
- Onboarding status is a pure projection over authoritative domain state. It derives the first incomplete phase, pending imports, unresolved proposals/conflicts, preference completeness, readiness blockers, redacted answer counts, and next action. It does not persist a competing mutable phase state.
- Only non-derivable decisions—such as acknowledgement of model-processing disclosure or a deliberately deferred human gate—may be stored as onboarding metadata, with timestamp and policy version.
- Before any model-assisted interpretation, the user sees what data may be sent, which configured provider/host processes it, what Career Agent stores locally, and what it cannot control about provider retention. The model-assisted step requires an explicit acknowledgement; deterministic local import may proceed without it.
- Evidence import supports one resume, a collection of career documents, or governed user statements. File operations are previewed, copy-first, checksum-addressed, selectively applicable, and idempotent.
- Deterministic extraction records source checksum and media type, extractor name/version, extraction time, normalized-text checksum, page/block identifiers, warnings, and OCR status. The normalized text is immutable for that extraction record.
- Each model-proposed fact cites the extraction record, page or block, character start/end offsets, and exact substring. The CLI verifies the checksums, coordinates, and substring before accepting the proposal. A mismatch or extraction warning is surfaced; it cannot be silently downgraded to supported evidence.
- Scanned-PDF behavior is explicit. If OCR is not supported in V0.1, image-only PDFs fail with a specific remediation message. If OCR is supported, engine/version, confidence/warnings, and provenance are retained.
- Agent interpretation produces proposals only. Explicit human confirmation promotes a fact to canonical profile state. Proposed, confirmed, conflicted, and user-stated facts remain listable through public read interfaces across fresh sessions.
- Career preferences are their own governed module. Hard constraints, weighted priorities, and missing/defaulted preferences are distinguishable from historical profile facts.
- Onboarding may offer ordinary reusable answers. Sensitive and high-risk answers remain progressive and require explicit retention and reuse choices when a real application first asks. Onboarding never grants submission authority or stores credentials and authentication secrets.

### Documentation, provenance, and claims

- Maintain one canonical tracked README and task-oriented guides for installation, onboarding, first application, configuration, architecture, workspace/state, evidence/approval, security/privacy, compatibility, troubleshooting, support/security reporting, contribution, and release operations.
- Documentation states the repo-local V0.1 boundary prominently and separates supported, experimental, and deferred capabilities. Package metadata uses the canonical README or a generated non-divergent derivative.
- Public examples use realistic synthetic data. Internal plans and ticket history are either clearly historical or excluded from release artifacts; they are never presented as user documentation.
- Preserve the exact upstream MIT notice for the pinned `MadsLorentzen/ai-job-search` revision in `THIRD_PARTY_NOTICES` or an equivalent shipped attribution file. Selecting and adding the Career Agent project license is a human-owned but release-blocking decision; the repository cannot be called open source before it is complete.
- Claims are constrained by executable evidence. “Local-first” does not mean “data never leaves the machine,” and append-only/tamper-evident governed interfaces are not described as tamper-proof against the local owner.
- Browser-assisted submission remains experimental until a separate public-interface journey proves host-browser handoff, real interactive approval, immediate revalidation, single-click execution, and evidence recording without internal test authorities.

## Testing Decisions

### Gate A — deterministic product journey

- Run on every declared supported operating system for pull requests that affect the release surface and again from the release tag. This gate cannot call a live model or employer portal.
- Begin from a clean checkout and use only tracked documentation, repository-discovered skills, the installed `career` executable, recorded or fixture-backed model-boundary responses, and public CLI contracts. It may not import private Python services or construct hidden state.
- Execute the documented install command against the built artifact, verify `career` outside the contributor environment, validate PATH guidance, and prove packaged resources work after the source checkout is made unavailable.
- Verify canonical `.agents/skills/` discovery. Exercise Claude relative-link behavior on a link-capable runner and the mirror fallback on Windows or an equivalent no-link environment. Preserve unrelated skill directories and reject unmanaged conflicts.
- Verify ownership-manifest creation, forced mid-install failure and rollback, idempotent repair, version incompatibility, upgrade/rollback, and uninstall that removes only owned paths.
- Create a workspace outside the checkout. Prove the exact resolution precedence, stable workspace ID, atomic config update, path/symlink validation, and independence from the current working directory.
- Prove `career doctor` causes no file, journal, timestamp, lock, recovery, or cleanup changes. Exercise recovery and cleanup only through explicit preview/apply commands.
- Run core readiness without browser or document-rendering declarations and prove onboarding remains usable. Test document and submission readiness separately.
- Import a realistic synthetic resume without fixture labels. Verify preview, selective apply, duplicate detection, immutable originals, source/extracted-text checksums, extractor metadata, warnings, and OCR behavior.
- Feed a recorded structured proposal through the public boundary. Accept valid page/block and character coordinates plus exact substring; reject checksum drift, invalid offsets, mismatched substrings, unsupported sources, and warning states that policy disallows.
- Prove facts remain proposals until explicit confirmation. Create and resolve a conflict after a fresh process starts, with no dependence on earlier chat or terminal output.
- Store preferences independently from facts and verify hard constraints, weighted priorities, and missing/defaulted values through public reads.
- Prove onboarding status is derived from authoritative state by deleting no phase ledger, restarting, and obtaining the same first incomplete step. Repeating import/apply/confirm commands must not duplicate data.
- Verify model-processing disclosure and acknowledgement at the interpretation boundary. Prove deterministic import can occur before acknowledgement while model-assisted proposal ingestion cannot.
- Seed only ordinary answers and prove sensitive/high-risk values are neither requested nor retained implicitly. Prove onboarding grants no submission authority.
- Execute README quickstart and onboarding commands directly or generate snippets from the tested command source. A non-runnable public example fails the gate.

### Gate B — model-driven skill evaluation

- Run for release candidates on one explicitly pinned, supported agent host and model; run additional scheduled evaluations only after recurring cost has been disclosed and approved.
- Record host version, model identifier, evaluation prompt-set revision, skill-bundle version, CLI/API version, trace or command transcript, and resulting artifacts for every run.
- Maintain positive trigger, ambiguous trigger, and negative/non-trigger prompts for every public skill. Evaluate whether the correct skill activates, irrelevant skills remain inactive, and the skill uses only supported public commands.
- Evaluate evidence discipline, privacy disclosure, confirmation requirements, approval boundaries, refusal to fabricate missing facts, and the prohibition on autonomous submission authority.
- Separate deterministic assertions from rubric judgments. Deterministic checks validate commands and artifacts; calibrated rubric checks assess orchestration quality. Flaky model outcomes do not block diagnosis of deterministic product failures and may not be hidden by retries without reporting them.

### Baseline and artifact gates

- Before feature implementation is considered complete, the existing test suite must be green from a clean environment. The allocator timeout must be fixed or, if proven environmental, quarantined with an owner, reproduction evidence, expiry date, and a replacement concurrency assertion. Silent retry is not an acceptable resolution.
- Existing deterministic storage, locking, journal, checksum, privacy, approval, release, recovery, migration, cleanup, and reset coverage remains mandatory. New tests focus on public contracts rather than incidental private structure.
- Build wheel and source distribution from a clean tree, inspect explicit content allowlists, install each in isolation, and verify there are no caches, scratch plans, personal files, credentials, or test-only artifacts.
- Run secret and personal-data scanning over Git history considered for publication and over both release artifacts. Synthetic literals must be clearly classified; real secrets or personal data are blockers.
- Real employer portals, candidate documents, and submissions are prohibited in automated tests. Submission experiments use synthetic loopback infrastructure unless a separate, explicitly approved manual compatibility exercise exists.
- A release cannot be declared complete from unit tests alone. Gate A, Gate B, artifact checks, documentation verification, provenance/license checks, and the declared platform matrix must all have fresh passing evidence.

## Open Human Decisions

These decisions do not block ticket decomposition, but each blocks the release gate named beside it:

- **Project license — Legal/provenance:** choose and add the Career Agent license. MIT is the default recommendation for compatibility and simplicity, but the repository owner must make the choice. The upstream MIT notice is required regardless.
- **Supported platform matrix — Deterministic journey:** name the exact macOS, Linux, Windows, and Python versions V0.1 claims. A platform is unsupported until Gate A passes there.
- **Scanned-PDF policy — Onboarding:** either defer OCR with a clear image-only-PDF error (recommended for V0.1) or choose a pinned OCR engine and accept its packaging, provenance, and quality obligations.
- **Evaluation runtime and budget — Model-driven evaluation:** select the supported agent host/model and approve any per-run or recurring spend before enabling the release-candidate or scheduled job.
- **Visibility and publication — Human authorization:** decide whether and when the repository becomes public and the V0.1 tag/release is published. No implementation ticket performs this automatically.

## Release Gates

The release owner may tag or publish V0.1 only when all of the following are true:

1. **Baseline:** the clean deterministic suite passes, including resolved concurrency behavior.
2. **Artifact:** wheel and source-distribution allowlists pass; clean external installs contain every runtime resource and no internal cache or personal material.
3. **Installation:** transactional install, PATH verification, compatibility handshake, rollback, repair, and uninstall pass on the supported platform matrix.
4. **Skills:** `.agents/skills/` is tracked and standards-valid; Claude discovery is generated and portable; safety rules survive both link and mirror modes.
5. **Workspace:** precedence, stable identity, external storage, atomic configuration, path safety, and read-only diagnostics are proven.
6. **Onboarding:** deterministic resume import, privacy acknowledgement, evidence locators, confirmation, preferences, fresh-session resumption, and no submission authority pass through public interfaces.
7. **Documentation:** the README and task guides are tracked, internally consistent, and their commands execute successfully from the tag.
8. **Legal/provenance:** the project license is present, the pinned upstream MIT notice is shipped, and repository history/artifacts pass secret and personal-data review.
9. **Evaluation:** model-driven skill evaluation passes on the pinned host/model with stored evidence and disclosed cost.
10. **Human authorization:** the release owner explicitly approves repository visibility and publication after reviewing the gate report. Passing automation does not itself publish anything.

## Out of Scope

- A graphical desktop, web, or mobile interface.
- A hosted Career Agent service or multi-tenant account system.
- Multiple candidate profiles within one V0.1 workspace.
- Publishing to PyPI or another package index before the complete artifact contract is verified. Local `uv tool` installation from the repository is the initial distribution path.
- A bespoke runtime-adapter framework for Codex and Claude Code. The release uses one canonical skill source plus links or installer-managed mirrors.
- A reusable skills plugin, marketplace distribution, global install-once/use-anywhere skill discovery, or launching the agent host from an unrelated directory. These are post-V0.1 distribution milestones.
- An MCP server solely for packaging or discovering the V0.1 skills.
- Guaranteed Windows symlink support. Windows may use the verified mirror fallback.
- Automatic installation of system-level TeX distributions, browser applications, or authenticated connectors.
- Gmail, Notion, automatic multi-portal discovery, interview preparation, offer analysis, salary analysis, reporting, upskilling, and third-party extension frameworks.
- Application-level encryption. Documentation will instead explain plaintext local storage and recommend appropriate full-disk protection.
- Storing passwords, passkeys, MFA codes, identity secrets, or prohibited personal values.
- Autonomous acceptance of legal attestations, account terms, identity checks, or other human-only consent.
- Claiming production-ready real-portal submission. Existing submission machinery remains experimental until separately proven through public runtime interfaces.
- Rewriting the established deterministic state, approval, evidence, or recovery model except where required to expose a complete public interface.
- Deleting the completed original V1 specification or implementation history. Historical material may be relocated or relabeled through a later approved documentation migration.
- Automatically making the repository public, tagging/publishing the release, or changing repository visibility. Those remain explicit human release decisions after the technical gates pass. Preparing the project license and required upstream attribution is in scope and release-blocking.

## Further Notes

- This specification follows a completed adversarial review of documentation, installation, onboarding, skills, packaging, and repository structure. The review found that the governed-state kernel is materially stronger than the public product experience.
- The architectural goal is depth: skills expose a small orchestration interface, the CLI hides deterministic complexity, and the workspace persists authoritative state. Callers and tests should cross the same seams.
- The deterministic clean-user journey is the highest repeatable product seam, while the pinned model-driven evaluation tests host orchestration separately. Lower-level tests remain valuable, but they cannot substitute for either gate.
- The existing untracked root README and untracked upstream audit are user-owned working files and are not modified or adopted by this specification automatically.
- The canonical repository identity for this work is `sidart10/career-agent`; historical links to the prior owner should be treated as migration history rather than the current project home.
- The adversarial review that drove these revisions is preserved at `.scratch/career-agent-public-release/adversarial-review-research.md`. Its no-go verdict applies to the pre-revision plan; implementation still remains a no-go until the release gates above are decomposed and satisfied.
- Decompose this specification into dependency-ordered implementation tickets only after review. Ticket domains should include: baseline remediation; legal/provenance; package resources/artifacts; transactional CLI installation; canonical skill migration and validation; version compatibility; external workspace selection; read-only diagnostics and explicit recovery; evidence extraction/locator contracts; privacy acknowledgement; preference state and derived onboarding projection; public documentation; deterministic cross-platform journey; model-driven skill evaluation; and final release audit.

## Reference Basis

The release contract and testing split were checked against current primary guidance:

- [OpenAI: Agent Skills](https://developers.openai.com/codex/build-skills) — repository skill discovery, symlink support, and progressive disclosure.
- [OpenAI: Plugins](https://developers.openai.com/plugins/build/plugins) — the later reusable distribution boundary.
- [OpenAI: Evaluate skills](https://developers.openai.com/blog/eval-skills) — trigger/non-trigger prompts, captured runs, deterministic checks, and rubric-based evaluation.
- [Anthropic: Extend Claude with skills](https://code.claude.com/docs/en/skills) — Claude Code project discovery, plugin scope, additional directories, and symlink behavior.
- [Agent Skills specification](https://agentskills.io/specification) — portable skill directory, metadata, and relative-reference contract.
- [uv: Tools](https://docs.astral.sh/uv/concepts/tools/) and [uv: Building distributions](https://docs.astral.sh/uv/guides/package/) — isolated executable installation and clean artifact verification.
- [Python: `importlib.resources`](https://docs.python.org/3/library/importlib.resources.html) and [platformdirs](https://platformdirs.readthedocs.io/en/latest/api.html) — packaged resource access and platform-appropriate user-data paths.
- [Pinned upstream MIT license](https://raw.githubusercontent.com/MadsLorentzen/ai-job-search/27eb57ae93498cddba6268d3dd84d721daa1fa0c/LICENSE) — required provenance for the audited upstream revision.
