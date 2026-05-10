# Documentation

Living documentation for `challenge-app`. Start with [architecture.md](architecture.md) if you want a system overview, or [design-decisions.md](design-decisions.md) if you want to understand the invariants behind the code.

## Files

- [architecture.md](architecture.md) — System architecture: layers, components, data flow, HTTP surface, deployment.
- [design-decisions.md](design-decisions.md) — The "why" behind the architecture: invariants reviewers must preserve.
- [ci-hitachi-integration-draft.md](ci-hitachi-integration-draft.md) — How the agents are wired into GitHub Actions for the DEV→TEST→PROD gates.
- [worklog.md](worklog.md) — Free-form session worklog (not authoritative).
- [release/](release/) — APCS-style release documentation bundle for the project itself, ingested by Agent 4 during CI runs.

## Conventions

- Architecture documents must be kept in sync with the code. If a change in `agents/`, `backend/`, or `.github/workflows/` invalidates a section here, update the doc in the same PR.
- `design-decisions.md` is the place to add new invariants. Each decision should follow the `Decision / Why / Consequence for reviewers` shape.
- Code references use the `path/to/file.py:42` pattern so they remain navigable.

## For LLM-based PR review

Both `architecture.md` and `design-decisions.md` are written to be consumed as context by an LLM agent during pull-request review. They are intentionally dense, self-contained, and free of session-specific noise. When fed alongside the PR diff they should be sufficient for the agent to reason about whether a change preserves the system's invariants.
