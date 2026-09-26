# Configuration

Career Agent resolves one active single-candidate workspace in this exact order:

1. Global `--workspace <path>` on the current command.
2. `CAREER_WORKSPACE`.
3. The atomic user configuration written by `career workspace select <path>`.
4. The platform-specific user-data directory chosen by `platformdirs`.

The current directory is never an implicit workspace. Run `career workspace show --json` to see the canonical path, stable workspace ID, schema version, and selection source.

Capability declarations are intentionally narrow. `CAREER_RUNTIME` may identify `codex` or `claude_code`. Browser, approval, web, Gmail, Notion, and collaboration declarations use `CAREER_*_CAPABILITY=1`; Doctor labels these as declarations, not independently verified remote access. Core, document, and submission readiness are reported separately.

Do not put API keys, credentials, or personal answers in the repository, skill files, configuration file, or capability variables.
