# Documentation

Living documentation for `verdict`. Start with [architecture.md](architecture.md) if you want a system overview, or [design-decisions.md](design-decisions.md) if you want to understand the invariants behind the code.

## Files

- [architecture.md](architecture.md) — System architecture: layers, components, data flow, full HTTP surface, agents (standalone + legacy), sanitization layer, Approvals panel, Cluster Health (SSE), deployment.
- [design-decisions.md](design-decisions.md) — The "why" behind the architecture: invariants reviewers must preserve. D1–D15 (latest: D13 unified Approvals, D14 push-based Cluster Health, D15 LLM output sanitization).
- [crownlabs-infrastructure-guide.md](crownlabs-infrastructure-guide.md) — Authoritative setup guide for the CrownLabs four-VM deployment (mgmt + dev/test/prod), Argo CD installation, kubeconfig merge, and the wayside-monitor GitOps pipeline.
- [ci-hitachi-integration-draft.md](ci-hitachi-integration-draft.md) — How the legacy scenario-based agents (agent4/5/6) wire into GitHub Actions. Predates the standalone Phase B/C/D agents — kept for historical context.
- [hitachi-reference-docs/](hitachi-reference-docs/) — Authoritative `.docx` templates provided by Hitachi Rail: Product Description, SW Functional Architecture, Functional Requirements (xlsx), Emails, Test Procedure, VDD (G-TMP S0203 rev.01). The VDD drafter agent's prompt is anchored to the VDD template here; future agents that produce formal documents must do the same.
- [worklog.md](worklog.md) — Append-only session-by-session log. Not authoritative for current state, but useful as a chronological narrative.
- [release/](release/) — APCS-style release documentation bundle for the project itself, ingested by Agent 4 during the legacy CI run.

## Conventions

- Architecture documents must be kept in sync with the code. If a change in `agents/`, `backend/`, or `.github/workflows/` invalidates a section here, update the doc in the same PR.
- `design-decisions.md` is the place to add new invariants. Each decision should follow the `Decision / Why / Consequence for reviewers` shape.
- Code references use the `path/to/file.py:42` pattern so they remain navigable.

## For LLM-based PR review

Both `architecture.md` and `design-decisions.md` are written to be consumed as context by an LLM agent during pull-request review. They are intentionally dense, self-contained, and free of session-specific noise. When fed alongside the PR diff they should be sufficient for the agent to reason about whether a change preserves the system's invariants.
