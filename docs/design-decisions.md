# Design Decisions

This document captures the **why** behind the architecture. It complements [architecture.md](architecture.md), which describes the **what**. When reviewing a change, this is the file to consult to understand which invariants must be preserved.

## D1 — Decisions are deterministic; LLMs only narrate

**Decision.** GO / HOLD outcomes are produced exclusively by the deterministic policy engines (`agent4/policy.py`, `agent5/policy.py`). Any LLM call is confined to rephrasing the natural-language explanation.

**Why.** The system is the audit trail for a railway-engineering release process. Decisions must be reproducible, explainable, and stable across runs. An LLM in the decision path would make verdicts non-reproducible and would undermine the auditability requirement.

**Consequence for reviewers.** A change that lets an LLM influence rule findings, decisions, or evidence references is a **structural violation**, not an enhancement. New LLM features must stay inside `explanation.py` or an equivalent narration boundary.

## D2 — Pipelines are LangChain `RunnableSequence`s of pure state transforms

**Decision.** Each agent is built as a chain of small functions that read and write a `TypedDict` state (`Agent4State`, `Agent5State`). Steps are stateless; state is the only carrier between them.

**Why.** This shape is intentionally LangGraph-compatible. The current implementation can be lifted into a graph runtime without rewriting business logic — only the orchestration substrate changes.

**Consequence for reviewers.** Avoid hidden side effects inside steps (no global mutation, no I/O outside ingestion). Adding a step should mean adding a node, not mutating siblings.

## D3 — Source of evidence is decoupled from the pipeline via adapters

**Decision.** Agents accept two source kinds today (`structured_dataset`, `apcs_doc_bundle`) through a common adapter contract. The pipeline only sees `RawInputBundle`.

**Why.** The system has to ingest two very different shapes — CSV scenarios for synthetic testing, and plain-text APCS documents for real engineering bundles — without forking the pipeline. An adapter layer keeps normalization, policy, and explanation source-agnostic.

**Consequence for reviewers.** A new evidence format should land as a new adapter under `agents/agentN/adapters/`, not as branching inside `ingestion.py` or `normalization.py`.

## D4 — The brain orchestrator is generic, not hardcoded to agent4 → agent5

**Decision.** The `BrainOrchestrator` works against a `StageRegistry` and a configurable `stage_order`. Agent 4 and Agent 5 are just two registered stages today.

**Why.** The challenge brief explicitly anticipates additional analysts (Agent 6, Agent 7…). Hardcoding the two-stage flow would force a rewrite at that point.

**Consequence for reviewers.** Avoid embedding agent-specific logic inside `orchestrator.py` or `stages.py`. Agent-specific behavior belongs in the stage implementation.

## D5 — Dependency policies, not dependency wiring

**Decision.** Stages declare dependency outcomes through `DependencyPolicy` (`require_success`, `require_go`, `allow_any`). The orchestrator gates execution based on these policies.

**Why.** Different gating semantics are needed at different stages — e.g. Phase 5 should only run if Phase 4 returned GO, but a future analytics stage might want to run regardless. Encoding this as data on the stage spec keeps the engine simple.

**Consequence for reviewers.** New gating semantics should appear as a new `DependencyPolicy` value, not as a special-case branch inside the orchestrator.

## D6 — Custom datasets persist on disk, not in memory

**Decision.** APCS bundles uploaded through the UI are written to `datasets/apcs_bundles/custom/` and reloaded at backend startup.

**Why.** The console is run locally (or inside a single container) and users expect uploaded sets to survive restarts. An in-memory store would be lost between sessions and would not match user expectations.

**Consequence for reviewers.** Changes that move custom-set storage in-memory or to ephemeral container state regress this behavior. If a database-backed store is added later, the migration must preserve any existing on-disk bundles.

## D7 — CI integration uses a synthesized dataset adapter

**Decision.** `scripts/eval/run_ci_analysis.py` collects CI-native evidence (diff, workflow files, charts, docs) and **synthesizes a temporary structured dataset** that the existing pipelines can consume, instead of building a CI-native ingestion path.

**Why.** Reusing the structured-dataset adapter lets the agents run unchanged in CI. Building a parallel CI-native ingestion path was rejected as premature — until the synthesized dataset proves insufficient, the simpler approach wins.

**Consequence for reviewers.** Improvements to CI fidelity should land as richer evidence collection in the CI script, not as agent-side changes.

## D8 — Frontend talks to backend through `/api` proxy, not absolute URLs

**Decision.** The Vite dev server proxies `/api` to `http://127.0.0.1:8001`. The frontend never hardcodes the backend URL.

**Why.** The container build serves the frontend statically through nginx alongside the backend, so the frontend must work against same-origin paths. Hardcoded URLs would break the container deployment.

**Consequence for reviewers.** Reject any change that introduces absolute URLs to the backend in frontend code.

## D9 — `strict_schema` and `fail_on_label_mismatch` are surfaced as HTTP errors

**Decision.** When the backend is configured with strict-schema or label-mismatch checks enabled, validation failures surface as 4xx HTTP errors with structured payloads, not as 200 responses with a warning field.

**Why.** Users running in strict mode are explicitly opting into hard failures. Soft failures (warnings buried in a successful response) would make these guards effectively invisible.

**Consequence for reviewers.** Don't reintroduce silent fallbacks to soft warnings in strict mode.

## D10 — APCS bundles are five fixed text files

**Decision.** An APCS document bundle is exactly five files: `APCS_Emails.txt`, `APCS_Module_Version_Inventory.txt`, `APCS_Requirements.txt`, `APCS_Test_Procedure.txt`, `APCS_VDD.txt`. The adapter assumes this contract.

**Why.** The challenge defines this artifact set as the documentary deliverable for a release. Accepting variable file lists would force the adapter into discovery logic and would weaken the equivalence with reference bundles.

**Consequence for reviewers.** Adding a new document type means extending the contract everywhere (adapter, normalization, fixtures, reference bundles), not just appending a file at upload time.


## D11 — Standalone agents skip the deterministic policy layer

**Decision.** For agents whose input is ad-hoc (PR diff, a single document, arbitrary text) and whose output is **guidance for a human reviewer** (not an auditable verdict), build them as standalone packages outside the agent4/agent5 mold: pydantic models, prompt templates, a runner that calls the LLM directly, no deterministic policy engine in front. The current example is `agents/pr_review/`.

**Why.** Forcing every agent through the scenario+dataset+ingestion+normalization+policy+evidence+explanation pipeline is correct for release readiness (where the GO/HOLD verdict is the system of record) but wasteful and confusing for advisory analyses. The PR review LLM **is** the analysis; there is nothing for a rule engine to compute. The deterministic boundary from [D1](#d1--decisions-are-deterministic-llms-only-narrate) still holds for agent4/agent5 because their outputs feed promotion decisions; standalone agents only emit suggestions that a human then turns into a GitHub PR action.

**Consequence for reviewers.** Don't retro-fit a `BrainStage` adapter around `pr_review` just for consistency. If a future agent needs to be chained with agent4/agent5 (e.g. a pre-test risk assessor), build a proper stage with a policy engine; if it's read-by-human guidance, follow the standalone pattern.

## D12 — Cross-repo execution: compute on the runner, consume on Verdict

**Decision.** When a subject repo's PR triggers an LLM analysis, the LLM call happens on the GitHub Actions runner (which shallow-clones the verdict repo to import the agent module), not on the Verdict pod. Verdict consumes the result by reading the PR comment via the GitHub API.

**Why.** The Verdict pod runs on CrownLabs behind a private NodePort. Exposing it publicly would require a tunnel (Cloudflare/ngrok), add auth, and create a permanent network surface. Pulling the result via GitHub API is asymmetric — Verdict can call out, but nothing needs to call in. This keeps the security posture minimal at the cost of duplicating compute (which is free on GH-hosted runners).

**Consequence for reviewers.** Do not add inbound webhooks to Verdict for subject-repo events. If a new analysis is needed, prefer "compute on the runner + persist as PR comment / artifact / commit". The Verdict pod's role is to read GitHub state and present it.

## D13 — Approvals are unified in one panel

**Decision.** The Verdict UI surface for "things waiting for my approval" hosts both **pull-request LLM reviews** and **GitHub Actions environment-gate approvals** (the deployments stuck in `status: waiting` because an Environment has a required reviewer). The sidebar entry is called *Approvals*, not *PR Review*.

**Why.** Treating these as two separate surfaces forced the reviewer to context-switch to GitHub Actions for every promotion. Both are "human gate, one click, decision derived from prior evidence" — semantically the same task. Verdict already had the backend wiring for both (`pulls_bridge` for PRs, the new `deployments_bridge` for environment gates) authenticated by the same `SUBJECT_REPO_TOKEN`. Putting them under one panel eliminates the GitHub trip.

**Consequence for reviewers.** Future work that adds a new gate (e.g. release-candidate sign-off, manual hotfix override) belongs in this same panel. Don't create yet another sidebar entry — keep the Approvals surface as the canonical "what needs my decision now" view.

## D14 — Cluster health is push-based, not polled

**Decision.** The Cluster Health page is fed by ArgoCD's `notifications-controller` posting events to `POST /webhooks/argocd` inside the cluster, then streamed to the browser via SSE on `GET /health/stream`. There is **no polling loop** in the Verdict backend or frontend.

**Why.**
1. **Real-time without round-trip pressure**: every transition is visible in the UI within hundreds of milliseconds. Polling at 30s would have shown stale state during the most demo-critical moments (a release going Degraded as it rolls).
2. **The ArgoCD notifications-controller already exists** in the standard install — only the ConfigMap had to be authored (`deploy/argocd/notifications-cm.yaml`). No new controller to deploy or maintain.
3. **No public exposure required**: ArgoCD on mgmt → Verdict on mgmt is an in-cluster service URL (`verdict.verdict.svc.cluster.local`). The webhook never leaves the cluster.
4. **Stateless backend**: the in-memory snapshot is rebuilt within seconds of any controller re-emit, so a Verdict restart loses at most one update cycle.

**Consequence for reviewers.** Don't add a polling fallback "just in case" — it would mask broken notifications config instead of surfacing it. If ArgoCD events stop arriving, the UI's "Live (SSE connected)" indicator dropping to "Offline" is the intended signal. Logs in `argocd-notifications-controller` are the authoritative diagnosis path.

## D15 — Every LLM-driven agent passes its output through a shared sanitization layer

**Decision.** Every standalone agent that produces user-facing output (`agents/pr_review`, `agents/subject_pipeline`, `agents/vdd_drafter`) calls into `agents/_sanitize.py` to apply, at minimum:

1. **Output size cap** (`cap_string`) per-field AND on the final rendered markdown — defense-in-depth against a runaway response.
2. **Enum strictness** (`validate_choice`) on every decision-typed field (`verdict`, `decision`). Subject pipeline soft-falls-back to `HOLD` on corruption; pr_review raises and the workflow surfaces the error.
3. **Identifier cross-check** (`unverified_ids` + `annotate_unverified`). Every `REQ-WMS-N` / `TC-WMS-N` reference the model cites is checked against the input context (retrieved chunks + diff for pr_review, full APCS bundle + diff for subject_pipeline). References the model invented get tagged inline as `[unverified citation]`. Idempotent.
4. **Prompt-injection guardrail** (`SECURITY_GUARDRAIL` prefix in every system prompt) instructing the model that user-provided content (diff, docs, release notes, commit messages, email threads) is DATA, not instructions.

**Why.** Without these, the LLM output is trusted by default. The risks: a fabricated REQ-WMS-N looks authoritative in a PR comment; a runaway response fills a committed file in the repo or chokes the dashboard; an embedded "ignore previous instructions" in a PR body steers the verdict; an unknown value in `verdict` corrupts the UI's state machine. All four are realistic with current free-tier models and observed in early demos.

**Consequence for reviewers.** Any new agent that emits LLM-derived content for users **must** route its output through `_sanitize.py` — adding a new agent without these guards is treated as a structural violation, on the same footing as adding a non-deterministic decision path under D1. The guardrail prefix and identifier cross-check are not optional polish — they are the difference between "advisory LLM assistant" and "system that can mislead a release decision".
