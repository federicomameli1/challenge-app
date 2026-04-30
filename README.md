# challenge-app

Release-readiness console: a React frontend, a FastAPI orchestration layer and the Python core agents that decide whether a release can promote from DEV → TEST → PROD.

## Repository layout

```
challenge-app/
├── frontend/                React + Vite app (UI)
├── backend/                 FastAPI app exposing /agents, /brain, /datasets endpoints
├── agents/                  Python core (deterministic policy engines)
│   ├── agent4/              Release Readiness Analyst (Phase 4)
│   ├── agent5/              Test Evidence Analyst (Phase 5)
│   └── brain/               Orchestration of agent4 → agent5
├── datasets/
│   ├── synthetic/           Generated CSV scenarios used by the agents
│   │   ├── phase4/{v1,v2}/
│   │   └── phase5/{v1,v2}/
│   └── apcs_bundles/        APCS document bundles (Emails, Requirements, VDD, ...)
│       ├── reference/       Original GO / HOLD reference documents
│       ├── baseline/        v1.1.x sets (GO_STABLE, HOLD_*)
│       ├── premium/         v1.2.0 multi-thread bundles
│       ├── adversarial/     v1.3.0 reasoning stress tests
│       ├── colleagues/      External contributor sets (v1.3.10+)
│       └── custom/          Bundles created at runtime via the UI
├── scripts/
│   ├── generate/            Synthetic dataset generators
│   ├── run/                 Single-run / orchestrator entrypoints
│   └── eval/                Evaluation, label-check and CI analysis
├── tests/                   Pytest suite (agent5, brain)
├── deploy/
│   ├── docker/              Dockerfile, nginx config, run_combined.py
│   └── helm/                Helm chart packaged to GHCR by CI
├── docs/                    Living documentation
└── artifacts/               Local run outputs (gitignored)
```

## Frontend

```bash
cd frontend
npm install
npm run dev      # Vite dev server, proxies /api → http://127.0.0.1:8001
npm test         # Vitest + Testing Library
npm run build    # writes frontend/dist/ for the container image
```

## Backend

```bash
pip install -r backend/requirements.txt
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8001
```

The backend auto-loads `.env` at the repo root. Set `OPENROUTER_API_KEY` to enable LLM-refined explanations; without it the deterministic explainer is used.

### Core HTTP endpoints

- `GET /health`
- `GET /agents/options`
- `POST /agents/validate`
- `POST /agents/scenarios`
- `POST /agents/run`
- `GET /brain/options`
- `POST /brain/run`
- `GET /datasets/custom-sets`
- `POST /datasets/custom-sets`
- `DELETE /datasets/custom-sets/{set_id}`

Custom sets uploaded from the UI persist on disk under `datasets/apcs_bundles/custom/` and are reloaded at startup.

## Running agents from the CLI

```bash
# Single Phase 4 scenario
python scripts/run/run_agent4.py --scenario-id S4-001 --pretty

# Phase 5 evaluate-all with label check
python scripts/run/run_agent5.py --evaluate-all --check-label \
  --dataset-root datasets/synthetic/phase5/v2

# Brain orchestrator (agent4 → agent5)
python scripts/run/run_brain_orchestrator.py \
  --scenario-id S4-001 --agent5-scenario-id P5V2-001 --pretty

# Run agent4 over all colleague APCS bundles
python scripts/run/run_colleagues_sets.py
```

The `agents/agent4` LangChain pipeline accepts `--source-adapter-kind apcs_doc_bundle` to read APCS document bundles instead of structured CSVs.

## Container build

The Dockerfile builds the frontend into static assets and runs nginx + uvicorn together inside one image.

```bash
docker build -f deploy/docker/Dockerfile -t challenge-app .
docker run --rm -p 8080:80 --env-file .env challenge-app
```

## Helm chart

```bash
helm package deploy/helm
```

CI publishes the chart to `oci://ghcr.io/<owner>/<repo>` whenever `deploy/helm/` changes.

## Notes

- Agent decisions are deterministic; the LLM layer only refines the natural-language explanation.
- `strict_schema` and `fail_on_label_mismatch` surface as HTTP errors when enabled.
- Custom dataset uploads accept `.txt`, `.csv` and `.docx` APCS assets.
