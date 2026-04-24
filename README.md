# challenge-app

Frontend + backend workspace for the release-readiness console.

The repository now embeds the full Python core migrated from `challange_hitachi`:

- `agent4/`
- `agent5/`
- `brain/`
- `synthetic_data/`
- `scripts/`
- `tests/`

`backend/app.py` is now a thin FastAPI orchestration layer over those packages instead of using simplified local stubs.

## Frontend

Run the React app:

```bash
npm install
npm run dev
```

## Backend

Custom sets created from the UI are persisted on disk under `Dataset/Test_Sets/SET_CUSTOM_*` and are reloaded from the backend on startup.

### Install backend dependencies

From the `challenge-app` root:

```bash
pip install -r backend/requirements.txt
```

### Run backend

From the `challenge-app` root:

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8001
```

### Configure OpenRouter for LLM summaries

Create or update the root `.env` file and set:

```env
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=openai/gpt-oss-20b:free
```

The backend auto-loads `.env` on startup. If `OPENROUTER_API_KEY` is missing, the app still runs and falls back to deterministic summaries even when LLM summaries are requested.

### Core HTTP endpoints

- `GET /health`
- `GET /datasets/custom-sets`
- `POST /datasets/custom-sets`
- `DELETE /datasets/custom-sets/{set_id}`
- `GET /agents/options`
- `POST /agents/validate`
- `POST /agents/scenarios`
- `POST /agents/run`
- `GET /brain/options`
- `POST /brain/run`

### Example: Release Readiness Analyst single scenario

```json
{
  "agent": "agent4",
  "dataset_root": "synthetic_data/v1",
  "scenario_id": "S4-001",
  "check_label": true,
  "strict_schema": true,
  "source_adapter_kind": "auto",
  "no_llm": true
}
```

The `agent` field also accepts human-readable aliases such as `Release Readiness Analyst` and `Test Evidence Analyst`; the backend normalizes them to the canonical ids `agent4` and `agent5`.

### Example: Test Evidence Analyst evaluate-all

```json
{
  "agent": "agent5",
  "dataset_root": "synthetic_data/phase5/v2",
  "evaluate_all": true,
  "check_label": true,
  "no_llm": true
}
```

### Example: Brain orchestration

```json
{
  "scenario_id": "S4-001",
  "agent5_scenario_id": "P5V2-001",
  "agent4_dataset_root": "synthetic_data/v1",
  "agent5_dataset_root": "synthetic_data/phase5/v2",
  "allow_agent5_after_agent4_hold": false
}
```

## Notes

- Agent decisions remain deterministic; the backend orchestrates the policy engines and exposes their outputs over HTTP.
- `strict_schema` and `fail_on_label_mismatch` are enforced as HTTP errors when enabled.
- Custom dataset uploads support APCS `.docx` bundles in addition to text and CSV assets.
- The repo is now self-contained for the copied synthetic datasets and Python runners.
