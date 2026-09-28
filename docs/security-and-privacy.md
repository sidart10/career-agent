# Security and privacy

Career Agent stores authoritative workspace state locally as plaintext files. Disk encryption, operating-system account security, backups, malware protection, and access to the selected directory remain the user's responsibility. The default project-local `workspace/` is ignored by Git. Ignore rules do not protect already-tracked files or forced additions. Do not commit personal data. Cloud-synced and network workspace roots are unsupported; local plaintext is not encrypted by Career Agent.

Local-first does not mean data never leaves the machine. Deterministic import and validation run locally, but model-assisted interpretation may send selected extracted text to the active model provider through the agent host. Provider terms, retention, enterprise settings, network controls, and administrator policy apply. Career Agent cannot override or verify those controls.

Before proposal ingestion, `career privacy status` discloses this boundary and `career privacy acknowledge` records only policy version, provider label, and timestamp—not the resume prose. A policy-version change or mismatch with the declared `CAREER_MODEL_PROVIDER` requires a new acknowledgement. The declaration is not automatic provider detection or network enforcement. Metadata-only import preview does not return extracted text; the governed `import inspect` path requires acknowledgement. An agent host can still bypass that workflow by directly reading files, so it must obey the shipped instructions.

Logs and CLI errors redact known sensitive patterns, but redaction is defense in depth, not a guarantee. Do not paste credentials, authentication cookies, government identifiers, banking data, or portal secrets into prompts or governed answers. Sensitive and high-risk answers require explicit retention and reuse choices when a real application needs them; onboarding seeds neither implicitly.

Doctor is read-only. Deletion, cleanup, reset, migration, and recovery are explicit operations with previews or plans. Deleted local files may remain in backups, filesystem snapshots, provider retention systems, or Git history.

Report a suspected vulnerability privately using the process in [support](support.md). Do not include real candidate documents in a report.
