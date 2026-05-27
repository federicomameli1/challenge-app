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
