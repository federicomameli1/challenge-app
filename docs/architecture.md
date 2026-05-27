# Architecture

Release-readiness console that decides whether a software release can be promoted across the **DEV → TEST → PROD** pipeline. The system is structured as three layers: a React UI, a FastAPI orchestration backend, and a Python core of deterministic decision agents wrapped in LangChain pipelines.

## High-level diagram

```
┌────────────────────────┐       ┌────────────────────────┐       ┌─────────────────────────┐
│   frontend/ (React)    │  HTTP │   backend/ (FastAPI)   │  call │  agents/ (Python core)  │
│   Vite + Tailwind      │ ────▶ │   /agents /brain /...  │ ────▶ │  agent4 → agent5        │
│   Proxies /api → 8001  │       │   Pydantic schemas     │       │  brain orchestrator     │
└────────────────────────┘       └────────────────────────┘       └─────────────────────────┘
                                              │                              │
                                              ▼                              ▼
                                    ┌──────────────────┐         ┌────────────────────────┐
                                    │ datasets/        │         │ Optional OpenRouter    │
                                    │ apcs_bundles/    │         │ LLM (explanation only) │
                                    │ synthetic/       │         └────────────────────────┘
                                    └──────────────────┘
```

The flow at runtime:

1. The user picks a scenario or uploads an APCS bundle in the UI.
2. The frontend calls the backend, which validates input via Pydantic schemas.
3. The backend invokes the appropriate LangChain pipeline (`agent4`, `agent5`, or the `brain` orchestrator).
4. The pipeline ingests evidence, normalizes it, runs the deterministic policy engine, and assembles an explanation. If `OPENROUTER_API_KEY` is set, the explanation is refined by an LLM; otherwise the deterministic explainer is used.
5. A typed `Agent4Output` / `Agent5Output` / `BrainRunReport` is returned to the UI.

## Layer 1 — Frontend (`frontend/`)

- React 18 + Vite + Tailwind CSS.
- Talks to the backend through a Vite proxy: `/api → http://127.0.0.1:8001`.
- Tests run via Vitest + Testing Library.
- Build output (`frontend/dist/`) is served by nginx in the container image.

## Layer 2 — Backend (`backend/app.py`)

A single FastAPI module that:

- Exposes the HTTP surface (`/agents`, `/brain`, `/datasets`, `/health`).
- Loads `.env` at the repo root to enable optional LLM narration via OpenRouter.
- Validates input with Pydantic models and returns typed JSON.
- Handles custom dataset uploads and persists them under `datasets/apcs_bundles/custom/`.
- Dispatches to the right LangChain pipeline based on `agent_kind`.

### HTTP surface

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/health` | Liveness probe |
| GET    | `/agents/options` | List available agents and source adapter kinds |
| POST   | `/agents/validate` | Validate a dataset/bundle without running the agent |
| POST   | `/agents/scenarios` | Discover scenarios in a dataset |
| POST   | `/agents/run` | Run a single agent on a scenario |
| GET    | `/brain/options` | List orchestration options |
| POST   | `/brain/run` | Run the brain orchestrator (agent4 → agent5) |
| GET    | `/datasets/custom-sets` | List user-uploaded APCS bundles |
| POST   | `/datasets/custom-sets` | Upload a new APCS bundle |
| DELETE | `/datasets/custom-sets/{set_id}` | Remove a user-uploaded bundle |
| POST   | `/agents/pr-review/run` | Standalone PR-review agent (diff + docs → GO/HOLD report) |
| POST   | `/agents/vdd-drafter/run` | Standalone VDD drafter (release metadata + diff + docs → full markdown VDD) |
| GET    | `/pulls?repo=...` | List PRs on a subject repo with last `[Verdict] LLM Review` comment parsed |
| POST   | `/pulls/{n}/approve` | Submit APPROVE review + optional auto-merge (handles GitHub's self-approval 422) |
| POST   | `/pulls/{n}/reject` | Submit REQUEST_CHANGES review |
| GET    | `/commits?repo=...&branch=main` | List recent commits with last `[Verdict] Test Evidence` commit comment parsed |
| GET    | `/releases?repo=...` | List GitHub releases + detect committed VDD file under `VDDs/VDD-<tag>.md` |
| GET    | `/issues?repo=...&state=...` | List GitHub Issues on the subject repo (PRs filtered out) |
| POST   | `/issues` | Create a new ticket on the subject repo |
| PATCH  | `/issues/{n}` | Update ticket state (close/reopen), labels, title, body |
| GET    | `/deployments?repo=...` | Aggregate pending GitHub Environment approvals (Actions runs in `waiting`) |
| POST   | `/deployments/approve` | Approve pending environment review |
| POST   | `/deployments/reject` | Reject pending environment review (body required) |
| POST   | `/webhooks/argocd` | Receive ArgoCD `notifications-controller` events |
| GET    | `/health/apps` | Current Cluster Health snapshot (apps + rollup counts) |
| GET    | `/health/events/recent` | Last 64 raw ArgoCD events received (debug) |
| GET    | `/health/stream` | Server-Sent Events stream — bootstrap snapshot then per-event updates |
| GET    | `/ci/...` | Legacy CI bridge endpoints (runs, artifacts, deployment approvals, single-repo via `CI_BRIDGE_REPO`) |

### Agent kinds and aliases

The backend resolves several aliases to canonical agent identifiers:

- `agent4` ← `agent_4`, `release_readiness_analyst`, `release_readiness`, `release_analyst`
- `agent5` ← `agent_5`, `test_evidence_analyst`, `test_evidence`, `evidence_analyst`

## Layer 3 — Agents core (`agents/`)

Three sub-packages, each self-contained.

### `agents/agent4/` — Release Readiness Analyst (Phase 4)

Decides whether a candidate release can promote from **DEV → TEST**.

Pipeline (`lc_pipeline.py`) is a LangChain `RunnableSequence` of pure state transforms. Each step writes into a `TypedDict` state so it can later be ported to LangGraph nodes without rewriting the logic.

```
ingestion → normalization → policy → explanation → evidence-trace → schema-validate
```

| Module | Responsibility |
|--------|----------------|
| `adapters/structured_dataset.py` | Reads phase-4 CSV scenarios |
| `adapters/apcs_doc_bundle.py` | Reads APCS document bundles (Emails, Requirements, VDD, Test Procedure, Module Inventory) |
| `ingestion.py` / `generic_ingestion.py` | Build the `RawInputBundle` from the chosen adapter |
| `normalization.py` | Produce a `NormalizedEvidenceBundle` (canonical evidence shape) |
| `policy.py` | **Authoritative deterministic rule engine**. Recommends HOLD if any hard gate is violated, GO only when all pass |
| `explanation.py` | Build the natural-language explanation; optional LLM refinement |
| `evidence.py` | Attach traceable evidence references to each rule finding |
| `models.py` | Pydantic output schema (`Agent4Output`, `RuleFindings`, `Decision`) |

Hard HOLD conditions enforced by `Phase4PolicyEngine`:

1. Critical service unhealthy in DEV.
2. Unresolved ERROR/CRITICAL runtime issue in deploy logs.
3. Open blocker in email thread.
4. Mandatory module version mismatch.
5. Unmet conditional requirement (e.g. retest required before promotion).

### `agents/agent5/` — Test Evidence Analyst (Phase 5)

Decides whether the release can promote from **TEST → PROD** based on test-execution evidence.

Same pipeline shape as agent4 but with phase-5 specific ingestion. Required CSV inputs:

- `requirements_master.csv`
- `test_cases_master.csv`
- `traceability_matrix.csv`
- `test_execution_results.csv`
- `defect_register.csv`

Optional release calendar: `phase5_release_calendar.csv` or `release_calendar.csv`.

### `agents/rag/` — Lightweight RAG primitives (Phase B foundation)

Shared, dependency-free building blocks used by agents that need to ground LLM reasoning in project documentation:

- `chunker.py` — paragraph-based splitting (`chunk_document`, `chunk_directory`); blank-line separation, configurable min chars.
- `hf_embeddings.py` — HuggingFace Inference API client targeting the **router-based endpoint** (`router.huggingface.co/hf-inference/models/.../pipeline/feature-extraction`). Configurable model via `HF_EMBEDDING_MODEL`, requires `HUGGINGFACE_TOKEN`.
- `retrieval.py` — pure-Python cosine similarity + `top_k` ranking (no numpy).

### `agents/_sanitize.py` — Shared LLM-output guardrails (D15)

Every standalone agent passes its LLM output through this layer before surfacing it to users or persisting it:

- `cap_string(text, max_chars, label)` — bounded output size with a visible truncation marker, applied per-field AND on the final rendered markdown.
- `validate_choice(value, allowed, field_name)` — strict enum check; raises `SanitizationError` instead of corrupting downstream state.
- `extract_known_ids` / `unverified_ids` / `annotate_unverified` — regex-extract every `REQ-WMS-N` / `TC-WMS-N` reference from the LLM output, cross-check against the input context (retrieved chunks + diff + doc bundle), and inline-tag any identifier the model invented as `[unverified citation]`. Idempotent.
- `SECURITY_GUARDRAIL` — paragraph prepended to every system prompt. Tells the model that user-provided content (diff, docs, release notes, commit messages, email threads) is DATA, not instructions, and that embedded directives like *"ignore previous instructions"* must be ignored.

See [D15 in design-decisions.md](design-decisions.md) for the policy.

### `agents/pr_review/` — Cross-repo PR review agent (Phase B)

Standalone LLM-driven GO/HOLD analyzer for a pull-request diff against a project's documentation. Does **not** conform to the `BrainStage` interface (the input shape is fundamentally different from scenario-based agents; a brain adapter can be added later if chaining is needed).

```
diff + docs_dir → chunk docs → embed all chunks (HF)
                            → embed diff query (HF)
                            → top-K retrieval
                            → prompt build (system + context + diff + JSON instruction)
                            → OpenRouter LLM call
                            → coerce JSON → render markdown report
```

| Module | Responsibility |
|--------|----------------|
| `models.py` | Pydantic input/output (`PRReviewInput`, `PRReviewOutput`, `Highlight`, `Verdict`, `Severity`) |
| `prompts.py` | System prompt + JSON output instruction + context block renderer |
| `runner.py` | `PRReviewRunner` orchestrating the pipeline; `from_env()` factory wires real LLM and HF clients |

Used from two execution sites:

1. **Verdict backend** via `POST /agents/pr-review/run` (the endpoint runs the pipeline inside the Verdict pod on the mgmt cluster).
2. **The subject repo's GitHub Actions runner** via `git clone` of the verdict repo + `python .github/scripts/run_pr_review.py` (lets the workflow do the LLM call without exposing the Verdict pod to the public internet — see *Cross-repo PR Review* section below).

### `agents/vdd_drafter/` — VDD Drafting agent (Phase D)

Standalone LLM-driven generator of a full Version Description Document following the Hitachi template **G-TMP S0203 rev.01** (the official `.docx` lives in `docs/hitachi-reference-docs/06. VDD/`).

```
release metadata + cumulative diff + APCS bundle + module versions
    → build user prompt (release block, diff stat, full diff, docs, module table, section guide)
    → OpenRouter (markdown output, max_tokens=2000)
    → _strip_code_fences + cap_string to 80 KB
    → _audit_sections checks the seven canonical headings appear
    → markdown ready to commit to VDDs/VDD-<tag>.md
```

| Module | Responsibility |
|--------|----------------|
| `models.py` | Pydantic input/output (`VDDDraftInput`, `VDDDraftOutput`, `ModuleVersion`) |
| `prompts.py` | System prompt anchored to G-TMP S0203 rev.01 + sub-section hints |
| `runner.py` | `VDDDrafterRunner` orchestrating the pipeline; `from_env()` factory |

Canonical sections (from the Hitachi template):

1. Introduction (Purpose / Applicability / Terms / Reference Documents / Description of Changes from Previous Revision)
2. Version Description (Inventory of materials / Inventory of SCI contents)
3. Documentation Related to the Baseline
4. Sw Version Build
5. Changes Incorporated (Accepted / Not accepted)
6. Sw Version Limitation
7. Installation Instructions

Invoked from two sites mirroring `pr_review`:
- **Verdict backend** via `POST /agents/vdd-drafter/run` (manual re-runs from UI/expert mode).
- **wayside-monitor GH Actions runner** via `.github/scripts/run_vdd_drafter.py` in `deploy-prod.yml::generate-vdd`. Triggered when a release is published. Output is committed to `wayside-monitor/VDDs/VDD-<tag>.md` on `main`. Verdict UI Releases page detects the file via the GitHub Contents API and exposes an "Open VDD" link.

### `agents/subject_pipeline.py` — Test Evidence agent (Phase C)

The legacy `SubjectRepoPipeline` was wired into the Phase C flow as the Test Evidence agent. It is **not** a standalone module like `pr_review` and `vdd_drafter` — it lives at the top level of `agents/` for historical reasons (it predates the standalone pattern) — but it follows the same execution model:

- **Hard pre-checks** (deterministic): any failing test → HOLD; missing APCS bundle → HOLD. No LLM call when these fire — saves tokens and avoids hallucinated GO when the evidence is already against the change.
- **LLM synthesis** (when pre-checks pass): one OpenRouter call with the parsed pytest JSON + APCS bundle + commit info. System prompt anchored to Hitachi GBMS (REQ-WMS-007 model-revalidation pattern is an explicit HOLD rule).
- **Sanitization**: passes through `_sanitize.py` — decision strict to {GO, HOLD} with safe HOLD fallback on corruption, identifier cross-check vs APCS bundle + diff stat, per-field caps.

Invoked from the wayside-monitor GH Actions runner via `.github/scripts/run_test_evidence.py` in `deploy-test.yml::test-evidence`. The verdict is posted as a **commit comment** (not a PR comment) on the merged SHA via `gh api commits/{sha}/comments`. Verdict UI Releases page reads those comments via the GitHub API for the *Recent builds on main* section.

### `agents/brain/` — Orchestrator

Generic dependency-aware stage runtime that chains agents:

- `models.py` — `BrainRunReport`, `BrainRunRequest`, `StageDependency`, `DependencyPolicy`, `StageExecutionResult`
- `stages.py` — `BrainStage` ABC, `StageExecutionContext`, `StageRegistry`
- `orchestrator.py` — `BrainOrchestrator` engine that:
  - executes stages in configured order,
  - validates dependency outcomes before each stage,
  - applies gating policies: `require_success`, `require_go`, `allow_any`,
  - emits a typed run report with stage results and handoffs.

The default plan is `agent4 → agent5`, but the architecture is intentionally generic so future stages (`agent6`, `agent7`, …) can be added without touching the engine.

## Determinism boundary

**This is the most important invariant.** Decisions are deterministic. LLMs only refine the natural-language explanation, never the GO/HOLD verdict.

- The policy engines in `agent4/policy.py` and `agent5/policy.py` produce structured `RuleFindings`. The decision is a pure function of the normalized evidence.
- `explanation.py` then builds a human-readable summary. If `OPENROUTER_API_KEY` is set and `--use-llm` is passed, the summary is rephrased via OpenRouter; otherwise the deterministic explainer is used.
- This means agent output is auditable: identical input always produces identical decisions and rule findings.

## Data flow — datasets and bundles

The agents accept two kinds of input source:

### Structured datasets (`datasets/synthetic/`)

CSV-based scenarios under `phase4/{v1,v2}/` and `phase5/{v1,v2}/`. Used for testing and reproducible runs.

### APCS document bundles (`datasets/apcs_bundles/`)

Document-based scenarios mimicking real engineering artifacts:

- `reference/` — original GO / HOLD reference bundles
- `baseline/` — v1.1.x bundles (`GO_STABLE`, `HOLD_*`)
- `premium/` — v1.2.0 multi-thread bundles
- `adversarial/` — v1.3.0 reasoning stress tests
- `colleagues/` — external contributor sets (v1.3.10+)
- `custom/` — bundles created at runtime via the UI

A bundle contains five plain-text artifacts:

```
APCS_Emails.txt
APCS_Module_Version_Inventory.txt
APCS_Requirements.txt
APCS_Test_Procedure.txt
APCS_VDD.txt
```

The `apcs_doc_bundle` adapter parses these files into the same `RawInputBundle` shape the structured adapter produces, so the rest of the pipeline is agnostic to the source format.

## CI/CD integration (`.github/workflows/ci.yml`)

The workflow embeds the agents directly into the release pipeline:

| Step | Agent | Purpose |
|------|-------|---------|
| `analyze-pre-test` | `agent4` | DEV→TEST readiness from the current change set |
| `approve-test` | — | Human gate (protected GitHub Environment) |
| `test-and-build` | — | Existing test/build logic |
| `analyze-pre-prod` | `agent5` | TEST→PROD readiness after tests/build |
| `approve-prod` | — | Human gate |
| `deploy-prod` | — | GitOps handoff |

The CI driver is `scripts/eval/run_ci_analysis.py`. It collects CI-native evidence, synthesizes a temporary structured dataset for the target gate, invokes the LangChain pipeline, and writes:

- `ci_report.json` and `ci_report.md`
- `agent_payload.json`
- `changed_files.txt`, `diff_stat.txt`

Configuration secrets/vars:

- `OPENROUTER_API_KEY` — enables LLM narration layer
- `OPENROUTER_MODEL` — optional model override
- `GITOPS_REPO`, `APP_NAME`, `GITOPS_TOKEN` — used by the prod handoff job

See [ci-hitachi-integration-draft.md](ci-hitachi-integration-draft.md) for the integration notes.

## Cross-repo PR Review (Verdict-as-gate, Phase B)

Verdict runs on the CrownLabs management cluster as a single deployment behind a private NodePort — it is **not exposed to the public internet**. The subject application (`wayside-monitor`) lives in its own repo and is deployed across `dev`/`test`/`prod` clusters via GitOps. The PR review loop crosses these boundaries without a tunnel:

```
                ┌──────────────────────────────────────────────────────────────┐
                │  Developer opens PR on wayside-monitor                       │
                └─────────────────────────────┬────────────────────────────────┘
                                              │
                ┌─────────────────────────────▼────────────────────────────────┐
                │  GH Actions runner (public)                                  │
                │  workflow: .github/workflows/verdict-llm-review.yml          │
                │   1. checkout wayside-monitor + verdict (shallow clone)      │
                │   2. python .github/scripts/run_pr_review.py                 │
                │      → imports agents.pr_review from the verdict clone       │
                │      → calls HF Inference + OpenRouter                       │
                │      → renders markdown report                               │
                │   3. upload report+JSON as workflow artifact                 │
                │   4. gh pr comment ← posts "[Verdict] LLM Review" markdown   │
                └─────────────────────────────┬────────────────────────────────┘
                                              │ (GitHub stores comment + artifact)
                                              ▼
                ┌──────────────────────────────────────────────────────────────┐
                │  Verdict UI (on mgmt, private NodePort)                      │
                │   - GET /pulls?repo=...                                      │
                │       fetches open PRs via GitHub API and parses the latest  │
                │       "[Verdict] LLM Review" comment from each.              │
                │   - POST /pulls/{n}/approve                                  │
                │       submits APPROVE review + optional auto-merge.          │
                │   - POST /pulls/{n}/reject                                   │
                │       submits REQUEST_CHANGES with the provided body.        │
                └──────────────────────────────────────────────────────────────┘
```

Key design properties:

- **No public exposure of Verdict.** The compute happens on the GH runner; Verdict consumes the result via the GitHub API. The SUBJECT_REPO_TOKEN inside the Verdict pod authenticates outbound calls only.
- **Single source of truth for the agent logic.** The `agents/pr_review/` module lives in the `verdict` repo; the workflow clones verdict at runtime and imports the module, so the prompts/embeddings/coercion logic isn't duplicated.
- **No persistent storage in Verdict.** The PR history is GitHub; Verdict reads it on demand. Adding caching/persistence is straightforward later (Phase F-style).
- **GO/HOLD is advisory.** The verdict drives the human reviewer's decision but does not enforce branch protection. The "Approve" button in the UI submits a GitHub PR review APPROVE and (by default) calls the merge API.

Required GitHub repo secrets on `wayside-monitor` for the workflows:

| Secret / Variable | Purpose |
|---|---|
| Secret `OPENROUTER_API_KEY` | LLM completion on the runner (pr_review, test_evidence, vdd_drafter) |
| Secret `HUGGINGFACE_TOKEN`  | Embedding calls on the runner (Inference Providers scope, only pr_review uses RAG) |
| Secret `GITOPS_TOKEN` | PAT scoped to `wayside-monitor-gitops` for the deploy workflows + scoped to `wayside-monitor` for the VDD commit |
| Variable `OPENROUTER_MODEL` | Optional model override (default `z-ai/glm-4.5-air:free`); upgrade to `meta-llama/llama-3.3-70b-instruct:free` or similar for stricter output |
| Secret `GITHUB_TOKEN` (auto) | `pull-requests: write`, `contents: write` for bot comments / VDD commit |

Required Verdict pod env (mounted from the `challenge-app-secrets` K8s secret — name pre-dates the rename, see [feedback-chart-legacy-names](#) in memory):

| Env var | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | LLM client (manual re-runs from `/agents/...` endpoints) |
| `OPENROUTER_MODEL` | optional model override |
| `HUGGINGFACE_TOKEN` | embeddings (manual pr_review re-runs); `optional: true` on the secret ref so the pod still starts without it |
| `SUBJECT_REPO_TOKEN` | auth for `/pulls`, `/issues`, `/commits`, `/releases`, `/deployments`; needs `Actions: R/W`, `Pull requests: R/W`, `Contents: Write`, `Issues: R/W` on the subject repo |
| `CI_BRIDGE_REPO`, `CI_BRIDGE_TOKEN` | default subject for the legacy `/ci/...` bridge endpoints |
| `VERDICT_ALLOW_SELF_MERGE` | optional; `"true"` (default) silently skips GitHub's self-approval 422 and proceeds with the merge — flip to `"false"` for production |

## Unified Approvals panel (D13)

A single Verdict UI surface (`/pulls` route) hosts both human-gated decisions on the subject repo:

```
        ┌──────────────────────────────────────────────────────────┐
        │  /api/pulls?repo=…    /api/deployments?repo=…            │
        │       │                       │                          │
        │       ▼                       ▼                          │
        │  pulls_bridge.py        deployments_bridge.py             │
        │       │                       │                          │
        │       ▼                       ▼                          │
        │  github /pulls           github /actions/runs?status=     │
        │  + /issues/{n}/comments   waiting + /pending_deployments  │
        │       (latest                                             │
        │        [Verdict] LLM Review)                              │
        └──────────────────────────────────────────────────────────┘
```

Approve / Reject are routed through the same `SUBJECT_REPO_TOKEN`:

- PR `Approve & merge` → review APPROVE + merge API call (squash). The `VERDICT_ALLOW_SELF_MERGE` env var (default `true` for demo) decides whether GitHub's self-approval 422 is silently skipped to proceed with the merge or surfaced as an error.
- PR `Request changes` → review REQUEST_CHANGES with required body.
- Deployment `Approve deployment` → POST to `/actions/runs/{id}/pending_deployments` with `state=approved`.
- Deployment `Reject` → same endpoint with `state=rejected` and required body.

The same panel is exposed at `/api/pulls` and `/api/deployments` for programmatic clients (e.g. potential Slack/CLI integrations).

## Tickets (Phase F)

`backend/issues_bridge.py` mounted at `/issues`. List / create / patch GitHub Issues on the subject repo. The list endpoint filters out PRs because GitHub's `/issues` endpoint mixes them in. Requires `SUBJECT_REPO_TOKEN` extended with `Issues: Read and write`.

`frontend/src/modules/frontend-ui/TicketsPage.jsx` renders the list as cards with luminance-aware label chips (so dark-blue labels get white text, light-yellow labels get black text), a "+ New ticket" modal, and per-card "Close ticket". Auto-refresh every 60s.

## Cluster Health (Phase E — D14)

Push-based dashboard for ArgoCD app state across mgmt / test / prod. **No polling.**

```
ArgoCD apps (on mgmt, test, prod managed by Argo CD on mgmt)
        │   sync or health status changes
        ▼
argocd-notifications-controller (in ns argocd, already installed)
        │   POST http://verdict.verdict.svc.cluster.local/api/webhooks/argocd
        ▼
backend/health_bridge.py
   ├─ in-memory snapshot (Dict[app_name → AppHealthSnapshot])
   ├─ rollup counters (apps_healthy, apps_degraded, apps_out_of_sync)
   └─ async fan-out to every SSE subscriber
        │   text/event-stream on /api/health/stream
        ▼
HealthPage.jsx (EventSource)
   ├─ initial bootstrap snapshot event
   ├─ per-event app_update messages
   └─ grouped grid (one section per cluster)
HomePage Cluster Health widget
   └─ fetches snapshot once on mount; turns rose on any Degraded/OutOfSync
```

The webhook contract is defined by `deploy/argocd/notifications-cm.yaml` — a single template covering health, sync, and operation triggers with a default subscription that wires every existing AND future Argo CD Application without per-app annotations.

The nginx config has a dedicated `location /api/health/stream` block with `proxy_buffering off` and 24h read/send timeouts so SSE actually streams through the proxy.

## Deployment (`deploy/`)

- `deploy/docker/Dockerfile` builds the frontend into static assets and runs nginx + uvicorn together inside one image.
- `deploy/docker/run_combined.py` is the container entrypoint.
- `deploy/docker/nginx/default.conf` proxies `/api/` → uvicorn on 8001 and serves the SPA fallback. Has a dedicated `location /api/health/stream` block with `proxy_buffering off` + 24h timeouts so SSE actually streams (D14).
- `deploy/helm/` packages the Helm chart (currently `0.1.8`), auto-published to `oci://ghcr.io/<owner>/charts/verdict` by the `helm-publish` job whenever files under `deploy/helm/` change.
- The container image references the secret `challenge-app-secrets` for `OPENROUTER_API_KEY`, `CI_BRIDGE_TOKEN`, `SUBJECT_REPO_TOKEN`, and (optional) `HUGGINGFACE_TOKEN`. The `huggingface_token` key is `optional: true` so the pod still starts when missing.
- `deploy/argocd/notifications-cm.yaml` — ConfigMap applied **on the mgmt cluster** (`kubectl apply -f deploy/argocd/notifications-cm.yaml`) to wire ArgoCD's notifications-controller to Verdict's webhook. Defines one webhook service, one template, and three trigger groups (health / sync / operation) with a default subscription for every Application — no per-app annotation needed.

## Testing (`tests/`)

Pytest suite covering:

- `tests/agent5/` — Phase 5 ingestion, normalization, policy, label-check
- `tests/brain/` — orchestrator dependency gating, stage registry, end-to-end agent4→agent5

Frontend tests live in `frontend/src/**/*.test.jsx` and run via Vitest.

## Extensibility

The architecture is designed so that adding a new agent or a new evidence source does not change the core engines:

- **New brain stage** — implement `BrainStage`, register it in `StageRegistry`, add it to the stage order. Use this when the input is scenario-based (dataset + scenario_id + release_id).
- **New evidence source for an existing agent** — implement an adapter under `agents/agentN/adapters/` returning a `RawInputBundle`.
- **New LLM provider** — replace the OpenRouter call in `explanation.py` with another provider behind the same `LLM_GENERATE` callable interface.
- **New standalone agent (non scenario-based)** — follow the `agents/pr_review/` pattern: a lightweight package with `models.py`, `prompts.py`, `runner.py`, exposed via its own backend endpoint. This is the right shape when the input is ad-hoc (a diff, a doc, an arbitrary payload) and the LLM call **is** the analysis (no deterministic policy engine needed). Reuse `agents/rag/` for documentation grounding.
- **New external execution site** — the `verdict-llm-review.yml` workflow in `wayside-monitor` demonstrates the pattern: a GH Actions runner shallow-clones this repo, adds `agents/` to `PYTHONPATH`, and invokes a standalone agent inline. Suitable when the Verdict pod is not reachable from the runner (CrownLabs deployment).
