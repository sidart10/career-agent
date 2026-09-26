# Architecture

Career Agent has three boundaries:

1. `.agents/skills/career-*` contains portable orchestration instructions. Every safety-critical skill carries a local `references/career-rules.md` copy.
2. `src/career_agent` is the deterministic Python engine and the only governed-state writer. Schemas and document templates ship under `career_agent.resources` and are read with `importlib.resources`.
3. The selected external workspace contains one candidate's evidence and state.

Codex discovers the canonical repository skills. The installer creates Claude Code links or mirrors without changing the canonical source. A version handshake covers the CLI, skill bundle, skill API, and supported workspace schemas.

Deterministic Gate A tests installation, artifacts, public CLI behavior, and a synthetic journey. Model-driven Gate B tests skill triggering and orchestration separately on a pinned host/model. A recorded proposal fixture is not described as a live model test.
