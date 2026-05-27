"""GitHub Actions deployment-approval bridge for the subject repo.

The existing ci_bridge.py also exposes `/ci/runs/{id}/pending-deployments`
+ `/ci/approve`, but those use the default `CI_BRIDGE_REPO` /
`CI_BRIDGE_TOKEN` env vars (single-repo configuration). This bridge is
parameterised by `repo` and authenticates with `SUBJECT_REPO_TOKEN`,
matching the auth surface used by /pulls, /issues, /commits, /releases.

`GET /deployments?repo=...` aggregates pending deployments across all
workflow runs currently in the `waiting` state so the UI can list every
'thing waiting for my approval' in one place.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .ci_bridge import CiBridgeConfig, _http_get  # noqa: F401
from .pulls_bridge import _http_request

GITHUB_API = "https://api.github.com"

router = APIRouter(prefix="/deployments", tags=["deployments"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PendingDeployment(BaseModel):
    """One waiting environment on one workflow run."""

    run_id: int
    run_number: int = 0
    run_url: str = ""
    workflow_name: str = ""
    head_sha: str = ""
    head_branch: str = ""
    head_commit_message: str = ""
    event: str = ""
    created_at: str = ""
    updated_at: str = ""
    environment_id: int = 0
    environment_name: str = ""
    current_user_can_approve: bool = False
    wait_timer: int = 0
    wait_timer_started_at: Optional[str] = None


class PendingDeploymentsResponse(BaseModel):
    repo: str
    items: List[PendingDeployment] = Field(default_factory=list)


class ApproveDeploymentRequest(BaseModel):
    repo: str
    run_id: int
    environment_ids: List[int]
    comment: Optional[str] = None


class RejectDeploymentRequest(BaseModel):
    repo: str
    run_id: int
    environment_ids: List[int]
    comment: str = Field(..., min_length=1, description="Reason for rejection")


class ActionResult(BaseModel):
    ok: bool
    run_id: int
    state: str
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_pending_for_run(cfg: CiBridgeConfig, run: Dict[str, Any]) -> List[PendingDeployment]:
    run_id = run.get("id")
    if not isinstance(run_id, int):
        return []
    url = f"{GITHUB_API}/repos/{cfg.repo}/actions/runs/{run_id}/pending_deployments"
    status, body, _ = _http_get(url, cfg.headers())
    if status != 200:
        return []
    try:
        pending = json.loads(body or b"[]")
    except json.JSONDecodeError:
        return []

    out: List[PendingDeployment] = []
    head_commit = run.get("head_commit") or {}
    for entry in pending:
        env = entry.get("environment") or {}
        out.append(
            PendingDeployment(
                run_id=run_id,
                run_number=int(run.get("run_number") or 0),
                run_url=run.get("html_url", ""),
                workflow_name=run.get("name") or run.get("display_title") or "",
                head_sha=run.get("head_sha", ""),
                head_branch=run.get("head_branch", ""),
                head_commit_message=(head_commit.get("message") or "").splitlines()[0]
                if head_commit
                else "",
                event=run.get("event", ""),
                created_at=run.get("created_at", ""),
                updated_at=run.get("updated_at", ""),
                environment_id=int(env.get("id") or 0),
                environment_name=env.get("name") or "",
                current_user_can_approve=bool(entry.get("current_user_can_approve", False)),
                wait_timer=int(entry.get("wait_timer") or 0),
                wait_timer_started_at=entry.get("wait_timer_started_at"),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PendingDeploymentsResponse)
def list_pending_deployments(repo: str, limit: int = 30) -> PendingDeploymentsResponse:
    """Aggregate every pending deployment on the subject repo into a flat list."""
    if not repo:
        raise HTTPException(status_code=400, detail="repo query parameter is required")

    cfg = CiBridgeConfig.for_subject_repo(repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )

    per_page = min(max(limit, 1), 100)
    # GitHub's `status=waiting` filter narrows to runs paused on an
    # environment gate — exactly what we care about here.
    url = (
        f"{GITHUB_API}/repos/{repo}/actions/runs"
        f"?status=waiting&per_page={per_page}"
    )
    status, body, _ = _http_get(url, cfg.headers())
    if status != 200:
        raise HTTPException(
            status_code=status,
            detail=f"GitHub returned {status} listing runs: {body[:200]!r}",
        )
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Invalid GitHub JSON: {exc}"
        ) from exc

    runs = payload.get("workflow_runs") or []
    items: List[PendingDeployment] = []
    for run in runs:
        items.extend(_fetch_pending_for_run(cfg, run))

    return PendingDeploymentsResponse(repo=repo, items=items)


def _submit_review(
    cfg: CiBridgeConfig,
    run_id: int,
    environment_ids: List[int],
    state: str,
    comment: Optional[str],
) -> Dict[str, Any]:
    if state not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="state must be 'approved' or 'rejected'")
    if not environment_ids:
        raise HTTPException(status_code=400, detail="environment_ids cannot be empty")

    url = f"{GITHUB_API}/repos/{cfg.repo}/actions/runs/{run_id}/pending_deployments"
    payload = {
        "environment_ids": environment_ids,
        "state": state,
        "comment": comment or "",
    }
    status, raw = _http_request("POST", url, cfg.headers(), payload=payload)
    if status not in (200, 201):
        body_text = (raw[:300] or b"").decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=status,
            detail=f"GitHub returned {status} reviewing deployment: {body_text}",
        )
    try:
        return json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {}


@router.post("/approve", response_model=ActionResult)
def approve_deployment(req: ApproveDeploymentRequest) -> ActionResult:
    cfg = CiBridgeConfig.for_subject_repo(req.repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )
    _submit_review(cfg, req.run_id, req.environment_ids, "approved", req.comment)
    return ActionResult(ok=True, run_id=req.run_id, state="approved")


@router.post("/reject", response_model=ActionResult)
def reject_deployment(req: RejectDeploymentRequest) -> ActionResult:
    cfg = CiBridgeConfig.for_subject_repo(req.repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )
    _submit_review(cfg, req.run_id, req.environment_ids, "rejected", req.comment)
    return ActionResult(ok=True, run_id=req.run_id, state="rejected")
