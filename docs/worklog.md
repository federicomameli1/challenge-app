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
