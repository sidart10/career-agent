# Release operations

Career Agent 0.1 is releasable only when all of these are fresh and passing:

- deterministic Gate A on every declared operating system and Python version;
- model-driven Gate B on the chosen pinned agent host/model, with approved cost and captured evidence;
- wheel and source-distribution allowlist checks plus isolated wheel execution;
- skill validation, installer rollback/repair/uninstall tests, schemas, lint, typing, and the full test suite;
- secret and personal-data scans over the publication history and both artifacts;
- complete public docs and a tested tagged-release install path;
- upstream attribution and a project license chosen by the owner.

Human release blockers still requiring an explicit owner decision are the project license, exact supported platform matrix, and Gate B host/model/budget. OCR is intentionally deferred in 0.1. Publication, repository visibility changes, package upload, and tag creation are human actions after technical gates pass.

Build with `uv build --no-sources`. Inspect both archives, install the wheel in an external clean environment, hide the source checkout, and exercise `career version`, packaged schemas/templates, initialization, and Doctor. Do not call the repository open source before the project license exists.
