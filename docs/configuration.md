# Configuration

## Project and workspace are different

The **project** contains software and skills. The **workspace** contains your private career data. The normal workspace is `workspace/` inside the project, ignored by Git.

Project-local launchers pass an explicit absolute `--project` path. Direct engine invocations otherwise discover the nearest Career Agent project by walking upward from the current directory. An explicit invalid project fails rather than silently choosing another.

Workspace selection precedence is:

1. Explicit `--workspace`.
2. `CAREER_WORKSPACE` environment variable.
3. This project's `.career-agent/workspace.json` selection.
4. A legacy user-level configured selection.
5. This project's `workspace/`.
6. Legacy platform user-data default when outside a recognized project.

An environment override wins even over the project binding. Agents must show the resolved path and selection source before initialization/import, not assume that `workspace/` won.

## Selecting an existing workspace

Use the project's launcher with `workspace show --json` to inspect the choice. Use `workspace select` with an initialized path to select another workspace. The project binding records its identity and stores an internal location relatively, an external location absolutely. A missing or mismatched selected workspace is an error, not permission to initialize a replacement.

Changing a selection does not move any files. Moving an external workspace requires selecting its new location explicitly. Uninstall preserves the selection.

## Agent-host capabilities

Host identity and browser/document capability declarations are diagnostic inputs, not proof of an available tool or successful action. Optional unavailable tools should disable only their dependent workflows.

`CAREER_MODEL_PROVIDER` declares the provider actually used for interpretation. When set, a mismatch with the stored acknowledgement blocks consented operations until a new acknowledgement is recorded. The agent must establish this value honestly; the engine cannot discover or enforce the host's actual network routing. It is not an API key. Never store authentication secrets in workspace records.

See [security and privacy](security-and-privacy.md) for the processing boundary and [troubleshooting](troubleshooting.md) for failed selection and installation checks.
