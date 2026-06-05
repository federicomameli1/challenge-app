# Agent 7 — Live Monitoring (Frontend Module)

Real-time production deployment & live monitoring dashboard for Agent 7,
integrated as a new "Live Monitoring" item in the Sidebar.

## Files

```
frontend/src/modules/agent7-live-monitoring/
├── LiveMonitoringPage.jsx              # main dashboard
├── index.js                            # re-export
├── hooks/
│   └── useAgent7WebSocket.js           # WebSocket hook
└── README.md                           # this file
```

## How the page is reached

The Sidebar (`frontend/src/modules/frontend-ui/Sidebar.jsx`) gets a new
nav item `live-monitoring`. Clicking it sets `activeView = "live-monitoring"`
in `App.jsx`, which renders `<LiveMonitoringPage />`.

## Run

You need the Agent 7 backend running on port 8001 (separate process).

From the `Challange_agent1` repo:

```bash
PYTHONPATH=. python3.11 -m uvicorn agent7.api.server:app --host 0.0.0.0 --port 8001 --reload
```

Then from this repo:

```bash
cd frontend
npm install   # first time only
npm run dev
```

## Configuration

The API base URL is read from the Vite env var `VITE_AGENT7_API_BASE`.
Default: `http://127.0.0.1:8001`. To override, create `frontend/.env.local`:

```
VITE_AGENT7_API_BASE=http://localhost:8002
```

## Demo flow

1. Click **Live Monitoring** in the Sidebar.
2. Wait ~1 second for the WebSocket to connect (green "Connected" indicator).
3. The first snapshot arrives with all probes `HEALTHY`.
4. Click **Start Deployment** — version shows up in the snapshot stream.
5. Click **Inject** next to `auth-service` — within ~2 seconds, that row turns
   red, the overall metric flips to `UNHEALTHY`, error rate jumps to 25%.
6. Click **Resolve** — back to `HEALTHY`, 0% error.
7. Click **Resolve All Probes** to clear all overrides at once.

## API surface used

| Method | URL                                            | Purpose                          |
|--------|------------------------------------------------|----------------------------------|
| GET    | `/api/agent7/scenarios`                        | List scenarios                   |
| POST   | `/api/agent7/deploy/start`                     | Start monitoring for a scenario  |
| WS     | `/api/agent7/ws/{scenario_id}`                 | Stream snapshots                 |
| POST   | `/api/agent7/demo/inject-problem`              | Set a probe to unhealthy         |
| POST   | `/api/agent7/demo/resolve-problem`             | Clear a probe override           |

CORS is `*` on the Agent 7 backend, so the Vite dev server can call it
from any port.
