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
| GET    | `/pulls?repo=...` | List PRs on a subject repo with last Verdict comment (PR review loop) |
| POST   | `/pulls/{n}/approve` | Submit APPROVE review + optional auto-merge |
| POST   | `/pulls/{n}/reject` | Submit REQUEST_CHANGES review |
| GET    | `/ci/...` | CI bridge endpoints (runs, artifacts, deployment approvals) |

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

Required GitHub repo secrets on `wayside-monitor` for the workflow:

| Secret | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | LLM completion on the runner |
| `HUGGINGFACE_TOKEN`  | Embedding calls on the runner (Inference Providers scope) |
| `GITHUB_TOKEN` (auto) | `pull-requests: write` for the bot comment |

Required Verdict pod env (mounted from the `challenge-app-secrets` K8s secret):

| Env var | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Same; for in-pod use of the agent endpoint (e.g. manual re-run from UI) |
| `HUGGINGFACE_TOKEN`  | Same |
| `SUBJECT_REPO_TOKEN` | Auth for `/pulls` GitHub calls; needs `Actions: R/W`, `Pull requests: R/W`, `Contents: Write` on the subject repo |
| `CI_BRIDGE_REPO`, `CI_BRIDGE_TOKEN` | Default subject for the CI bridge endpoints |

## Deployment (`deploy/`)

- `deploy/docker/Dockerfile` builds the frontend into static assets and runs nginx + uvicorn together inside one image.
- `deploy/docker/run_combined.py` is the container entrypoint.
- `deploy/helm/` packages the Helm chart, auto-published to `oci://ghcr.io/<owner>/charts/verdict` by the `helm-publish` job whenever files under `deploy/helm/` change.
- The container image references the secret `challenge-app-secrets` for `OPENROUTER_API_KEY`, `CI_BRIDGE_TOKEN`, `SUBJECT_REPO_TOKEN`, and (optional) `HUGGINGFACE_TOKEN`. The `huggingface_token` key is marked `optional: true` in the chart so the pod still starts when it is missing (the PR review endpoint then returns 503 until the key is added).

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
