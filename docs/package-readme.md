# Career Agent

Career Agent 0.1 is supervised, repository-local early access for one job seeker. Its Python CLI owns governed state; repository-discovered Agent Skills orchestrate only the CLI's public contracts from Codex or Claude Code.

Download the project ZIP or clone the repository, open that folder in your local agent, and ask it to help set up your career agent. The default personal-data folder is the Git-ignored `workspace/` inside the project; an explicitly selected external workspace is also supported. The installer builds a project-local runtime, not a global command. This is a moving development preview, not a tagged stable release. This release supports workspace setup, evidence-backed profile construction, career preferences, opportunity capture and ranking, and application preparation. Browser-assisted submission is experimental and never gains authority during onboarding.

Career Agent is local-first, not local-only. Authoritative files are plaintext in the selected workspace, and model-assisted interpretation may send selected extracted text to the model provider configured by the host. Read [security and privacy](security-and-privacy.md) before using personal documents.

This repository is not open source until its owner chooses and adds a project license. The required upstream attribution is preserved separately in `THIRD_PARTY_NOTICES.md`.

Start with [installation](installation.md), then [onboarding](onboarding.md). The [documentation map](README.md) links every maintained guide.
