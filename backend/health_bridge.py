"""Cluster Health bridge — ArgoCD notifications consumer + SSE broadcast.

ArgoCD `argocd-notifications-controller` on the mgmt cluster posts to
`POST /webhooks/argocd` whenever an Application's health or sync status
changes. We keep a small in-memory snapshot of every app's latest state
and stream updates to the Verdict UI via Server-Sent Events.

Webhook payload shape (defined by the notifications ConfigMap template):

    {
      "app":            "verdict",
      "cluster":        "in-cluster",      // ArgoCD destination name
      "namespace":      "verdict",
      "sync_status":    "Synced" | "OutOfSync" | "Unknown",
      "health_status":  "Healthy" | "Degraded" | "Suspended" | "Missing" | "Progressing" | "Unknown",
      "operation_phase":"Succeeded" | "Failed" | "Running" | "",
      "revision":       "<sha>",
      "url":            "https://argocd.example/applications/...",
      "timestamp":      "2026-05-28T10:15:00Z"
    }

State is intentionally in-memory: the controller re-fires on the next
status change, so a Verdict restart loses at most one update cycle.
"""

from __future__ import annotations

import asyncio
import http.client as _http_client
import json
import logging
import os
import ssl
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AppHealthSnapshot(BaseModel):
    app: str
    cluster: str = ""
    namespace: str = ""
    sync_status: str = "Unknown"
    health_status: str = "Unknown"
    operation_phase: str = ""
    revision: str = ""
    url: Optional[str] = None
    received_at: str = Field(..., description="When Verdict received the update (UTC ISO8601)")
    event_timestamp: Optional[str] = None


class HealthSnapshotResponse(BaseModel):
    apps: List[AppHealthSnapshot] = Field(default_factory=list)
    received_at: str
    apps_total: int = 0
    apps_healthy: int = 0
    apps_degraded: int = 0
    apps_out_of_sync: int = 0


# ---------------------------------------------------------------------------
# In-memory state + SSE fan-out
# ---------------------------------------------------------------------------


_STATE: Dict[str, AppHealthSnapshot] = {}
_STATE_LOCK = asyncio.Lock()
_SUBSCRIBERS: List[asyncio.Queue] = []
_SUBSCRIBERS_LOCK = asyncio.Lock()
_RECENT_EVENTS: Deque[Dict[str, Any]] = deque(maxlen=64)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_healthy(snap: AppHealthSnapshot) -> bool:
    return snap.health_status == "Healthy" and snap.sync_status == "Synced"


def _is_degraded(snap: AppHealthSnapshot) -> bool:
    return snap.health_status in {"Degraded", "Missing"}


def _is_out_of_sync(snap: AppHealthSnapshot) -> bool:
    return snap.sync_status == "OutOfSync" and snap.health_status != "Degraded"


def _snapshot_payload() -> HealthSnapshotResponse:
    apps = list(_STATE.values())
    apps.sort(key=lambda a: (a.cluster, a.app))
    healthy = sum(1 for a in apps if _is_healthy(a))
    degraded = sum(1 for a in apps if _is_degraded(a))
    oos = sum(1 for a in apps if _is_out_of_sync(a))
    return HealthSnapshotResponse(
        apps=apps,
        received_at=_now_iso(),
        apps_total=len(apps),
        apps_healthy=healthy,
        apps_degraded=degraded,
        apps_out_of_sync=oos,
    )


async def _broadcast(event: Dict[str, Any]) -> None:
    async with _SUBSCRIBERS_LOCK:
        targets = list(_SUBSCRIBERS)
    if not targets:
        return
    for q in targets:
        # Non-blocking: if a subscriber's queue is full, drop the event for it.
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Dropping SSE event for full subscriber queue")


# ---------------------------------------------------------------------------
# Webhook (ArgoCD notifications → Verdict)
# ---------------------------------------------------------------------------


@router.post("/webhooks/argocd")
async def receive_argocd_event(request: Request) -> Dict[str, Any]:
    """Ingest one ArgoCD notification event.

    Tolerates JSON shapes from common notification templates: top-level
    fields or nested under `app`/`data` are both handled. Unknown fields
    are ignored.
    """
    try:
        raw = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object body")

    # Some templates wrap the payload under "data" or "app"; flatten.
    nested = raw.get("data") if isinstance(raw.get("data"), dict) else None
    body = {**raw, **(nested or {})}

    app_name = str(body.get("app") or body.get("application") or "").strip()
    if not app_name:
        raise HTTPException(status_code=400, detail="payload missing 'app' field")

    snapshot = AppHealthSnapshot(
        app=app_name,
        cluster=str(body.get("cluster") or body.get("destination") or ""),
        namespace=str(body.get("namespace") or ""),
        sync_status=str(body.get("sync_status") or body.get("sync") or "Unknown"),
        health_status=str(body.get("health_status") or body.get("health") or "Unknown"),
        operation_phase=str(body.get("operation_phase") or body.get("operation") or ""),
        revision=str(body.get("revision") or ""),
        url=str(body.get("url")) if body.get("url") else None,
        received_at=_now_iso(),
        event_timestamp=body.get("timestamp"),
    )

    async with _STATE_LOCK:
        _STATE[app_name] = snapshot

    event = {
        "type": "app_update",
        "snapshot": snapshot.model_dump(),
    }
    _RECENT_EVENTS.append({**event, "received_at": snapshot.received_at})
    await _broadcast(event)
    return {"ok": True, "app": app_name}


# ---------------------------------------------------------------------------
# Snapshot + SSE stream (Verdict UI consumers)
# ---------------------------------------------------------------------------


@router.get("/health/apps", response_model=HealthSnapshotResponse)
async def get_health_snapshot() -> HealthSnapshotResponse:
    """Current snapshot of every app Verdict has seen."""
    return _snapshot_payload()


@router.get("/health/events/recent")
async def get_recent_events() -> Dict[str, Any]:
    """Last ~64 events received — useful for UI bootstrap or debugging."""
    return {"events": list(_RECENT_EVENTS)}


@router.get("/health/stream")
async def stream_health_events(request: Request) -> StreamingResponse:
    """Server-Sent Events stream. The client receives:
       - one `snapshot` event with the current state when it connects,
       - then one `app_update` event per webhook payload.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    async with _SUBSCRIBERS_LOCK:
        _SUBSCRIBERS.append(queue)
    logger.info("Health SSE subscriber connected (total=%d)", len(_SUBSCRIBERS))

    async def stream():
        try:
            # Bootstrap message: current snapshot.
            bootstrap = {"type": "snapshot", "data": _snapshot_payload().model_dump()}
            yield _sse_format(bootstrap)

            keepalive_interval = 15.0
            last_send = time.monotonic()
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=keepalive_interval)
                    yield _sse_format(event)
                    last_send = time.monotonic()
                except asyncio.TimeoutError:
                    # Send a comment frame so proxies don't close the connection.
                    yield ": keepalive\n\n"
                    last_send = time.monotonic()
        finally:
            async with _SUBSCRIBERS_LOCK:
                if queue in _SUBSCRIBERS:
                    _SUBSCRIBERS.remove(queue)
            logger.info("Health SSE subscriber disconnected (total=%d)", len(_SUBSCRIBERS))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",   # disable nginx buffering for SSE
            "Connection": "keep-alive",
        },
    )


def _sse_format(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


# ---------------------------------------------------------------------------
# Kubernetes-native ArgoCD poller
# ---------------------------------------------------------------------------

_K8S_SA_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
_K8S_API_HOST = "kubernetes.default.svc"
_POLL_TASK: Optional[asyncio.Task] = None


def _k8s_fetch_argocd_apps() -> List[Dict[str, Any]]:
    """Synchronous call to K8s API for all ArgoCD Application resources.

    Uses the pod's mounted service-account token. Returns raw item dicts.
    Returns [] when not running in-cluster or on any error.
    """
    token_file = _K8S_SA_DIR / "token"
    ca_file = _K8S_SA_DIR / "ca.crt"
    if not token_file.exists():
        logger.debug("K8s SA token not found — not running in-cluster")
        return []
    token = token_file.read_text().strip()
    ctx = ssl.create_default_context(cafile=str(ca_file) if ca_file.exists() else None)
    conn = _http_client.HTTPSConnection(_K8S_API_HOST, 443, context=ctx, timeout=10)
    try:
        conn.request(
            "GET",
            "/apis/argoproj.io/v1alpha1/applications",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = conn.getresponse()
        if resp.status == 403:
            logger.warning(
                "K8s RBAC denied read access to ArgoCD applications — "
                "ensure the ClusterRole is applied (deploy/helm/templates/rbac.yaml)"
            )
            return []
        if resp.status != 200:
            logger.warning("K8s API returned %d listing ArgoCD apps", resp.status)
            return []
        return json.loads(resp.read()).get("items", [])
    except Exception as exc:
        logger.warning("K8s ArgoCD app fetch failed: %s", exc)
        return []
    finally:
        conn.close()


def _item_to_snapshot(item: Dict[str, Any]) -> AppHealthSnapshot:
    meta = item.get("metadata") or {}
    spec = item.get("spec") or {}
    status = item.get("status") or {}
    dest = spec.get("destination") or {}
    sync = status.get("sync") or {}
    health = status.get("health") or {}
    op = status.get("operationState") or {}
    return AppHealthSnapshot(
        app=str(meta.get("name") or ""),
        cluster=str(dest.get("name") or ""),
        namespace=str(dest.get("namespace") or ""),
        sync_status=str(sync.get("status") or "Unknown"),
        health_status=str(health.get("status") or "Unknown"),
        operation_phase=str(op.get("phase") or ""),
        revision=str(sync.get("revision") or ""),
        received_at=_now_iso(),
    )


async def _sync_from_k8s() -> int:
    """Fetch apps from K8s API, update state, broadcast to SSE subscribers."""
    items = await asyncio.to_thread(_k8s_fetch_argocd_apps)
    if not items:
        return 0
    snapshots = [_item_to_snapshot(it) for it in items]
    async with _STATE_LOCK:
        for snap in snapshots:
            _STATE[snap.app] = snap
    for snap in snapshots:
        event = {"type": "app_update", "snapshot": snap.model_dump()}
        _RECENT_EVENTS.append({**event, "received_at": snap.received_at})
        await _broadcast(event)
    return len(snapshots)


async def _poll_loop(interval: int) -> None:
    logger.info("ArgoCD health poller started (interval=%ds)", interval)
    while True:
        try:
            count = await _sync_from_k8s()
            if count:
                logger.info("ArgoCD K8s sync: updated %d apps", count)
        except Exception as exc:
            logger.warning("ArgoCD K8s sync error: %s", exc)
        await asyncio.sleep(interval)


def start_argocd_poller() -> None:
    """Launch the background polling task. Call once at app startup."""
    global _POLL_TASK
    interval = int(os.environ.get("ARGOCD_POLL_INTERVAL", "30") or "30")
    if interval <= 0:
        logger.info("ArgoCD poller disabled (ARGOCD_POLL_INTERVAL=0)")
        return
    _POLL_TASK = asyncio.get_event_loop().create_task(_poll_loop(interval))


# ---------------------------------------------------------------------------
# Manual sync endpoint
# ---------------------------------------------------------------------------

@router.post("/health/sync")
async def sync_health() -> Dict[str, Any]:
    """Manually pull current ArgoCD app state from the K8s API."""
    count = await _sync_from_k8s()
    return {"ok": True, "apps_synced": count}
