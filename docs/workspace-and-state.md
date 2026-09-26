# Workspace and state

Each initialized workspace has `workspace.json` with a random stable ID, schema version, and `single_candidate` kind. Personal data lives outside the product checkout by default. `profile/`, `resources/`, `opportunities/`, `applications/`, `runs/`, and `journals/` contain authoritative or recovery-supporting state.

Use the CLI as the only writer. Files are checksum-addressed where appropriate, writes are atomic, sequence allocation is locked, and consequential operations are journaled. These controls are tamper-evident through governed interfaces; they are not tamper-proof against the machine owner.

`career doctor` and `career onboarding status` are read-only. Recovery, cleanup, migration, and reset require a separate plan or preview and an unchanged digest-bound apply. Back up the entire workspace together. Never restore only a journal or registry file into a newer workspace.

Legacy repository-local data is not moved automatically. Preview a migration and inspect its exact copy plan before applying it.
