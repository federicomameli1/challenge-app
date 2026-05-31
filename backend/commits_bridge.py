"""Read-only bridge for recent commits on the subject repo's main branch.

Mirrors `pulls_bridge.py` but for commits instead of PRs: lists the last N
commits on the configured base branch and parses out the most recent
`[Verdict] Test Evidence` commit comment so the Releases / Builds UI can
render a verdict badge per commit without exposing the Verdict pod.

The compute itself runs on the wayside-monitor GH Actions runner
(`deploy-test.yml` → `run_test_evidence.py`), which posts the markdown as
a commit comment via the GitHub API. This bridge only reads.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .ci_bridge import CiBridgeConfig, _http_get

GITHUB_API = "https://api.github.com"

router = APIRouter(prefix="/commits", tags=["commits"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestEvidenceSnapshot(BaseModel):
    comment_id: int
    posted_at: str
    verdict: Optional[str] = None  # "GO" | "HOLD" | None
    summary: Optional[str] = None
    body_markdown: str
    html_url: Optional[str] = None


class CommitSummary(BaseModel):
    sha: str
    short_sha: str
    message: str
    author: str
    committed_at: str
    html_url: str
    test_evidence: Optional[TestEvidenceSnapshot] = None


class CommitsResponse(BaseModel):
    repo: str
    branch: str
    items: List[CommitSummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_HEADER_RE = re.compile(r"^\s*##\s*\[Verdict\]\s*Test Evidence", re.IGNORECASE)
_VERDICT_LINE_RE = re.compile(r"\*\*Verdict:\*\*\s*[^\n]*?\b(GO|HOLD)\b", re.IGNORECASE)
_SUMMARY_LINE_RE = re.compile(
    r"\*\*Summary:\*\*\s*(.+?)(?:\n\n|\n###|\Z)", re.DOTALL
)


def _is_test_evidence_comment(body: str) -> bool:
    return bool(body) and bool(_HEADER_RE.search(body))


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


def _fetch_test_evidence_comment(
    cfg: CiBridgeConfig, sha: str
) -> Optional[TestEvidenceSnapshot]:
    url = (
        f"{GITHUB_API}/repos/{cfg.repo}/commits/{sha}/comments"
        "?per_page=100"
    )
    status, body, _ = _http_get(url, cfg.headers())
    if status != 200:
        return None
    try:
        comments = json.loads(body or b"[]")
    except json.JSONDecodeError:
        return None
    # Newest first
    comments.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    for comment in comments:
        text = comment.get("body") or ""
        if not _is_test_evidence_comment(text):
            continue
        verdict, summary = _parse_verdict(text)
        return TestEvidenceSnapshot(
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


@router.get("", response_model=CommitsResponse)
def list_commits(
    repo: str,
    branch: str = "main",
    limit: int = 20,
) -> CommitsResponse:
    """List recent commits on `branch` with the latest Test Evidence comment, if any."""
    if not repo:
        raise HTTPException(status_code=400, detail="repo query parameter is required")

    cfg = CiBridgeConfig.for_subject_repo(repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )

    per_page = min(max(limit, 1), 50)
    url = (
        f"{GITHUB_API}/repos/{repo}/commits"
        f"?sha={branch}&per_page={per_page}"
    )
    status, body, _ = _http_get(url, cfg.headers())
    if status != 200:
        raise HTTPException(
            status_code=status,
            detail=f"GitHub returned {status} listing commits: {body[:200]!r}",
        )

    try:
        raw_commits = json.loads(body or b"[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Invalid GitHub JSON: {exc}"
        ) from exc

    items: List[CommitSummary] = []
    for raw in raw_commits:
        sha = raw.get("sha") or ""
        if not sha:
            continue
        commit = raw.get("commit") or {}
        author = (commit.get("author") or {}).get("name", "") or (
            (raw.get("author") or {}).get("login", "")
        )
        message = (commit.get("message") or "").splitlines()[0]
        committed_at = (commit.get("author") or {}).get("date", "")

        evidence = _fetch_test_evidence_comment(cfg, sha)

        items.append(
            CommitSummary(
                sha=sha,
                short_sha=sha[:8],
                message=message,
                author=author,
                committed_at=committed_at,
                html_url=raw.get("html_url", ""),
                test_evidence=evidence,
            )
        )

    return CommitsResponse(repo=repo, branch=branch, items=items)
