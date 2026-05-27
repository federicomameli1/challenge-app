"""GitHub Pull Requests bridge.

Read-only listing for the Verdict UI:
- `GET /pulls?repo=...&state=open` — open PRs on a subject repo, with the
  most recent Verdict LLM Review comment parsed out for display.

Write endpoints (review/approve/reject + merge) live in the same module
and use the same auth (SUBJECT_REPO_TOKEN) as the existing CI bridge.

Authentication is reused from `ci_bridge.CiBridgeConfig.for_subject_repo`
so the same SUBJECT_REPO_TOKEN powers both CI run actions and PR actions.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .ci_bridge import CiBridgeConfig, _http_get  # noqa: F401


def _http_request(
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
) -> Tuple[int, bytes]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req_headers = dict(headers)
    if body is not None:
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, (exc.read() if hasattr(exc, "read") else b"")
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=502, detail=f"GitHub request failed: {exc.reason}"
        ) from exc

GITHUB_API = "https://api.github.com"

router = APIRouter(prefix="/pulls", tags=["pulls"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PullReviewSnapshot(BaseModel):
    """Parsed view of the most recent `[Verdict] LLM Review` comment on a PR."""

    comment_id: int
    posted_at: str
    verdict: Optional[str] = None  # "GO" | "HOLD" | None when not parseable
    summary: Optional[str] = None
    body_markdown: str
    html_url: Optional[str] = None


class PullSummary(BaseModel):
    number: int
    title: str
    author: str
    branch: str
    base: str
    head_sha: str
    html_url: str
    state: str
    draft: bool = False
    mergeable: Optional[bool] = None
    created_at: str
    updated_at: str
    last_review: Optional[PullReviewSnapshot] = None


class PullsResponse(BaseModel):
    repo: str
    items: List[PullSummary] = Field(default_factory=list)


class ApproveRequest(BaseModel):
    repo: str
    body: Optional[str] = Field(
        default=None,
        description="Optional review body. Defaults to a generic 'Approved via Verdict' message.",
    )
    merge: bool = Field(default=True, description="Merge the PR after the review is submitted")
    merge_method: str = Field(default="squash", description="One of: merge | squash | rebase")


class RejectRequest(BaseModel):
    repo: str
    body: str = Field(..., description="Reason for rejection — required by GitHub for REQUEST_CHANGES")


class ActionResult(BaseModel):
    ok: bool
    pr_number: int
    review_id: Optional[int] = None
    review_state: Optional[str] = None
    merged: bool = False
    merge_sha: Optional[str] = None
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_VERDICT_HEADER_RE = re.compile(r"^\s*##\s*\[Verdict\]", re.IGNORECASE)
_VERDICT_LINE_RE = re.compile(r"\*\*Verdict:\*\*\s*[^\n]*?\b(GO|HOLD)\b", re.IGNORECASE)
_SUMMARY_LINE_RE = re.compile(
    r"\*\*Summary:\*\*\s*(.+?)(?:\n\n|\n###|\Z)", re.DOTALL
)


def _is_verdict_comment(body: str) -> bool:
    return bool(body) and bool(_VERDICT_HEADER_RE.search(body))


def _parse_verdict(body: str) -> Tuple[Optional[str], Optional[str]]:
    verdict: Optional[str] = None
    summary: Optional[str] = None
    m = _VERDICT_LINE_RE.search(body)
    if m:
        verdict = m.group(1).upper()
    s = _SUMMARY_LINE_RE.search(body)
    if s:
        summary = s.group(1).strip()
    return verdict, summary


def _fetch_last_verdict_comment(
    cfg: CiBridgeConfig, pr_number: int
) -> Optional[PullReviewSnapshot]:
    url = (
        f"{GITHUB_API}/repos/{cfg.repo}/issues/{pr_number}/comments"
        "?per_page=100&sort=created&direction=desc"
    )
    status, body, _ = _http_get(url, cfg.headers())
    if status != 200:
        return None
    try:
        comments = json.loads(body or b"[]")
    except json.JSONDecodeError:
        return None
    for comment in comments:  # already newest-first
        text = comment.get("body") or ""
        if not _is_verdict_comment(text):
            continue
        verdict, summary = _parse_verdict(text)
        return PullReviewSnapshot(
            comment_id=comment.get("id"),
            posted_at=comment.get("created_at"),
            verdict=verdict,
            summary=summary,
            body_markdown=text,
            html_url=comment.get("html_url"),
        )
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PullsResponse)
def list_pulls(repo: str, state: str = "open", limit: int = 50) -> PullsResponse:
    """List PRs on `repo` with the latest Verdict comment, if any.

    `state` is forwarded to the GitHub API (open / closed / all).
    """
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
        f"{GITHUB_API}/repos/{repo}/pulls"
        f"?state={state}&per_page={per_page}&sort=updated&direction=desc"
    )
    status, body, _ = _http_get(url, cfg.headers())
    if status != 200:
        raise HTTPException(
            status_code=status,
            detail=f"GitHub returned {status} listing pulls: {body[:200]!r}",
        )

    try:
        raw_pulls = json.loads(body or b"[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Invalid GitHub JSON: {exc}"
        ) from exc

    items: List[PullSummary] = []
    for raw in raw_pulls:
        number = raw.get("number")
        if number is None:
            continue
        last_review = _fetch_last_verdict_comment(cfg, number)
        items.append(
            PullSummary(
                number=number,
                title=raw.get("title", ""),
                author=(raw.get("user") or {}).get("login", ""),
                branch=(raw.get("head") or {}).get("ref", ""),
                base=(raw.get("base") or {}).get("ref", ""),
                head_sha=(raw.get("head") or {}).get("sha", ""),
                html_url=raw.get("html_url", ""),
                state=raw.get("state", "open"),
                draft=bool(raw.get("draft", False)),
                mergeable=raw.get("mergeable"),
                created_at=raw.get("created_at", ""),
                updated_at=raw.get("updated_at", ""),
                last_review=last_review,
            )
        )

    return PullsResponse(repo=repo, items=items)


class _SelfReviewSkipped(Exception):
    """Raised when GitHub refuses a self-approval and the caller should
    proceed without a review (e.g. for the same-author merge flow)."""


def _submit_review(
    cfg: CiBridgeConfig,
    pr_number: int,
    event: str,
    body: str,
) -> Dict[str, Any]:
    """POST a pull-request review. `event` is APPROVE or REQUEST_CHANGES."""
    url = f"{GITHUB_API}/repos/{cfg.repo}/pulls/{pr_number}/reviews"
    status, raw = _http_request(
        "POST",
        url,
        cfg.headers(),
        payload={"event": event, "body": body},
    )
    if status not in (200, 201):
        body_text = (raw[:500] or b"").decode("utf-8", errors="replace")
        # GitHub explicitly forbids users from approving their own PRs.
        # For the dev/demo flow we surface a sentinel so the caller can
        # continue to the merge step instead of bailing out.
        if (
            status == 422
            and event == "APPROVE"
            and "approve your own pull request" in body_text.lower()
        ):
            raise _SelfReviewSkipped(body_text)
        raise HTTPException(
            status_code=status,
            detail=f"GitHub returned {status} submitting review: {body_text}",
        )
    try:
        return json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {}


def _merge_pr(
    cfg: CiBridgeConfig,
    pr_number: int,
    merge_method: str,
) -> Dict[str, Any]:
    if merge_method not in {"merge", "squash", "rebase"}:
        raise HTTPException(
            status_code=400,
            detail=f"merge_method must be merge|squash|rebase, got {merge_method!r}",
        )
    url = f"{GITHUB_API}/repos/{cfg.repo}/pulls/{pr_number}/merge"
    status, raw = _http_request(
        "PUT",
        url,
        cfg.headers(),
        payload={"merge_method": merge_method},
    )
    if status not in (200, 201):
        raise HTTPException(
            status_code=status,
            detail=(
                f"GitHub returned {status} merging PR: "
                f"{(raw[:300] or b'').decode('utf-8', errors='replace')}"
            ),
        )
    try:
        return json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {}


@router.post("/{pr_number}/approve", response_model=ActionResult)
def approve_pull(pr_number: int, req: ApproveRequest) -> ActionResult:
    """Submit an APPROVE review and (optionally) merge the PR.

    If GitHub refuses the review because the caller is the PR author
    (self-approval is not allowed), we still proceed with the merge step
    so the dev/demo flow remains usable. The response signals this via
    review_state == "SELF_REVIEW_SKIPPED".
    """
    cfg = CiBridgeConfig.for_subject_repo(req.repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )

    review: Dict[str, Any] = {}
    review_state = "APPROVED"
    review_skipped_reason: Optional[str] = None
    try:
        review = _submit_review(
            cfg,
            pr_number,
            event="APPROVE",
            body=req.body or "Approved via Verdict.",
        )
    except _SelfReviewSkipped as skip:
        review_state = "SELF_REVIEW_SKIPPED"
        review_skipped_reason = (
            "GitHub does not allow approving your own pull request — "
            "proceeding directly to merge."
        )

    merged = False
    merge_sha: Optional[str] = None
    message: Optional[str] = review_skipped_reason
    if req.merge:
        try:
            merge_resp = _merge_pr(cfg, pr_number, req.merge_method)
            merged = bool(merge_resp.get("merged"))
            merge_sha = merge_resp.get("sha")
            merge_message = merge_resp.get("message")
            message = (
                f"{review_skipped_reason} {merge_message}".strip()
                if review_skipped_reason and merge_message
                else (merge_message or review_skipped_reason)
            )
        except HTTPException as exc:
            return ActionResult(
                ok=False,
                pr_number=pr_number,
                review_id=review.get("id"),
                review_state=review_state,
                merged=False,
                message=(
                    f"{review_skipped_reason} Merge failed: {exc.detail}"
                    if review_skipped_reason
                    else f"Review submitted but merge failed: {exc.detail}"
                ),
            )

    return ActionResult(
        ok=True,
        pr_number=pr_number,
        review_id=review.get("id"),
        review_state=review_state,
        merged=merged,
        merge_sha=merge_sha,
        message=message,
    )


@router.post("/{pr_number}/reject", response_model=ActionResult)
def reject_pull(pr_number: int, req: RejectRequest) -> ActionResult:
    """Submit a REQUEST_CHANGES review with a required body."""
    cfg = CiBridgeConfig.for_subject_repo(req.repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )
    if not (req.body and req.body.strip()):
        raise HTTPException(status_code=400, detail="body is required for rejection")

    review = _submit_review(cfg, pr_number, event="REQUEST_CHANGES", body=req.body)

    return ActionResult(
        ok=True,
        pr_number=pr_number,
        review_id=review.get("id"),
        review_state="CHANGES_REQUESTED",
    )
