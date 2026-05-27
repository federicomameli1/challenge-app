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
