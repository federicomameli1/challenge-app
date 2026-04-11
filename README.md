# challenge-app

Frontend + backend workspace for the release-readiness console.

## Frontend

Run the React app:

```bash
npm install
npm run dev
```

## Backend (Agent Integration)

The backend is now inside `challenge-app/backend` and exposes Agent 4/5 execution as HTTP APIs.

Custom sets created from the UI are now persisted on disk under `challenge-app/Dataset/Test_Sets/SET_CUSTOM_*` and are reloaded from the backend on startup.

### Install backend dependencies

```bash
pip install -r challenge-app/backend/requirements.txt
```

### Run backend

```bash
uvicorn challenge-app.backend.app:app --reload --host 0.0.0.0 --port 8001
```

### Endpoints

- `GET /health`
- `GET /datasets/custom-sets`
- `POST /datasets/custom-sets`
- `DELETE /datasets/custom-sets/{set_id}`
- `GET /agents/options`
- `POST /agents/run`

### Example: Agent 4 single scenario

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

### Example: Agent 5 evaluate-all

```json
{
	"agent": "agent5",
	"dataset_root": "synthetic_data/phase5/v2",
	"evaluate_all": true,
	"check_label": true,
	"no_llm": true
}
```

## Notes

- Agent decisions remain deterministic; backend only orchestrates existing policy engines.
- `strict_schema` and `fail_on_label_mismatch` are enforced as HTTP errors when enabled.
- New sets created in the UI are stored in `challenge-app/Dataset/Test_Sets`, not in the nested duplicate folder.