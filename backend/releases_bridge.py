"""Read-only bridge for published GitHub releases on the subject repo.

Lists tag-based releases (`/repos/{owner}/{repo}/releases`) and points at
the auto-drafted VDD file the deploy-prod workflow commits to
`VDDs/VDD-<tag>.md`. Verdict UI shows these in the Releases page.
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .ci_bridge import CiBridgeConfig, _http_get  # noqa: F401

GITHUB_API = "https://api.github.com"

router = APIRouter(prefix="/releases", tags=["releases"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ReleaseSummary(BaseModel):
    tag: str
    name: str = ""
    body: str = ""
    html_url: str = ""
    published_at: Optional[str] = None
    author: str = ""
    draft: bool = False
    prerelease: bool = False
    vdd_path: Optional[str] = Field(
        default=None,
        description="Path within the repo to the auto-drafted VDD file (e.g. 'VDDs/VDD-v0.1.0.md')",
    )
    vdd_url: Optional[str] = Field(
        default=None,
        description="GitHub URL to the rendered VDD file on the main branch",
    )


class ReleasesResponse(BaseModel):
    repo: str
    items: List[ReleaseSummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vdd_url(repo: str, tag: str) -> str:
    return f"https://github.com/{repo}/blob/main/VDDs/VDD-{tag}.md"


def _vdd_exists(cfg: CiBridgeConfig, tag: str) -> bool:
    """Probe the GitHub Contents API to confirm the VDD file is committed.

    Returns false on any non-200 response, so the UI can fall back to
    "VDD pending" until the auto-draft commit lands.
    """
    url = f"{GITHUB_API}/repos/{cfg.repo}/contents/VDDs/VDD-{tag}.md?ref=main"
    status, _, _ = _http_get(url, cfg.headers())
    return status == 200


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/vdd-content")
def get_vdd_content(repo: str, tag: str) -> dict:
    """Return the raw markdown of a VDD file for client-side PDF rendering."""
    if not repo or not tag:
        raise HTTPException(status_code=400, detail="repo and tag are required")
    cfg = CiBridgeConfig.for_subject_repo(repo)
    if not cfg.token:
        raise HTTPException(status_code=503, detail="SUBJECT_REPO_TOKEN not configured")

    import base64
    url = f"{GITHUB_API}/repos/{repo}/contents/VDDs/VDD-{tag}.md?ref=main"
    status, body, _ = _http_get(url, cfg.headers())
    if status == 404:
        raise HTTPException(status_code=404, detail=f"VDD not found for tag {tag}")
    if status != 200:
        raise HTTPException(status_code=502, detail=f"GitHub returned {status}")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid JSON: {exc}") from exc
    content = payload.get("content", "")
    if payload.get("encoding") == "base64":
        content = base64.b64decode(content).decode("utf-8", errors="replace")
    return {"tag": tag, "content": content}


@router.get("", response_model=ReleasesResponse)
def list_releases(repo: str, limit: int = 20) -> ReleasesResponse:
    """List published GitHub releases with a pointer to the auto-drafted VDD."""
    if not repo:
        raise HTTPException(status_code=400, detail="repo query parameter is required")

    cfg = CiBridgeConfig.for_subject_repo(repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )

    per_page = min(max(limit, 1), 50)
    url = f"{GITHUB_API}/repos/{repo}/releases?per_page={per_page}"
    status, body, _ = _http_get(url, cfg.headers())
    if status != 200:
        raise HTTPException(
            status_code=status,
            detail=f"GitHub returned {status} listing releases: {body[:200]!r}",
        )

    try:
        raw_releases = json.loads(body or b"[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Invalid GitHub JSON: {exc}"
        ) from exc

    items: List[ReleaseSummary] = []
    for raw in raw_releases:
        tag = raw.get("tag_name") or ""
        if not tag:
            continue
        vdd_path = f"VDDs/VDD-{tag}.md"
        has_vdd = _vdd_exists(cfg, tag)
        items.append(
            ReleaseSummary(
                tag=tag,
                name=raw.get("name") or tag,
                body=raw.get("body") or "",
                html_url=raw.get("html_url") or "",
                published_at=raw.get("published_at"),
                author=(raw.get("author") or {}).get("login", ""),
                draft=bool(raw.get("draft", False)),
                prerelease=bool(raw.get("prerelease", False)),
                vdd_path=vdd_path if has_vdd else None,
                vdd_url=_vdd_url(repo, tag) if has_vdd else None,
            )
        )

    return ReleasesResponse(repo=repo, items=items)
