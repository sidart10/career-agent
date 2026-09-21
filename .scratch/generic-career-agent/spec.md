# Generic Career Agent Specification

Status: decomposed

## Problem Statement

The existing career-agent implementation contains valuable job-search methods, portal integrations, document templates, Gmail and Notion workflows, and PDF validation tools, but its operating model is unreliable and tied primarily to Claude Code. Candidate information is mixed with framework instructions, application state is split across loosely managed files, role-specific documents are generated into shared locations, filenames drift, temporary artifacts accumulate, and the system cannot always establish which document version was approved or submitted. The older personalized implementation compounds this with Chief-of-Staff concerns and Google Sheets as another source of truth.

The user wants a focused, generic career agent—not a general-purpose workspace assistant—that can be cloned and used by one job seeker in either Claude Code or Codex. It must preserve the useful behavior of the upstream ai-job-search repository while replacing its prompt-driven file lifecycle with deterministic workspace operations. It must use the host runtime's web, browser, computer-use, connector, document, PDF, and approval capabilities instead of building another browser or hosted product.

The complete application workflow must be autonomous in the practical sense: the agent should not ask for approval after every step. It should research, prepare, validate, navigate, fill, upload, and recover on its own; ask only for genuinely missing facts or mandatory human interactions; and request one application-specific approval immediately before the final submission. Answers learned while filling applications must be saved and reused safely so that the agent becomes less interruptive over time without ever inventing sensitive information.

The missing foundation is a deterministic, local-first career workspace with governed state transitions, stable identifiers, canonical naming, tamper-evident releases, evidence-qualified submission records, reusable application answers, optional one-way integrations, and a dual-runtime skill harness.

## Solution

Build a standalone, single-candidate career-agent repository based on a pinned upstream ai-job-search snapshot. Preserve the upstream career methodology, portal adapters, profile expansion, ranking, document generation, PDF verification, Gmail synchronization, Notion presentation, reporting, interview, outcome, salary, upskilling, template extension, portal extension, reset, and maintenance capabilities. Remove Google Sheets, Chief-of-Staff behavior, global document dumps, competing trackers, and legacy command definitions.

The repository will expose one canonical collection of career-namespaced Agent Skills to both Claude Code and Codex. The skills will express capability-oriented workflows rather than hardcoding one runtime's tool names. Claude and Codex will retain their own small root instruction entry points, both loading the same shared career rules. Claude's skill discovery surface will link to the canonical portable skills; platforms that cannot create links will receive an installer-managed mirror with drift detection. There will be no legacy commands directory.

A shared local career CLI will own every deterministic mutation: initialization, imports, identifiers, workspace paths, application manifests, reusable answers, lifecycle transitions, document releases, submission attempts, evidence registration, pipeline generation, synchronization checkpoints, validation, migrations, diagnostics, and cleanup. Agents may edit ordinary drafts, but they may not directly mutate governed state. Operations will be schema-validated, locked, atomic, checkpointed, and idempotent.

The local application manifests and operation journals are authoritative. The workspace contains the candidate profile, canonical resources, lightweight opportunities, complete application records, and a generated Markdown pipeline projection. Every pursued role receives one application record containing the captured posting, editable drafts, tamper-evident releases, submission attempts, interviews, and outcome. Notion remains an optional one-way tracking view, and Gmail remains an optional source of policy-qualified pipeline events. Neither integration is required for the core workflow, and Google Sheets is removed entirely.

Application-form answers will accumulate organically. The agent asks for an unknown answer only when it first appears in a real application, saves the exact user-provided response with provenance and sensitivity metadata, maps later wording variants to a canonical question, and reuses the answer automatically. Stable answers remain valid until contradicted; time-sensitive answers are reconfirmed only when stale or conflicting. Company-specific narratives stay with the application and are never blindly reused.

The primary product seam is one synthetic end-to-end application journey through the real skills and CLI against a local fake employer portal. Gmail and Notion are substituted only at their connector boundaries. This exercises the highest useful seam: profile evidence, discovery, deduplication, application creation, grounded document generation, LaTeX rendering, PDF validation, answer capture and reuse, browser filling, final review, approval binding, submission evidence, pipeline updates, and outcome handling.

## Initial Release Boundary

The initial release proves the reliable application loop for one candidate on one local machine. It is intentionally narrower than the complete planned capability surface.

V1 includes:

- installation and doctor diagnostics;
- candidate workspace initialization;
- immutable source import and structured profile confirmation;
- opportunity capture and reversible deduplication;
- authoritative fit evaluation from a complete posting;
- application record creation;
- application-owned drafts and validated PDF releases;
- reusable answer capture with risk-aware reuse policies;
- browser-assisted form completion;
- human-controlled approval bound to a canonical payload;
- one submission attempt with uncertain-result handling;
- tamper-evident submission evidence;
- a generated local pipeline view;
- interruption recovery, cleanup, migration foundations, and scoped reset; and
- Claude Code and Codex conformance at the CLI and persisted-state boundary.

V1 does not require Gmail, Notion, interview preparation, offer analysis, salary comparison, reporting, upskilling, private Git versioning, upstream-update automation, or third-party portal extension. These remain part of the planned capability surface but cannot block the V1 release.

V1 is complete only when the primary and uncertain-result end-to-end journeys pass on macOS, Linux, and the declared Windows execution environment, and when the state, approval, privacy, tamper-detection, and recovery invariants in this specification pass their contract tests.

## User Stories

1. As a job seeker, I want to clone one focused career-agent repository, so that I can begin without adopting a general Chief-of-Staff workspace.
2. As a Claude Code user, I want the career workflows available as native skills, so that they are discoverable in the runtime I already use.
3. As a Codex user, I want the same canonical skills available natively, so that behavior does not drift between runtimes.
4. As a cross-platform user, I want installation to work on macOS, Linux, and the declared Windows execution environment, so that skill discovery is not dependent on Unix links.
5. As a user, I want the installer to be safe to rerun, so that interrupted or repeated setup does not corrupt my workspace.
6. As a user, I want a doctor command to report missing dependencies and integrations, so that setup problems are actionable.
7. As a user, I want LaTeX availability detected without silently installing system software, so that I remain in control of machine-level changes.
8. As a user, I want Gmail, Notion, and browser capabilities detected without automatic authentication, so that setup does not assume external permissions.
9. As a maintainer, I want the upstream repository and pinned baseline retained as provenance, so that future fixes can be reviewed instead of manually rediscovered.
10. As a maintainer, I want upstream updates previewed and applied manually, so that local architecture and personal data are not silently changed.
11. As a user, I want one candidate identity per workspace, so that another person's documents or answers can never be submitted accidentally.
12. As a user, I want personal career data ignored by version control by default, so that cloning and updating the harness does not expose my information.
13. As a user, I want an explicit opt-in path for private versioning, so that I can back up my workspace when I understand the privacy implications.
14. As a user, I want owner-only permissions applied where supported, so that local human-readable files are not unnecessarily exposed.
15. As a user, I want the product to disclose that local files are not custom-encrypted, so that I can choose an encrypted disk when required.
16. As a new user, I want to import an existing resume or career resource collection, so that I do not have to recreate my history manually.
17. As a user, I want imported files preserved unchanged, so that the career agent never destroys or rewrites my originals.
18. As a user, I want imports staged, checksummed, deduplicated, and previewed, so that normalization remains reversible.
19. As a user, I want imported PDF and DOCX resumes converted into a proposed structured profile, so that future tailoring has a reliable source.
20. As a user, I want conflicting dates, titles, metrics, and skills queued for confirmation, so that the system never guesses which source is correct.
21. As a user, I want one canonical structured career profile, so that every application uses the same confirmed facts.
22. As a user, I want every resume claim grounded in an imported source or user-confirmed fact, so that the agent cannot invent achievements.
23. As a user, I want unsupported improvements presented only as suggestions, so that plausible wording cannot become false evidence.
24. As a user, I want facts learned during application work promoted into my profile only after confirmation, so that future applications can safely reuse them.
25. As a job seeker, I want the agent to discover jobs using installed portal adapters and runtime web tools, so that I can search broadly.
26. As a job seeker, I want portal searches to respect access restrictions and rate limits, so that automation behaves responsibly.
27. As a job seeker, I want authenticated browser sessions used only when I have connected them, so that the agent does not assume access.
28. As a job seeker, I want CAPTCHA and anti-bot controls left for me to complete, so that the agent never attempts to bypass them.
29. As a job seeker, I want discovered roles stored as lightweight opportunities, so that research does not create full application folders prematurely.
30. As a job seeker, I want exact duplicates merged by requisition ID or canonical URL and metadata-similar roles presented as reversible duplicate candidates, so that distinct requisitions are not silently collapsed.
31. As a job seeker, I want every discovery source preserved on the opportunity, so that provenance is not lost when duplicates are merged.
32. As a job seeker, I want hard eligibility constraints separated from ranking preferences, so that soft preferences do not silently reject viable roles.
33. As a job seeker, I want fit scores to show supporting and opposing evidence, so that ranking decisions are explainable.
34. As a job seeker, I want high-scoring roles prepared automatically when enabled, so that autonomy saves meaningful time.
35. As a job seeker, I want the authoritative fit evaluation rerun with the complete posting before application preparation, so that discovery scores are not treated as final.
36. As a job seeker, I want selecting a role to pursue to create one complete application record, so that all artifacts have a single owner.
37. As a job seeker, I want immutable sequential application, release, and submission identifiers, so that renaming a company or role cannot break history.
38. As a job seeker, I want readable company and role slugs around stable IDs, so that folders remain understandable without becoming identity keys.
39. As a job seeker, I want the original posting, source metadata, and capture time preserved, so that later changes do not erase the basis of my application.
40. As a job seeker, I want the posting rechecked before final review, so that material changes or closure are detected before submission.
41. As a job seeker, I want materially changed postings to invalidate readiness, so that stale documents are not submitted.
42. As a job seeker, I want closed roles marked expired rather than submitted, so that the pipeline remains truthful.
43. As a job seeker, I want tailored documents created inside the correct application, so that files never appear in arbitrary locations.
44. As a job seeker, I want imported resumes stored as immutable resources, so that tailoring never edits a source document in place.
45. As a job seeker, I want a clean LaTeX master generated from confirmed profile facts, so that documents use a consistent source of truth.
46. As a job seeker, I want LaTeX/PDF to be the canonical resume pipeline, so that typography and reproducibility remain strong.
47. As a job seeker, I want a validated DOCX export only when a portal requires it, so that format conversion is deliberate and traceable.
48. As a job seeker, I want cover letters generated only when required or strategically useful, so that the agent does not create generic filler.
49. As a job seeker, I want role-specific application narratives kept with that application, so that another employer never receives recycled company-specific prose.
50. As a job seeker, I want independent drafting and review passes, so that unsupported claims and missed requirements are caught before release.
51. As a job seeker, I want PDFs checked for readability, required contact information, placeholders, page constraints, layout defects, and ATS text order, so that compilation success alone is insufficient.
52. As a job seeker, I want validation failures to remain drafts, so that broken documents cannot become approved releases.
53. As a job seeker, I want editable drafts separated from append-only, tamper-evident releases, so that later edits cannot silently change what I approved.
54. As a job seeker, I want every release tied to source facts and checksums, so that document provenance can be audited.
55. As a job seeker, I want internal artifacts to use canonical names, so that agents never improvise version suffixes or final filenames.
56. As a job seeker, I want professional upload filenames generated from my name, employer, role, and artifact type, so that employer-facing files are clear.
57. As a job seeker, I want the exact local copies selected for upload snapshotted under the submission attempt, so that I can distinguish what the agent attempted to upload from what the employer later confirms receiving.
58. As a job seeker, I want portfolios, certificates, transcripts, references, and writing samples selected from canonical resources, so that filenames alone never trigger an upload.
59. As a job seeker, I want every additional attachment recorded in the submission manifest, so that the application package is complete.
60. As a reference provider, I want my contact details submitted only when permission and applicable role scope are recorded, so that my data is handled responsibly.
61. As a job seeker, I want the agent to fill complete applications using browser and computer-use capabilities, so that automation does not stop at document creation.
62. As a job seeker, I want required portal accounts prepared as part of a selected application, so that account creation is not a separate project.
63. As a job seeker, I want to handle passwords, passkeys, MFA, and verification codes myself, so that credentials are never stored by the agent.
64. As a job seeker, I want legal attestations and identity verification surfaced as human-interaction gates, so that the agent cannot acknowledge them on my behalf.
65. As a job seeker, I want these mandatory interactions treated as pauses rather than repeated workflow approvals, so that the agent resumes automatically afterward.
66. As a job seeker, I want unknown application questions asked only when they first occur, so that onboarding is not an invasive questionnaire.
67. As a job seeker, I want an eligible response saved according to its retention class after I provide it, so that the same fact is not requested unnecessarily on later applications.
68. As a job seeker, I want low-risk, semantically equivalent wording mapped to canonical question IDs, so that minor phrasing changes do not create duplicate questions.
69. As a job seeker, I want ambiguous or high-risk wording clarified and any reusable alias confirmed before it is learned, so that semantic differences are never silently erased.
70. As a job seeker, I want demographic and other sensitive answers handled only under an explicit retention and reuse policy, so that the agent never infers my identity or silently broadens my consent.
71. As a job seeker, I want “prefer not to answer” stored only when I explicitly choose it, so that non-disclosure is not selected on my behalf.
72. As a job seeker, I want canonical answers with jurisdictional and application-specific overrides, so that context-dependent answers remain accurate.
73. As a job seeker, I want a conflicting response classified as a one-off override, contextual override, or new default, so that the system never silently replaces my baseline.
74. As a job seeker, I want stable, low-risk answers retained until contradicted, so that I am not repeatedly asked for unchanged identity facts.
75. As a job seeker, I want every time-sensitive or high-risk answer governed by a field-specific freshness and review policy, so that legal, compensation, location, and availability answers remain accurate without relying on one global expiry period.
76. As a job seeker, I want factual answers separated from employer-specific narratives, so that only appropriate content enters the reusable answer bank.
77. As a job seeker, I want compensation stored with currency, period, range, location context, and flexibility, so that annual, hourly, and cross-currency answers cannot be confused.
78. As a job seeker, I want legal, preferred, display, and former names represented separately, so that the agent fills the exact field requested.
79. As a job seeker, I want passwords, codes, national identifiers, banking details, and identity documents excluded from the answer bank, so that dangerous secrets are not accumulated.
80. As a job seeker, I want unexpected requests for prohibited information flagged, so that suspicious applications stop safely.
81. As a job seeker, I want unanswered required questions queued when I am unavailable, so that the agent can continue preparing other applications without guessing.
82. As a job seeker, I want the answer bank to support list, update, scoped export, and deletion with a preview of surviving historical references, so that I understand and control where my data remains.
83. As a job seeker, I want answer audit events to omit historical sensitive values, so that change history does not become another sensitive database.
84. As a job seeker, I want prior submission snapshots left intact when a reusable answer is changed or deleted, so that historical records remain truthful.
85. As a job seeker, I want one concise final review of the employer, role, files, answers, new reusable answers, overrides, and anomalies, so that approval is informed without being repetitive.
86. As a job seeker, I want approval to originate from a trusted human interaction and be bound to a fingerprint of the exact payload reviewed, so that the agent cannot approve its own work or submit unreviewed material.
87. As a job seeker, I want material post-approval changes to trigger one updated review, so that conditional portal questions cannot bypass consent.
88. As a job seeker, I want the agent to click Submit after my one application-specific approval, so that I am not asked to approve every mechanical step.
89. As a job seeker, I want submission evidence to distinguish the planned payload, the payload observed before submission, and any values or artifacts confirmed by the employer, so that the system never overstates what the employer received.
90. As a job seeker, I want minimal evidence collection and redaction around sensitive fields, so that screenshots do not unnecessarily preserve private answers.
91. As a job seeker, I want an ambiguous result recorded as an uncertain submission, so that the agent never fabricates success.
92. As a job seeker, I want uncertain submissions checked against the portal and Gmail before retrying, so that duplicate applications are prevented.
93. As a job seeker, I want the application lifecycle to distinguish opportunity status, application stage, submission status, and outcome, so that unrelated concepts cannot overwrite each other.
94. As a job seeker, I want a generated local Markdown pipeline rebuilt from authoritative application manifests, so that I have a readable tracker without creating another source of truth.
95. As a Notion user, I want one-way automatic tracking updates after meaningful local changes, so that my dashboard stays current.
96. As a Notion user, I want only metadata and filenames synchronized by default, so that document contents remain local.
97. As a Notion user, I want failed synchronization recorded as pending without blocking local work, so that connector downtime cannot stop applications.
98. As a Gmail user, I want explicit recruiting events that satisfy the documented sender, thread, application-match, trust, and transition policies to update local state with message provenance, so that status tracking requires less manual work.
99. As a Gmail user, I want ambiguous, conflicting, and unmatched messages queued for review, so that email interpretation cannot corrupt application state.
100. As a Gmail user, I want reading and classification to leave messages, labels, and folders unchanged, so that synchronization has no inbox side effects.
101. As a job seeker, I want hired, offer-accepted, declined, and withdrawn outcomes to require explicit evidence or my instruction, so that consequential outcomes are never inferred from email.
102. As a job seeker, I want outreach and follow-up messages drafted but never sent without exact approval, so that communication remains under my control.
103. As a job seeker, I want interviews, follow-ups, and outcomes linked to the exact submitted release, so that later preparation reflects what the employer saw.
104. As a job seeker, I want offer and salary analysis to preserve sources, currencies, assumptions, and comparisons, so that decisions remain auditable.
105. As a job seeker, I want upskilling recommendations aggregated from real target-role gaps, so that development work serves my search strategy.
106. As a user, I want every governed mutation to follow the documented lock, journal, and atomic-replacement protocol on supported filesystems, so that concurrent Claude, Codex, hook, and browser tasks cannot corrupt state.
107. As a user, I want long-running operations checkpointed and idempotent, so that a crash can resume without duplicate applications, releases, submissions, or integrations.
108. As a user, I want temporary artifacts confined to run-specific managed directories, so that build files never leak into the repository root.
109. As a user, I want successful temporary work cleaned automatically, so that the workspace remains organized.
110. As a user, I want failed diagnostic bundles retained for seven days, so that errors can be investigated without permanent clutter.
111. As a user, I want cleanup to leave releases and submission evidence untouched, so that maintenance cannot erase career history.
112. As a user, I want schema migrations previewed and backed up before execution, so that harness upgrades cannot silently rewrite personal data.
113. As a user, I want reset actions divided into explicit scopes with deletion plans, so that a broad reset cannot erase more than intended.
114. As a user, I want remote Notion deletion separated from local reset, so that local cleanup cannot destroy external records accidentally.
115. As a user, I want logs to contain run IDs, transitions, references, checksums, and sanitized errors rather than personal content, so that diagnostics remain privacy-conscious.
116. As a maintainer, I want existing upstream portal, ranking, web-safety, PDF, lint, security, and update tests retained where applicable, so that proven behavior is not discarded.
117. As a maintainer, I want one synthetic end-to-end release gate, so that the complete user journey is verified at the highest useful seam.
118. As a maintainer, I want tests to use synthetic candidates, fake postings, mocked connectors, and a fake portal, so that automated verification can never contact a real employer.
119. As a maintainer, I want runtime conformance checks, so that Claude and Codex load the same skills and enforce the same workspace contract.
120. As a maintainer, I want hooks to provide warnings and defense in depth rather than core correctness, so that workflows remain safe when hooks are unavailable.

## Implementation Decisions

- The product is a standalone, local-first career workspace for one candidate. It is not a general Chief-of-Staff agent, hosted SaaS, recruiting-team product, or global plugin installation.
- The new implementation uses the audited upstream ai-job-search revision as a pinned source baseline. The upstream remote is retained, updates are review-only, and upstream code is adapted rather than copied from the older personalized fork.
- The useful upstream feature surface is inventoried in a parity matrix. Each capability is classified as preserve in V1, redesign in V1, defer, or remove. Deferred capabilities remain planned but do not block the initial release.
- Google Sheets, Chief-of-Staff wrappers, global resume and cover-letter output directories, CSV/JSON competing state, prompt-driven file movement, and company-role identity keys are removed.
- Planned workflows are career-namespaced skills: career-setup, career-expand, career-discover, career-rank, career-apply, career-pipeline, career-interview, career-outcome, career-gmail-sync, career-notion-sync, career-report, career-upskill, career-add-template, career-add-portal, career-reset, and career-doctor. Only skills required by the Initial Release Boundary must ship in V1.
- The portable Agent Skills collection is the only editable skill source. Claude discovers the same skills through an installer-created link or junction; a synchronized mirror is the fallback only when linking is impossible. The doctor command detects mirror drift.
- Claude and Codex retain small runtime-specific instruction entry points that load one shared career operating manual. Shared workflows describe capabilities instead of hardcoding runtime tool names. There is no legacy commands surface.
- Runtime tools remain responsible for reasoning, web research, browser and computer use, connector access, document inspection, and interaction with the user. The harness does not build a parallel browser, email client, or Notion client.
- The career CLI is the sole writer for governed state. It owns initialization, imports, stable IDs, paths, manifests, answer-bank operations, state transitions, releases, submissions, evidence registration, pipeline generation, sync checkpoints, doctor checks, schema migration, cleanup, and scoped reset.
- Ordinary drafts remain agent-editable. Hooks block or warn on direct writes to release artifacts, submission evidence, generated pipeline output, and protected manifest fields, but core correctness is enforced by CLI validation and checksum verification rather than depending on hooks. A checksum mismatch quarantines the affected artifact and invalidates readiness and any derived approval.
- Personal data is ignored by version control by default. The tracked repository contains code, schemas, templates, documentation, and synthetic fixtures only. Private versioning requires an explicit opt-in.
- The logical workspace consists of a profile area, canonical resources, opportunities, applications, and a generated pipeline. Resources include imported and master resumes, portfolios, certificates, reference data, and document templates.
- Tailored documents never live in shared resources. Each pursued application owns its posting snapshot, editable drafts, tamper-evident releases, submission attempts, interviews, and outcome.
- Imported originals are preserved unchanged and identified by checksums. Structured profile facts cite their source and confirmation state. Conflicts remain unresolved until the user chooses the canonical fact.
- Opportunity deduplication uses an exact employer requisition ID or canonical URL for automatic merges. Normalized company, title, location, and posting similarity produce reversible duplicate candidates for review rather than automatic merges. Every merge preserves the original records and source metadata and can be undone.
- Job evaluation separates explicit hard constraints from weighted preferences. Discovery ranking is preliminary; the complete posting receives an authoritative evaluation before application preparation.
- Stable sequential identifiers are assigned once: application IDs use a year-scoped sequence, while releases and submissions use application-local sequences. Human-readable slugs may change without changing identity.
- The state model uses four orthogonal dimensions. Opportunity status is discovered, evaluating, pursued, dismissed, or expired. Application stage is preparing, ready_for_review, approved, applying, submitted, or closed. Submission status is none, in_progress, uncertain, or confirmed. Outcome is offer_accepted, hired, rejected, withdrawn, no_response, or offer_declined. Interviews, offers, and other recruiting activity are timestamped event collections rather than singular application stages; the generated pipeline may derive a display phase from those events.
- An application reaches submitted only after confirmation evidence exists. An ambiguous external result remains at applying with an uncertain submission status. Uncertain attempts are never retried until the first attempt is proven unsuccessful.
- The posting snapshot contains the original content, source metadata, retrieval time, and freshness check. Material changes to responsibilities, location, compensation, eligibility, or availability invalidate readiness.
- LaTeX/PDF is the required canonical rendering pipeline for V1. The doctor command detects lualatex or xelatex, reports platform-specific installation guidance rather than silently installing a toolchain, and marks document-generation readiness as failed until a supported engine is available.
- The document release gate verifies compilation, PDF readability, required contact information, unresolved placeholders, page constraints, layout anomalies, extracted ATS text, and logical text order. A failed document remains a draft.
- DOCX is a secondary export only when required by a portal. It is generated from the same structured content and belongs to the same release manifest.
- Cover letters are generated only when required, enabled by the user's role strategy, or materially useful. Otherwise the application records that no cover letter was required.
- Every approved claim must resolve to imported evidence or a confirmed profile fact. Independent review may propose improvements, but unsupported claims cannot enter a release.
- Drafts are mutable; releases are append-only through supported operations and tamper-evident on read. A correction always creates a new release. Each release records its source facts, artifact checksums, validation results, and creation metadata. The CLI verifies release integrity before approval, upload preparation, submission, reporting, and migration.
- Internal release artifacts use fixed canonical names. Submission preparation creates employer-facing copies using a sanitized First_Last_Company_Role_Artifact convention and records the originating release path and checksum.
- Additional attachments are selected through typed metadata and application requirements, never filename similarity alone. The exact local copy selected for upload is preserved under the submission attempt without being misrepresented as employer-confirmed receipt.
- Reference records include permission state, applicable role scope, and confirmation date. A reference with missing or expired permission cannot be submitted.
- The answer bank grows during real applications rather than through an upfront questionnaire. An unknown question pauses for the user's answer; the response is stored only when its retention class allows storage and is reused only under its field-specific reuse policy.
- Answer records contain a canonical question ID, typed value, source, sensitivity, confirmation time, freshness policy, recognized wording aliases, and optional jurisdictional or application context.
- Registered low-risk wording variants resolve automatically. Ambiguous wording is clarified before reuse. Legal, demographic, compensation, authorization, sponsorship, disability, veteran-status, criminal-history, and other high-risk aliases require an exact registered template or user-confirmed alias mapping. Question polarity, time horizon, jurisdiction, units, and compound wording are validated before reuse.
- A canonical answer may have contextual overrides. When a new answer conflicts, the user classifies it as application-only, contextual, or a new default. One-off answers never silently replace the default.
- Stable, low-risk identity answers do not expire unless contradicted. Other fields use an explicit policy of stable, verify_on_conflict, verify_per_jurisdiction, verify_per_application, application_only, or expires_after. Work authorization, sponsorship, compensation, location, relocation, and notice-period fields may not rely on one global expiry period and are always surfaced in the final review when reused.
- Voluntary demographic and other sensitive responses may be stored only after explicit opt-in to their retention policy. The agent never infers them, never broadens their scope through alias learning, and stores “prefer not to answer” only when that is the user's explicit response.
- Passwords, passkeys, MFA codes, national identifiers, banking information, and identity-document contents are prohibited from the answer bank and diagnostic logs. Unexpected requests for those values stop and surface a warning.
- Compensation answers are structured by currency, period, range, location context, and flexibility. Conversion is allowed only when source and target units are explicit.
- Legal name, preferred name, display name, and former name are distinct profile fields. The agent fills only the meaning requested by the form.
- Reusable factual answers live in the answer bank. Employer- and role-specific narratives live in the application draft. Prior narratives may inform a new response but are never pasted unchanged by default.
- Answer updates use schema validation, locking, atomic replacement, and sanitized audit events. The audit records the key, action, time, and affected applications but not historical sensitive values. Deletion previews every surviving historical reference and whether it contains an exact value, redacted value, or digest. Existing submission snapshots remain tamper-evident, but sensitive snapshots follow the minimum-retention rules below.
- If a required question cannot be answered while the user is unavailable, the agent saves progress, adds the exact question to a needs-input queue, and continues other safe work rather than guessing.
- The browser workflow covers navigation, account preparation, form filling, document upload, validation, final review, submission, confirmation handling, evidence capture, and local state update.
- Required passwords, CAPTCHA, MFA, and identity checks are human-interaction gates, are never stored, and allow the workflow to resume after the user completes them. Account creation, acceptance of portal terms, and personal legal attestations are separately identified as consequential human consent; they cannot be completed or represented as accepted by the agent and must be included in the final payload review when they affect submission.
- Before submission, the agent presents one concise application-specific review containing employer, role, portal, uploaded filenames, every answer, newly stored reusable answers, contextual overrides, material attestations, and anomalies.
- Approval must originate from a trusted human interaction that the submitting agent cannot fabricate. It is bound to a deterministic fingerprint of the canonical submission payload and one submission attempt. Any answer, artifact, attachment, destination, attestation, material posting change, new conditional question, unverifiable portal-session restart, or approval expiry invalidates approval and requires one updated final review. Allowlisted presentation-only changes do not.
- After approval and an immediate fingerprint recheck, the agent clicks Submit and handles ordinary confirmation steps. The submission attempt separately records the planned payload, the payload observed before submission, and any values or artifacts confirmed by employer evidence, plus the URL, timestamps, receipt or application ID, checksums, and confidence of each evidence claim.
- Evidence collection is minimal. Screenshots of demographic, identity, or other sensitive fields are avoided; unavoidable diagnostic captures are redacted and governed by temporary retention.
- Application manifests and operation journals in the local workspace are the source of truth. The Markdown pipeline is a disposable generated projection, is never hand-edited, and can always be rebuilt. There is no Google Sheet.
- Notion is an optional one-way presentation adapter. Meaningful local state changes enqueue an automatic upsert of one row per opportunity or application. Only tracking metadata and filenames are sent by default, not document contents. Failed operations remain pending, and a manual sync can repair or rebuild the view.
- Gmail is an optional read-only event source. An event may update local state automatically only when the sender and thread are attributable to a known application, the extracted event is allowed by the state machine, the message is not attempting to instruct the agent, and the match satisfies a documented confidence policy. Ambiguous, conflicting, consequential, suspicious, and unmatched messages enter a review queue. Processing is idempotent by message ID and does not label, archive, delete, or otherwise mutate email.
- Gmail never infers hired, offer accepted, declined, or withdrawn. External messages remain drafts until the exact recipient and payload are approved.
- Application submission approval does not authorize later consequential actions. Withdrawal, offer acceptance or rejection, interview scheduling or cancellation, and every outbound message require their own explicit approval.
- All governed writes use schema versions, a documented lock-ownership and stale-lock recovery protocol, atomic replacement on supported filesystems, and operation journals. Each long-running operation has a run ID and safe checkpoints; rerunning it resumes or returns the existing result rather than creating duplicates. Unsupported network or synchronization filesystems fail readiness rather than receiving unsupported atomicity guarantees.
- Temporary rendering, extraction, browser diagnostics, and intermediate files live only in managed run directories. Successful runs clean them automatically. Failed diagnostic bundles expire after seven days through opportunistic cleanup on CLI startup and doctor runs. Releases and submission evidence are excluded from cleanup.
- Diagnostic logs contain run IDs, operations, state transitions, references, checksums, and sanitized errors. Answer values, resume contents, email bodies, credentials, and sensitive browser fields are redacted by default.
- Schema upgrades are explicit. Upgrade planning validates the workspace and previews migrations; application creates a recoverable backup and commits transactionally. Pulling repository updates never migrates personal data automatically.
- Reset is divided into explicit scopes such as generated drafts, temporary files, integrations, and all personal workspace data. It displays the exact deletion plan and requires confirmation. Remote Notion deletion and immutable submission-evidence deletion are separate explicit operations.
- The installer creates an isolated Python environment, installs pinned Python and portal dependencies, establishes skill discovery links, and runs the doctor command. It detects system-level prerequisites and connectors without installing or authenticating them silently.
- Both Unix and PowerShell installers are idempotent. Platforms without link privileges use a generated skill mirror, which the doctor command validates against the canonical source.
- The repository retains reviewed upstream portal adapters and their common search/detail contract, enablement flags, normalized structured output, bounded retries, source metadata, parser-health checks, and narrow permissions. Executable adapter dependencies are pinned with integrity metadata. No third-party or market-specific adapter is enabled until it is allowlisted and passes its contract and security tests.
- External pages, job descriptions, emails, imported documents, and portal content are untrusted data. They may inform career decisions but cannot override system instructions, approval rules, managed paths, or tool permissions.

## State Transition and Integrity Invariants

- `application.stage = submitted` requires at least one submission attempt with `submission.status = confirmed`.
- `submission.status = uncertain` keeps the application at `applying` and prohibits another submission attempt until the uncertain attempt is explicitly resolved as confirmed or unsuccessful.
- A confirmed submission attempt references exactly one unexpired approval record and one canonical payload digest.
- Every canonical payload references tamper-evident release and attachment checksums. A checksum mismatch invalidates the payload and its approval.
- A material posting change moves an application in `ready_for_review` or `approved` back to `preparing`. Closure of the posting prevents a new submission attempt but does not erase application history.
- Expiring or dismissing an opportunity cannot overwrite the state or history of an application already created from it.
- An outcome requires an application history and explicit user instruction or attributable evidence. Gmail and portal interpretation cannot infer `offer_accepted`, `hired`, `withdrawn`, or `offer_declined`.
- Interviews, interview rounds, follow-ups, and offers are repeatable events. They may affect a derived pipeline display phase but do not bypass application or submission transitions.
- Administrative closure without a terminal outcome records an explicit closure reason and remains distinguishable from rejection, withdrawal, no response, and offer decisions.
- All state changes, including connector-derived changes, pass through the same CLI transition validator. A connector cannot write state directly or bypass an invariant.
- Sequential IDs are allocated while holding the workspace registry lock, are never recycled, and may contain gaps after interrupted or rolled-back operations.
- The generated pipeline contains no independent state. Deleting it and regenerating it from valid manifests and journals produces an equivalent view.

## Submission Approval Contract

Before requesting approval, the CLI creates a canonical submission payload containing:

- application and submission-attempt identifiers;
- posting snapshot identifier, checksum, and freshness result;
- release and attachment identifiers, employer-facing filenames, and checksums;
- normalized portal field identifiers and proposed values;
- human-completed attestations and account or terms-consent events relevant to submission;
- unresolved anomalies and evidence limitations; and
- portal destination and the final irreversible action.

The payload uses deterministic serialization and a versioned digest algorithm. Approval records contain the payload digest, approval time, approving actor, runtime session, one-time nonce, and expiry. Approval is valid for one submission attempt and cannot be transferred to another application or regenerated payload.

Approval must originate through a runtime interaction whose user provenance is preserved and which the submitting agent cannot invoke as a bare self-approval flag. When a runtime cannot provide such an interaction, the workflow stops and asks the user to run an interactive CLI confirmation that displays the payload digest and summary. A model-authored assertion that the user approved is not sufficient evidence.

Immediately before the irreversible action, the CLI recomputes the canonical payload digest and checks approval validity. A mismatch, expired approval, reused nonce, or unverifiable browser state returns the application to final review. The implementation maintains an explicit allowlist of presentation-only portal changes that do not affect the payload.

## Answer Retention and Reuse Policy

Every answer type has one retention class and one reuse policy:

- `ordinary`: may be stored and snapshotted exactly; may use `stable` or `verify_on_conflict` reuse.
- `contextual`: stored with its jurisdiction, employer, role, location, or application scope; may be reused only when that scope matches.
- `high_risk`: may be stored as a proposed answer but must be surfaced in every final review and may require `verify_per_application` or `verify_per_jurisdiction`.
- `sensitive`: stored only after explicit retention opt-in; redacted from ordinary logs, default exports, diagnostics, and historical evidence.
- `prohibited`: never persisted in the answer bank, logs, diagnostic captures, submission snapshots, or generated views.

Historical submission records preserve the minimum evidence required to establish what was reviewed and attempted. Ordinary values may be retained exactly. Sensitive values are represented by a redacted value or keyed digest unless the user explicitly enables exact sensitive-history retention. Prohibited values are never retained.

Listing and export operations are redacted by default. Exact sensitive export requires explicit confirmation and an owner-only destination where supported. Deletion removes the reusable value and aliases, then reports every immutable or backup reference that survives; it must not claim full erasure when historical evidence remains.

## Runtime Capability Contract

The repository maintains a versioned capability matrix for Claude Code and Codex. For each capability it identifies whether V1 requires it, how each runtime supplies it, how doctor verifies it, and the safe degraded behavior when it is unavailable.

Workspace initialization, governed CLI mutation, approval binding, checksum verification, supported PDF rendering, persisted-state validation, and final submission safety are required capabilities. Missing required capabilities fail readiness. Gmail, Notion, automated discovery adapters, and other post-V1 integrations are optional and degrade to disabled or queued behavior without blocking local work.

Runtime conformance means that both runtimes discover the supported V1 workflows, call the same versioned CLI contracts, enforce the same invariants, and produce equivalent governed state for equivalent fixtures. It does not require identical model prose, tool names, browser implementations, or reasoning traces.

## Testing Decisions

- Tests assert externally observable behavior and persisted contracts rather than prompt wording, internal helper layout, or exact model prose.
- The primary seam is one synthetic end-to-end application journey through the real V1 skills and career CLI against a configurable local fake employer portal. This is the V1 release gate and the preferred location for workflow assertions. Optional post-V1 connectors have their own contract tests and do not block this journey.
- The primary journey covers importing a candidate resume, resolving profile facts, discovering and deduplicating a posting, evaluating fit, creating an application, generating and validating LaTeX artifacts, collecting and safely reusing an unknown answer, filling the portal, pausing for final review, binding trusted approval, submitting, distinguishing observed from employer-confirmed evidence, and regenerating the pipeline.
- A second end-to-end path forces an ambiguous portal result and proves that the application remains applying, the submission becomes uncertain, evidence is retained, and no automatic retry occurs.
- Connector contract tests cover successful idempotent upsert, unavailable connector, retry, duplicate event, ambiguous Gmail match, policy-qualified status event, suspicious content, and prohibited consequential inference.
- Document tests use synthetic profiles and deterministic fixtures. They verify compilation, required fields, placeholder detection, page constraints, layout signals, ATS extraction, logical order, checksums, PDF release creation, and portal-required DOCX export.
- Answer-bank tests cover first encounter, allowed exact reuse, user-confirmed aliases, rejected high-risk automatic aliases, ambiguous wording, polarity, time horizon, jurisdiction, field-specific freshness, contextual override, default replacement, sensitive opt-in and redaction, prohibited data, scoped export, deletion previews, and tamper-evident historical submissions.
- State-machine tests cover every allowed transition and cross-dimensional invariant, including submitted without confirmed evidence, retry while uncertain, terminal outcomes without valid history, connector attempts to bypass transitions, material posting changes after approval, and repeated interview and offer events.
- Approval contract tests prove that an agent cannot self-approve, approval is bound to one canonical payload and attempt, nonce reuse fails, expiry fails, every material mutation invalidates approval, allowlisted presentation-only changes do not, and the final digest is checked immediately before the irreversible action.
- Filesystem tests verify stable IDs, canonical internal names, sanitized external filenames, collision resistance, path traversal rejection, symlink escape rejection, locking, atomic writes, interruption recovery, idempotent replay, managed cleanup, release tamper detection, and approval invalidation.
- Discovery tests retain upstream adapter suites and cover normalized search/detail output, retries, enablement, source provenance, parser health, robots decisions, deduplication, deadline handling, and ranking-state updates.
- Migration tests use anonymized disorder fixtures representing shared resume folders, duplicate final files, date-based application folders, missing manifests, old tracker rows, temporary LaTeX artifacts, uncertain submission history, and Google Sheet metadata. Migration remains copy-first and preserves uncertainty.
- Runtime conformance tests verify that Claude Code and Codex discover the required V1 workflows, load the same shared rules, call the same CLI contracts, enforce the same invariants, report capabilities accurately, and produce equivalent governed state.
- Installer tests run in clean Unix fixtures and the declared supported Windows environment, covering repeated installation, missing LaTeX, missing connector authentication, link and mirror modes, dependency pinning, and doctor diagnostics.
- Security tests verify version-control exclusions, owner-only permissions where supported, untrusted-content boundaries, narrow executable permissions, secret redaction, protected paths, destructive-reset previews, and the absence of real network submission in automated tests.
- The fake portal supports adversarial modes for a conditional question appearing after approval, polarity changes, client-side value normalization, rejected uploads, session expiry, delayed submission, duplicate clicks, partial success, missing confirmation, network failure after external submission, and confirmation evidence that does not echo the complete payload.
- Recovery tests crash the workflow before and after every governed checkpoint, including after an external submission but before the local journal commit, and prove that replay neither loses evidence nor creates a duplicate attempt.
- Concurrency tests cover simultaneous ID allocation, stale-lock recovery, two runtime processes targeting the same application, and unsupported synchronization or network filesystems.
- Trust-boundary tests place adversarial instructions in job descriptions, emails, imported resumes, filenames, portal fields, and confirmation pages and prove that untrusted content cannot alter approval, paths, permissions, policy, or executable configuration.
- Manual compatibility checks may exercise representative real portal families without submitting, uploading real personal documents, or treating those checks as automated release evidence.
- Existing upstream portal, PDF, layout, ranking, lint, security, version-check, and update-triage tests are retained or adapted where they still test the chosen contract.
- No automated test may sign into a real employer portal, upload a real person's documents, send a message, mutate a real inbox, write to a production Notion workspace, or click a real Submit button.

## Out of Scope

- General Chief-of-Staff, second-brain, marketing, design, personal-operations, and unrelated productivity workflows.
- Google Sheets or any spreadsheet as a pipeline source of truth.
- A hosted web application, cloud database, multi-user workspace, recruiter product, or team collaboration platform.
- Multiple candidate identities inside one repository.
- Building replacements for Claude Code or Codex web search, browser, computer use, email, Notion, document, PDF, or approval capabilities.
- A broad port-adapter framework or custom MCP server when host capabilities and the local CLI are sufficient.
- Automatic authentication, password management, CAPTCHA bypass, MFA interception, identity verification, or legal attestation on the user's behalf.
- Final application submission without one trusted human approval bound to the exact reviewed canonical payload.
- Automatic submission retry after an uncertain result.
- Automatic withdrawal, offer acceptance, offer rejection, interview scheduling changes, or outbound message sending without a separate explicit approval.
- Inferring voluntary demographic answers, legal identity, work authorization, salary units, or consequential outcomes.
- Custom application-level encryption or secret storage. Users requiring encryption at rest must use an encrypted filesystem or device.
- Automatic deletion of imported source files, legacy workspaces, tamper-evident releases, submission evidence, or remote Notion records.
- A database, event-sourcing platform, distributed transaction system, telemetry service, or enterprise observability stack in the initial version.
- Blindly enabling every market-specific job portal or adding executable third-party adapters without review and tests.

## Further Notes

- The pinned upstream baseline audited for this effort is revision 27eb57ae93498cddba6268d3dd84d721daa1fa0c. It is a provenance point, not an instruction to preserve upstream's Claude-only layout or unreliable file lifecycle.
- The existing personalized career agent is a migration reference only. Its candidate data, Chief-of-Staff wrappers, Google Sheet integration, broad permissions, and older tool revisions must not become the new foundation.
- The current new repository contains planning documents only. No production harness, skills, CLI, installer, hooks, schemas, or tests have been implemented yet.
- The highest-value implementation slice is the V1 reliable application loop: confirmed profile evidence, reversible opportunity deduplication, application-owned drafts, validated LaTeX release, risk-aware answer learning, full browser filling, trusted final approval, evidence-qualified submission record, and generated pipeline.
- V1 completion means that after any application run, a user or a fresh agent can establish—without guessing—the posting used, confirmed supporting facts, current draft, approved release, local files selected for upload, planned and observed answers, employer-confirmed evidence, submission status, next action, and any evidence limitations.
- Before an implementation ticket becomes `ready-for-agent`, it maps each requirement it owns to the relevant CLI command, persisted schema, invariant, failure behavior, and acceptance test. Once that reviewed issue set exists, the specification status becomes `decomposed`; implementation proceeds through the tickets rather than by treating the full specification as one agent task.
