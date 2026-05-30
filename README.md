# Verdict

Release-readiness console for safety-critical railway software — built for Hitachi Rail GBMS. Bridges the gap between CI/CD automation and regulatory compliance gates by using AI agents to prepare the evidence that human reviewers need to approve a release.

## What it does

- **PR Review** — LLM agent analyses every PR diff against GBMS requirements (REQ-WMS-*) and test cases (TC-WMS-*), posts a GO/HOLD report as a GitHub comment
- **Test Evidence** — after each merge to main, synthesises a structured test evidence summary from pytest output and the APCS bundle
- **VDD Drafting** — on release, auto-drafts the Version Description Document following the Hitachi template G-TMP S0203 rev.01 and commits it to `VDDs/VDD-<tag>.md`
- **Approvals** — unified panel for PR approvals and GitHub Actions environment gates (one-click approve/reject)
- **Cluster Health** — live SSE dashboard of ArgoCD app state across mgmt/test/prod, polled every 30 s from the K8s API

## Repository layout

```
verdict/
├── frontend/          React + Vite + Tailwind (UI)
├── backend/           FastAPI orchestration layer
│   ├── app.py         Main entrypoint, all HTTP routes
│   ├── pulls_bridge.py
│   ├── releases_bridge.py
│   ├── commits_bridge.py
│   ├── issues_bridge.py
│   ├── deployments_bridge.py
│   ├── health_bridge.py
│   └── brain_wayside.py
├── agents/
│   ├── agent4/        Release Readiness Analyst (deterministic)
│   ├── agent5/        Test Evidence Analyst (deterministic)
│   ├── brain/         Orchestrator (agent4 → agent5)
│   ├── pr_review/     Standalone LLM PR reviewer
│   ├── vdd_drafter/   Standalone LLM VDD generator
│   ├── rag/           Lightweight RAG primitives (chunker, embeddings, retrieval)
│   ├── _sanitize.py   Shared LLM output guardrails
│   └── subject_pipeline.py  Test evidence agent
├── datasets/          APCS bundles and synthetic CSV scenarios (agent test data)
├── scripts/
│   ├── eval/          CI analysis entrypoints
│   └── seed_health_local.py  Seed Health page from kubectl locally
├── tests/             Pytest suite (agent5, brain)
├── deploy/
│   ├── docker/        Dockerfile, nginx config, run_combined.py
│   ├── helm/          Helm chart (published to GHCR by CI)
│   └── argocd/        notifications-cm.yaml for ArgoCD webhook
└── docs/              Architecture, design decisions, CrownLabs guide
```

## Local development

### Backend

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# copy secrets from the deployed K8s secret (optional)
source .verdict_env

uvicorn backend.app:app --reload --port 8001
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # Vite dev server, proxies /api → http://127.0.0.1:8001
npm test         # Vitest + Testing Library
```

### Seed Cluster Health locally

With the backend running and kubectl configured:

```bash
python3 scripts/seed_health_local.py --context mgmt
```

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes (for LLM features) | LLM completions via OpenRouter |
| `OPENROUTER_MODEL` | No | Model override (default: `openai/gpt-oss-20b:free`) |
| `SUBJECT_REPO_TOKEN` | Yes | GitHub PAT for wayside-monitor (pulls, issues, releases, deployments) |
| `HUGGINGFACE_TOKEN` | No | Embeddings for RAG (pr_review agent) |
| `ARGOCD_TOKEN` | No | ArgoCD API token for local health polling |
| `ARGOCD_SERVER` | No | ArgoCD server address (default: `localhost:8080`) |
| `ARGOCD_POLL_INTERVAL` | No | Seconds between K8s health polls (default: `30`, `0` to disable) |
| `VERDICT_ALLOW_SELF_MERGE` | No | Allow self-approval bypass for demo (default: `true`) |

## Container build

```bash
docker build -f deploy/docker/Dockerfile -t verdict .
docker run --rm -p 8080:80 --env-file .verdict_env verdict
```

## Deployment

Verdict runs on the CrownLabs management VM (K3s + Argo CD). See [docs/crownlabs-infrastructure-guide.md](docs/crownlabs-infrastructure-guide.md) for the full setup.

The Helm chart is auto-published to `oci://ghcr.io/federicomameli1/charts/verdict` by CI whenever `deploy/helm/` changes.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system description and [docs/design-decisions.md](docs/design-decisions.md) for the invariants reviewers must preserve.
