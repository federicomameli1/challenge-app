# Worklog

Free-form, append-only notes on what was implemented in each working session. **Not authoritative** — for the current architecture see [architecture.md](architecture.md), for invariants see [design-decisions.md](design-decisions.md).

## Architecture summary (current)

Three-layer release-readiness console:

- **Frontend** — React + Vite + Tailwind, served at `:5173` in dev, statically by nginx in the container.
- **Backend** — FastAPI app at `backend/app.py`, exposes `/agents`, `/brain`, `/datasets`, `/health`.
- **Core agents** — `agents/agent4` (Phase 4, DEV→TEST), `agents/agent5` (Phase 5, TEST→PROD), `agents/brain` (orchestrator). Each agent is a LangChain `RunnableSequence` of pure state transforms over a `TypedDict` state.

The deterministic policy engines own the GO / HOLD verdict. The LLM layer (OpenRouter, behind `OPENROUTER_API_KEY`) only refines the natural-language explanation.

## Session entries

Append new entries below, newest at the top. Use the format:

```
## YYYY-MM-DD — short title
- bullet of what changed
- bullet of validation done
```
