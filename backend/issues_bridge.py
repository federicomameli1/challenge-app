"""GitHub Issues bridge for the subject repo.

The Tickets page in Verdict UI is a thin mirror of GitHub Issues on
`wayside-monitor`. Reads + create + close/label, no inbound webhooks.

GitHub returns PRs and Issues from the same `/issues` endpoint; we
filter out the entries that carry a `pull_request` field so the Tickets
page only shows genuine issues.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .ci_bridge import CiBridgeConfig, _http_get  # noqa: F401
from .pulls_bridge import _http_request  # reuse the generic verb helper

GITHUB_API = "https://api.github.com"

router = APIRouter(prefix="/issues", tags=["issues"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class IssueLabel(BaseModel):
    name: str
    color: Optional[str] = None  # hex string without '#', from GitHub
    description: Optional[str] = None


class IssueSummary(BaseModel):
    number: int
    title: str
    author: str
    state: str  # "open" | "closed"
    state_reason: Optional[str] = None  # "completed" | "not_planned" | "reopened"
    body: str = ""
    html_url: str = ""
    created_at: str = ""
    updated_at: str = ""
    closed_at: Optional[str] = None
    labels: List[IssueLabel] = Field(default_factory=list)
    assignees: List[str] = Field(default_factory=list)
    comments: int = 0


class IssuesResponse(BaseModel):
    repo: str
    items: List[IssueSummary] = Field(default_factory=list)


class CreateIssueRequest(BaseModel):
    repo: str
    title: str = Field(..., min_length=1, max_length=256)
    body: Optional[str] = Field(default=None, max_length=64_000)
    labels: List[str] = Field(default_factory=list)
    assignees: List[str] = Field(default_factory=list)


class UpdateIssueRequest(BaseModel):
    repo: str
    state: Optional[str] = Field(
        default=None, description="open / closed"
    )
    state_reason: Optional[str] = Field(
        default=None,
        description="completed / not_planned / reopened (only valid when closing/reopening)",
    )
    labels: Optional[List[str]] = Field(
        default=None,
        description="If provided, REPLACES the issue's label set",
    )
    title: Optional[str] = None
    body: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _label_from_raw(raw: Any) -> IssueLabel:
    if isinstance(raw, dict):
        return IssueLabel(
            name=str(raw.get("name") or "").strip() or "label",
            color=raw.get("color"),
            description=raw.get("description"),
        )
    return IssueLabel(name=str(raw))


def _issue_from_raw(raw: Dict[str, Any]) -> IssueSummary:
    user = raw.get("user") or {}
    assignees = raw.get("assignees") or []
    labels = raw.get("labels") or []
    return IssueSummary(
        number=raw.get("number") or 0,
        title=raw.get("title") or "",
        author=user.get("login", ""),
        state=raw.get("state", "open"),
        state_reason=raw.get("state_reason"),
        body=raw.get("body") or "",
        html_url=raw.get("html_url", ""),
        created_at=raw.get("created_at", ""),
        updated_at=raw.get("updated_at", ""),
        closed_at=raw.get("closed_at"),
        labels=[_label_from_raw(item) for item in labels],
        assignees=[(a or {}).get("login", "") for a in assignees if a],
        comments=int(raw.get("comments") or 0),
    )


def _is_pull_request(raw: Dict[str, Any]) -> bool:
    return bool(raw.get("pull_request"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=IssuesResponse)
def list_issues(repo: str, state: str = "open", limit: int = 50) -> IssuesResponse:
    """List issues on `repo`, filtering out pull requests."""
    if not repo:
        raise HTTPException(status_code=400, detail="repo query parameter is required")

    cfg = CiBridgeConfig.for_subject_repo(repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )

    per_page = min(max(limit, 1), 100)
    url = (
        f"{GITHUB_API}/repos/{repo}/issues"
        f"?state={state}&per_page={per_page}&sort=updated&direction=desc"
    )
    status, body, _ = _http_get(url, cfg.headers())
    if status != 200:
        raise HTTPException(
            status_code=status,
            detail=f"GitHub returned {status} listing issues: {body[:200]!r}",
        )
    try:
        raw_items = json.loads(body or b"[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Invalid GitHub JSON: {exc}"
        ) from exc

    items = [_issue_from_raw(raw) for raw in raw_items if not _is_pull_request(raw)]
    return IssuesResponse(repo=repo, items=items)


@router.post("", response_model=IssueSummary, status_code=201)
def create_issue(req: CreateIssueRequest) -> IssueSummary:
    cfg = CiBridgeConfig.for_subject_repo(req.repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )

    payload: Dict[str, Any] = {"title": req.title}
    if req.body:
        payload["body"] = req.body
    if req.labels:
        payload["labels"] = req.labels
    if req.assignees:
        payload["assignees"] = req.assignees

    url = f"{GITHUB_API}/repos/{req.repo}/issues"
    status, raw = _http_request("POST", url, cfg.headers(), payload=payload)
    if status not in (200, 201):
        body_text = (raw[:300] or b"").decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=status,
            detail=f"GitHub returned {status} creating issue: {body_text}",
        )
    try:
        return _issue_from_raw(json.loads(raw or b"{}"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Invalid GitHub JSON: {exc}"
        ) from exc


@router.patch("/{number}", response_model=IssueSummary)
def update_issue(number: int, req: UpdateIssueRequest) -> IssueSummary:
    cfg = CiBridgeConfig.for_subject_repo(req.repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )

    payload: Dict[str, Any] = {}
    if req.state is not None:
        if req.state not in {"open", "closed"}:
            raise HTTPException(status_code=400, detail="state must be 'open' or 'closed'")
        payload["state"] = req.state
    if req.state_reason is not None:
        payload["state_reason"] = req.state_reason
    if req.labels is not None:
        payload["labels"] = req.labels
    if req.title is not None:
        payload["title"] = req.title
    if req.body is not None:
        payload["body"] = req.body
    if not payload:
        raise HTTPException(
            status_code=400,
            detail="No update fields provided (state / state_reason / labels / title / body)",
        )

    url = f"{GITHUB_API}/repos/{req.repo}/issues/{number}"
    status, raw = _http_request("PATCH", url, cfg.headers(), payload=payload)
    if status not in (200, 201):
        body_text = (raw[:300] or b"").decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=status,
            detail=f"GitHub returned {status} updating issue: {body_text}",
        )
    try:
        return _issue_from_raw(json.loads(raw or b"{}"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Invalid GitHub JSON: {exc}"
        ) from exc
