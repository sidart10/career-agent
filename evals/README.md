# Skill evaluation packet

`skill-cases.json` is the versioned Gate B prompt set. Each public skill has positive, ambiguous, and negative cases. A release-candidate run must record the agent host version, exact model identifier, prompt-set revision, skill-bundle and CLI/API versions, JSON trace or command transcript, artifacts, deterministic assertions, and rubric result.

The evaluator checks correct triggering, irrelevant-skill non-triggering, public-command use, evidence discipline, privacy disclosure, human confirmation, refusal to fabricate, and refusal to invent submission authority. Retries are reported rather than hidden.

No live or scheduled evaluation is enabled by this repository. The owner must choose a supported host/model and explicitly approve the per-run and recurring cost before enabling it.
