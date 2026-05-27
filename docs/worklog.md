# Worklog

Free-form, append-only notes on what was implemented in each working session. **Not authoritative** — for the current architecture see [architecture.md](architecture.md), for invariants see [design-decisions.md](design-decisions.md).

## Architecture summary (current)

Three-layer release-readiness console:

- **Frontend** — React + Vite + Tailwind, served at `:5173` in dev, statically by nginx in the container.
- **Backend** — FastAPI app at `backend/app.py`, exposes `/agents`, `/brain`, `/datasets`, `/health`, `/ci/...` (CI bridge), `/pulls/...` (PR review loop).
- **Core agents** — two families:
  - *Scenario-based agents* — `agents/agent4` (Phase 4, DEV→TEST), `agents/agent5` (Phase 5, TEST→PROD), `agents/brain` (orchestrator). Each is a LangChain `RunnableSequence` of pure state transforms with a deterministic policy engine; LLM refines explanation only.
  - *Standalone agents* — `agents/pr_review` (cross-repo PR analyzer), built on the shared `agents/rag` primitives (chunker + HF embeddings + cosine retrieval). The LLM call **is** the analysis; no deterministic policy.

The scenario-based agents own deterministic GO/HOLD verdicts. Standalone agents emit GO/HOLD as guidance for a human reviewer. For the cross-repo PR review loop the LLM runs on the GH Actions runner (not in the Verdict pod) — see [architecture.md → Cross-repo PR Review](architecture.md).

## Session entries

Append new entries below, newest at the top. Use the format:

```
## YYYY-MM-DD — short title
- bullet of what changed
- bullet of validation done
```

## 2026-05-28 — Closing the roadmap: Phases C–F, unified Approvals, sanitization layer

Major session arc: the remaining four phases of the roadmap landed, plus a unification refactor and a security/quality hardening pass on every LLM-driven agent.

### Phase C — Test Evidence Agent integration

The legacy `agents/subject_pipeline.py::SubjectRepoPipeline` (deterministic pre-checks + LLM synthesis on APCS bundle + test results + commit info) was re-wired to wayside-monitor's pipeline.

- **wayside-monitor**: new job `test-evidence` in `.github/workflows/deploy-test.yml`. Runs after `pytest --json-report`, downloads the test artifact, shallow-clones verdict to import `subject_pipeline`, then posts the verdict as a **commit comment** on the merged SHA via `gh api commits/{sha}/comments`. Output also uploaded as `wayside-test-evidence-${sha}` artifact.
- **wayside-monitor**: new wrapper `.github/scripts/run_test_evidence.py` that parses the pytest JSON via `test_report_parser`, reads the APCS bundle from `docs/`, builds commit info from `git`, and calls `SubjectRepoPipeline.analyze()`.
- **verdict backend**: new `backend/commits_bridge.py` mounted at `/commits`. Lists recent commits on a subject branch and parses the latest `[Verdict] Test Evidence` commit comment from each.
- **verdict frontend**: new `frontend/src/modules/frontend-ui/ReleasesPage.jsx` with a "Recent builds on main" section that surfaces each commit's verdict badge + inline-expandable full report.

### Phase D — VDD Drafting Agent (G-TMP S0203 rev.01)

The skeleton VDD that the old `deploy-prod.yml` step wrote by hand is now replaced by an LLM-drafted document anchored to the official Hitachi template.

- **verdict**: new standalone module `agents/vdd_drafter/` (Pydantic models, prompt templates, `VDDDrafterRunner`). The system prompt cites `G-TMP S0203 rev.01` as the source of truth. The user prompt lists the **seven canonical top-level sections** (Introduction / Version Description / Documentation Related to the Baseline / Sw Version Build / Changes Incorporated / Sw Version Limitation / Installation Instructions) with their sub-sections, extracted directly from the `.docx` template in `docs/hitachi-reference-docs/06. VDD/`.
- **verdict backend**: `POST /agents/vdd-drafter/run`. Also a new `backend/releases_bridge.py` mounted at `/releases` — lists tagged GitHub releases and probes the Contents API to detect whether the auto-drafted VDD file is committed yet (returns `vdd_url=null` until it lands → UI shows "VDD pending").
- **verdict frontend**: `ReleasesPage.jsx` gains a "Released versions" section above "Recent builds" with an "Open VDD" button per release.
- **wayside-monitor**: new wrapper `.github/scripts/run_vdd_drafter.py` that resolves the previous tag (`git describe --tags --abbrev=0 HEAD^`), computes the cumulative diff, reads the APCS bundle, extracts `__version__` from each top-level package's `__init__.py`, and calls the runner. `.github/workflows/deploy-prod.yml::generate-vdd` was updated to call this instead of the hand-rolled skeleton template.

### Hitachi GBMS alignment of all LLM prompts

After the first VDD draft came back with 8 invented sections that didn't match the Hitachi template, audited every prompt against `docs/hitachi-reference-docs/`.

- All three standalone agents (`pr_review`, `subject_pipeline`, `vdd_drafter`) now name the GBMS framework, the documentary artifacts (Functional Requirements, Test Procedure, VDD = G-TMP S0203, GBMS standards G-PRD S0200 / G-PRC S0201), and the WMS vocabulary (`REQ-WMS-XXX`, `TC-WMS-XXX`, module names) explicitly in the system prompt.
- The threshold-without-revalidation rule (REQ-WMS-007) is called out as an automatic HOLD pattern in pr_review and subject_pipeline.

### Phase F — Tickets (GitHub Issues mirror)

- **verdict backend**: `backend/issues_bridge.py` mounted at `/issues`. `GET /issues`, `POST /issues`, `PATCH /issues/{n}` — filters out PRs (GitHub's `/issues` endpoint mixes them in).
- **verdict frontend**: `TicketsPage.jsx` with card per issue (title, author, age, comments, assignees, luminance-aware label chips), inline-expandable description, "Close ticket" button, and a "+ New ticket" modal. Auto-refresh 60s.
- **verdict frontend**: HomePage Tickets widget shows the live open-issue count + link.
- Requires `SUBJECT_REPO_TOKEN` PAT extended with `Issues: Read and write`.

### Approvals unification — PR reviews + deployment gates in one panel

After noticing the deployment "Waiting" state on the test/production environment gates wasn't surfaced in Verdict (only on GitHub Actions), the PR Review tab was renamed **Approvals** and now hosts both.

- **verdict backend**: new `backend/deployments_bridge.py` mounted at `/deployments`. Aggregates every pending deployment across all subject-repo workflow runs in `status=waiting`. `GET /deployments`, `POST /deployments/approve`, `POST /deployments/reject` (rejection requires a body, per GitHub's API). Uses `SUBJECT_REPO_TOKEN`, same auth surface as the rest.
- **verdict frontend**: `PRReviewPage.jsx` retitled "Approvals". Gains a "Pending deployments" section above "Pull requests". Each deployment card shows environment name, workflow + run number, branch/sha, commit message, and Approve / Reject / Open run on GitHub. Approve is disabled when `current_user_can_approve` is false. Reject opens a modal with required body.
- Sidebar label updated `PR Review` → `Approvals`. Home widget renamed too.

### Phase E — Cluster Health (ArgoCD notifications + SSE)

Real-time cluster-state dashboard fed by ArgoCD's `notifications-controller`, with zero polling.

- **verdict backend**: new `backend/health_bridge.py`. In-memory snapshot + SSE fan-out:
  - `POST /webhooks/argocd` — ingests notifications events. Tolerant payload shape (flat or nested under `data`).
  - `GET /health/apps` — current snapshot with rollup counts (apps_healthy / apps_degraded / apps_out_of_sync).
  - `GET /health/events/recent` — last 64 events for debug.
  - `GET /health/stream` — text/event-stream. Sends a bootstrap `snapshot` on connect, then one `app_update` per webhook. Keepalive comment frame every 15s.
- **verdict nginx**: dedicated `location /api/health/stream` block with `proxy_buffering off`, 24h read/send timeouts — so SSE actually streams through.
- **verdict frontend**: `HealthPage.jsx` with grouped grid (one section per cluster). One card per ArgoCD app with health/sync/op-phase status pill, namespace, short revision, age, and "Open in Argo CD" link. Live connection indicator (green dot + Live label). Uses EventSource on `/api/health/stream` for incremental updates.
- **verdict frontend**: HomePage Cluster Health widget shows live counts and turns rose when any app is Degraded or OutOfSync.
- **operator action (one-time on mgmt)**: apply `deploy/argocd/notifications-cm.yaml` — defines the webhook service (`http://verdict.verdict.svc.cluster.local/api/webhooks/argocd`), a template, three trigger groups (health / sync / operation), and a default subscription that wires every existing and future Argo CD Application to send events to Verdict. No per-app annotation needed.

### Self-merge bypass — opt-in via env var

GitHub returns 422 when the PAT owner tries to approve their own PR. For single-developer iteration this blocked the demo flow, so the backend now silently skips the failing APPROVE step and proceeds with the merge.

- **verdict backend** `pulls_bridge.py`: new `_SelfReviewSkipped` exception; `approve_pull` catches it and records `review_state="SELF_REVIEW_SKIPPED"`. The bypass is gated by `VERDICT_ALLOW_SELF_MERGE` env var (default `true` for demo). To disable in production, set `env.allow_self_merge: "false"` in `verdict-gitops/environments/mgmt/values.yaml` (chart 0.1.8+ renders that into the pod's env).
- **verdict frontend**: post-action toast distinguishes "approved and merged" from "merged (self-review skipped — GitHub forbids approving your own PR)".

### LLM output sanitization (essential hardening)

After feedback that the LLM output should be controlled / sanitized, added a shared guard layer used by every standalone agent.

- **new file** `agents/_sanitize.py` exposes:
  - `cap_string(text, max_chars, label)` — bounded output size with a visible truncation marker.
  - `validate_choice(value, allowed, field)` — strict enum check; raises `SanitizationError`.
  - `extract_known_ids` / `unverified_ids` / `annotate_unverified` — regex-extract REQ-WMS-N / TC-WMS-N references, cross-check against the input context, and tag inline `[unverified citation]` any identifier the model invented. Idempotent.
  - `SECURITY_GUARDRAIL` constant — paragraph prepended to every system prompt instructing the model to treat user-provided content (diff, docs, release notes, commit messages, email threads) as DATA, not instructions.
- Applied across **pr_review** (per-field caps; cross-check vs retrieved chunks + diff; 50-highlight cap), **subject_pipeline** (per-field caps; decision strict to {GO,HOLD} with safe fallback to HOLD on corrupt output; cross-check vs APCS bundle + diff stat), **vdd_drafter** (markdown capped at 80KB).
- Smoke-tested end-to-end: an LLM payload citing `REQ-WMS-007` (real) and `REQ-WMS-999` (invented) gets the 999 reference tagged `[unverified citation]` in the rendered summary and in the matching highlight; the real one is left clean.

### CI / development ergonomics

- **verdict ci.yml**: `approve-test` and `approve-prod` jobs now have their `environment:` line commented out to drop the required-reviewer wait that was slowing single-developer iteration. The jobs remain in place as no-op steps so the dependency chain stays intact; restoring the gate is a one-line change.
- **verdict ci.yml** `helm-publish`: chart auto-published to `oci://ghcr.io/<owner>/charts` on every push that touches `deploy/helm/`.
- `frontend/.gitignore` and `wayside-monitor/.gitignore` updated to drop accidentally-tracked `*.tgz` Helm package artifacts.

### Roadmap snapshot at end of session

All six phases (A–F) plus the unification refactor are closed. The remaining work is the **pre-production cleanup checklist** tracked in the auto-memory: switching `VERDICT_ALLOW_SELF_MERGE` off, renaming the legacy `challenge-app-secrets` secret, retargeting `ci_bridge_repo` from `challenge-app` to `wayside-monitor`, swapping the OpenRouter model when budget allows, choosing a privacy-respecting LLM provider for Hitachi data residency, and re-aligning the scenario-based `agent4/5/6` legacy modules to Hitachi GBMS if they re-enter active use.

## 2026-05-26 — PR review loop (Phase A foundation + Phase B steps 1-3)

Built the end-to-end loop that lets a developer push a PR to `wayside-monitor`, get an automated LLM verdict, and approve/reject it from Verdict UI without exposing the Verdict pod to the public internet.

### New files (verdict repo)
- `agents/rag/` — paragraph chunker, HuggingFace Inference API client (router endpoint), cosine `top_k`. Pure Python, zero new deps.
- `agents/pr_review/` — `PRReviewRunner` (standalone, not BrainStage). Pipeline: chunk docs → embed → retrieve → LLM → coerce JSON → render markdown report.
- `backend/pulls_bridge.py` — new router mounted at `/pulls`:
  - `GET /pulls?repo=...&state=open` — list PRs + parse latest `[Verdict] LLM Review` comment.
  - `POST /pulls/{n}/approve` — submit APPROVE review + optional auto-merge.
  - `POST /pulls/{n}/reject` — submit REQUEST_CHANGES with required body.
  Reuses `CiBridgeConfig.for_subject_repo()` for auth via `SUBJECT_REPO_TOKEN`.

### Modified files (verdict repo)
- `backend/app.py` — wired both new routers (`/agents/pr-review/run`, `/pulls/*`).
- `deploy/helm/Chart.yaml` — bumped to **0.1.7**.
- `deploy/helm/templates/deployment.yaml`:
  - Inject `HUGGINGFACE_TOKEN` from `challenge-app-secrets` with `optional: true` so the pod survives a missing key (endpoint returns 503 instead).
  - Optional `HF_EMBEDDING_MODEL` env var via `values.env.hf_embedding_model`.
  - Quote the image string and conditionally append the tag (fixes the pre-existing `helm template` failure with default values when the tag is empty / digest-pinned).
- `.github/workflows/ci.yml` `helm-publish` job — push to `oci://ghcr.io/<owner>/charts` (was pushing to `<owner>/<repo>`, which created the abandoned `verdict/verdict` package on GHCR).

### New files (wayside-monitor repo)
- `.github/workflows/verdict-llm-review.yml` — triggers on PR open/sync against main:
  1. checkout wayside-monitor + verdict (shallow clone).
  2. `pip install pydantic`.
  3. `python .github/scripts/run_pr_review.py` with `PYTHONPATH=$GITHUB_WORKSPACE/.verdict-src`.
  4. upload `pr-review-output/` as artifact.
  5. `gh pr comment` posts the markdown report.
- `.github/scripts/run_pr_review.py` — wrapper that imports `agents.pr_review` from the verdict clone, computes `git diff origin/<base>...HEAD`, runs the runner, writes `report.md` + `result.json`.

### Validation
- End-to-end run on `wayside-monitor#1` (vibration threshold bump): workflow green in ~18s, comment posted, artifact uploaded. Verdict came back **GO** with one Info highlight — should have been HOLD per REQ-WMS-007 (model re-validation). Tuning deferred; the pipeline itself is sound.

### Known issues / next session
- **Phase B step 4 (frontend)** not started — backend `/pulls` endpoints exist but no UI yet.
- `f09102b` (pulls_bridge commit) on `new-dashboard` is **not yet on main** — needs PR + merge so the deployed pod has the new routes.
- LLM quality: `z-ai/glm-4.5-air:free` is too lenient; consider `meta-llama/llama-3.3-70b-instruct:free` via `OPENROUTER_MODEL` var on `wayside-monitor`. Prompt could be tighter on HOLD criteria. RAG retrieval missed `APCS_Requirements.txt#3` (the chunk holding REQ-WMS-007) — augmenting the diff query with the file's leading comments would help.
- `SUBJECT_REPO_TOKEN` needs `Pull requests: Read+Write` and `Contents: Write` (in addition to `Actions: R/W`) for the approve/reject endpoints to work; verify before testing.

## 2026-05-10 — Subject-repo agentic pipeline (wayside-monitor integration)

### New files
- `agents/test_report_parser.py` — parses `pytest-json-report` JSON output into a structured summary dict; `format_test_summary_for_prompt()` renders it for LLM context
- `agents/subject_pipeline.py` — two-stage pipeline: deterministic pre-checks (CI tests failed → HOLD, APCS missing → HOLD) short-circuit before the LLM call; Stage 2 sends APCS bundle + test results + commit diff to an OpenRouter LLM with a railway safety system prompt

### Modified files
- `scripts/eval/run_ci_analysis.py`
  - Added `--subject-run-id` CLI arg (env: `SUBJECT_RUN_ID`)
  - Added `fetch_subject_test_artifact(repo, run_id)` — downloads `wayside-test-report` artifact zip from GitHub Actions API, unzips, returns parsed JSON
  - Added `run_subject_pipeline_analysis(...)` — runs `SubjectRepoPipeline` instead of `LLMBundleAgent` when in subject-repo mode
  - `_run_pre_test_analysis()` now branches: fetches test artifact and calls subject pipeline for external repos; runs Agent 4 for self-review
  - SRP refactoring: split `_compute_heuristics()` → `_compute_local_heuristics()` + `_compute_subject_heuristics()`; extracted `_scan_event_markers()`, `_phase5_requirement_ids()`, `_run_agent_pipeline()` helper
  - Fixed Pylance `reportOptionalMemberAccess` errors (10) by assigning `.get()` to local vars before `isinstance` check
- `.github/workflows/ci.yml` (challenge-app)
  - Added `SUBJECT_RUN_ID` extraction from `client_payload` in "Resolve subject repo" step
  - Passes `${SUBJECT_RUN_ID:+--subject-run-id "$SUBJECT_RUN_ID"}` to `run_ci_analysis.py`
  - Fixed redundant `&& github.event_name != 'repository_dispatch'` in `approve-prod` and `deploy-prod`
- `backend/app.py` — added `python-dotenv` loading at startup
- `backend/requirements.txt` — added `python-dotenv>=1.0.0`

### wayside-monitor repo (separate repo)
- `.github/workflows/ci.yml` — added `pytest-json-report` install, `--json-report` flag to pytest, artifact upload step for `wayside-test-report`, and `subject_run_id: ${{ github.run_id }}` in dispatch payload

### Dashboard (previous session)
- `ReleaseDashboard.jsx` — dataset list split into "Bundled" (read-only, A4/A5 badges) and "Custom" (+ Upload button, delete only for custom) sections
- `CiPanel.jsx` — tab toggle ("Challenge App" | subject repo name), subject repo config card (text input + Connect/Disconnect), subject runs list with metadata and GitHub link
- `backend/ci_bridge.py` — `GET /ci/subject-runs?repo=&limit=` endpoint using `SUBJECT_REPO_TOKEN`
- `frontend/src/modules/frontend-ui/dashboardApi.js` — added `fetchSubjectCiRuns()`

### Known gap
- Human approval gate for subject-repo GO/HOLD decisions (wayside-monitor) not yet wired in the UI — currently shows run metadata only; the actual SubjectRepoPipeline result is in the CI artifacts
