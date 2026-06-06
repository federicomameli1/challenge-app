"""Agent 7 — Production Deployment Gate with Live Monitoring bridge.

Exposes:
  POST /agent7/deploy          — start a dry-run deployment for a scenario
  GET  /agent7/status/{id}     — poll current monitoring state
  GET  /agent7/stream/{id}     — SSE stream of live monitoring snapshots
  POST /agent7/demo/inject     — inject a synthetic probe failure
  POST /agent7/demo/resolve    — resolve a previously injected failure
  POST /agent7/demo/reset      — reset all demo state

The LiveMonitoringService runs in a background thread per active deployment.
Demo injection works by replacing the SyntheticProbe status in-memory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from threading import Lock
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent7", tags=["agent7"])

# ---------------------------------------------------------------------------
# In-memory state (one deployment per scenario_id for the demo)
# ---------------------------------------------------------------------------

_STATE_LOCK = Lock()
_ACTIVE: Dict[str, Dict[str, Any]] = {}  # scenario_id -> deployment state
_DEMO_OVERRIDES: Dict[str, Dict[str, Any]] = {}  # scenario_id -> {probe_name: {status, error}}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DeployRequest(BaseModel):
    scenario_id: str = Field(..., description="e.g. 'P7-001'")
    release_id: str = Field(default="REL-demo")
    probe_names: list = Field(
        default=["sensor-collector", "anomaly-engine", "alert-dispatcher", "redis-broker"]
    )
    stabilization_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
    interval_seconds: float = Field(default=3.0, ge=1.0, le=30.0)


class InjectRequest(BaseModel):
    scenario_id: str
    probe_name: str
    status: str = Field(default="unhealthy", pattern="^(unhealthy|degraded)$")
    error_message: str = Field(default="simulated production outage")
    response_time_ms: Optional[float] = Field(default=None)


class ResolveRequest(BaseModel):
    scenario_id: str
    probe_name: str


class ResetRequest(BaseModel):
    scenario_id: str


# ---------------------------------------------------------------------------
# Synthetic probe factory
# ---------------------------------------------------------------------------

def _make_probe(name: str, scenario_id: str):
    """Return a probe function that respects demo overrides."""
    from agents.agent7.models import HealthProbeResult, HealthProbeStatus, utc_now_iso

    def probe_fn() -> HealthProbeResult:
        with _STATE_LOCK:
            override = _DEMO_OVERRIDES.get(scenario_id, {}).get(name)

        if override:
            status_val = override.get("status", "unhealthy")
            status = HealthProbeStatus(status_val)
            return HealthProbeResult(
                probe_name=name,
                status=status,
                response_time_ms=override.get("response_time_ms", 900.0),
                error_message=override.get("error_message", "simulated outage"),
            )

        return HealthProbeResult(
            probe_name=name,
            status=HealthProbeStatus.HEALTHY,
            response_time_ms=45.0 + hash(name) % 30,
        )

    return probe_fn


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/deploy")
def start_deployment(req: DeployRequest) -> Dict[str, Any]:
    """Start a dry-run deployment with live monitoring for the given scenario."""
    from agents.agent7.deployment import DeploymentConfig, HealthProbe, LiveMonitoringService
    from agents.agent7.models import DeploymentStatus, utc_now_iso

    sid = req.scenario_id

    # Stop any existing deployment for this scenario
    with _STATE_LOCK:
        existing = _ACTIVE.get(sid)
        if existing and existing.get("monitor"):
            try:
                existing["monitor"].stop()
            except Exception:
                pass
        _DEMO_OVERRIDES.pop(sid, None)

    probes = tuple(
        HealthProbe(name=name, check_fn=_make_probe(name, sid))
        for name in req.probe_names
    )

    monitor = LiveMonitoringService(
        probes=probes,
        interval_seconds=req.interval_seconds,
        stabilization_seconds=req.stabilization_seconds,
    )
    monitor.start(version=req.release_id)

    with _STATE_LOCK:
        _ACTIVE[sid] = {
            "monitor": monitor,
            "release_id": req.release_id,
            "probe_names": req.probe_names,
            "started_at": utc_now_iso(),
        }

    logger.info("Agent 7 deployment started for %s", sid)
    return {
        "scenario_id": sid,
        "release_id": req.release_id,
        "deployment_status": DeploymentStatus.STABILIZING.value,
        "message": "Deployment started. Stream /agent7/stream/{scenario_id} for live updates.",
    }


@router.get("/status/{scenario_id}")
def get_status(scenario_id: str) -> Dict[str, Any]:
    """Return the current monitoring state for a deployment."""
    with _STATE_LOCK:
        entry = _ACTIVE.get(scenario_id)

    if not entry:
        raise HTTPException(status_code=404, detail=f"No active deployment for {scenario_id}")

    state = entry["monitor"].get_current_state()
    return {
        "scenario_id": scenario_id,
        "release_id": entry["release_id"],
        "started_at": entry["started_at"],
        **state.to_dict(),
    }


@router.get("/stream/{scenario_id}")
async def stream_monitoring(scenario_id: str, request: Request) -> StreamingResponse:
    """SSE stream of live monitoring snapshots."""

    async def event_stream():
        # Bootstrap: send current state immediately
        with _STATE_LOCK:
            entry = _ACTIVE.get(scenario_id)
        if not entry:
            yield f"data: {json.dumps({'error': 'No active deployment'})}\n\n"
            return

        last_snapshot_count = 0

        while True:
            if await request.is_disconnected():
                break

            with _STATE_LOCK:
                entry = _ACTIVE.get(scenario_id)
            if not entry:
                break

            state = entry["monitor"].get_current_state()
            state_dict = state.to_dict()
            snapshots = state_dict.get("snapshots", [])
            current_count = len(snapshots)

            if current_count > last_snapshot_count:
                latest = snapshots[-1] if snapshots else {}
                payload = {
                    "type": "snapshot",
                    "scenario_id": scenario_id,
                    "deployment_status": state_dict.get("deployment_status"),
                    "overall_status": latest.get("overall_status"),
                    "stability_achieved": state_dict.get("stability_achieved"),
                    "probe_results": latest.get("probe_results", []),
                    "timestamp_utc": latest.get("timestamp_utc"),
                    "snapshot_count": current_count,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                last_snapshot_count = current_count
            else:
                yield ": keepalive\n\n"

            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/demo/inject")
def inject_problem(req: InjectRequest) -> Dict[str, Any]:
    """Inject a synthetic probe failure into the live monitoring demo."""
    with _STATE_LOCK:
        if req.scenario_id not in _ACTIVE:
            raise HTTPException(
                status_code=404,
                detail=f"No active deployment for {req.scenario_id}. Start one first.",
            )
        _DEMO_OVERRIDES.setdefault(req.scenario_id, {})[req.probe_name] = {
            "status": req.status,
            "error_message": req.error_message,
            "response_time_ms": req.response_time_ms or (900.0 if req.status == "unhealthy" else 400.0),
        }

    logger.info("Demo inject: %s → %s=%s", req.scenario_id, req.probe_name, req.status)
    return {
        "ok": True,
        "scenario_id": req.scenario_id,
        "probe_name": req.probe_name,
        "injected_status": req.status,
    }


@router.post("/demo/resolve")
def resolve_problem(req: ResolveRequest) -> Dict[str, Any]:
    """Resolve a previously injected probe failure."""
    with _STATE_LOCK:
        overrides = _DEMO_OVERRIDES.get(req.scenario_id, {})
        overrides.pop(req.probe_name, None)

    logger.info("Demo resolve: %s → %s restored", req.scenario_id, req.probe_name)
    return {"ok": True, "scenario_id": req.scenario_id, "probe_name": req.probe_name}


@router.post("/demo/reset")
def reset_demo(req: ResetRequest) -> Dict[str, Any]:
    """Stop deployment and clear all demo state for a scenario."""
    with _STATE_LOCK:
        entry = _ACTIVE.pop(req.scenario_id, None)
        _DEMO_OVERRIDES.pop(req.scenario_id, None)

    if entry and entry.get("monitor"):
        try:
            entry["monitor"].stop()
        except Exception:
            pass

    return {"ok": True, "scenario_id": req.scenario_id}
