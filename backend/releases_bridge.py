"""Bridge for published GitHub releases on the subject repo.

Lists tag-based releases and points at the auto-drafted VDD file.
Also exposes POST /releases to publish a new GitHub release from the UI.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .ci_bridge import CiBridgeConfig, _http_get

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
    vdd_docx_url: Optional[str] = Field(
        default=None,
        description="Raw GitHub URL to download the filled .docx template",
    )
    vdd_pdf_url: Optional[str] = Field(
        default=None,
        description="Raw GitHub URL to download the PDF converted from the filled .docx",
    )


class ReleasesResponse(BaseModel):
    repo: str
    items: List[ReleaseSummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vdd_url(repo: str, tag: str) -> str:
    return f"https://github.com/{repo}/blob/main/VDDs/VDD-{tag}.md"


def _vdd_docx_url(repo: str, tag: str) -> str:
    return f"https://github.com/{repo}/raw/main/VDDs/VDD-{tag}.docx"


def _vdd_pdf_url(repo: str, tag: str) -> str:
    return f"https://github.com/{repo}/raw/main/VDDs/VDD-{tag}.pdf"


def _vdd_exists(cfg: CiBridgeConfig, tag: str, ext: str = ".md") -> bool:
    """Probe the GitHub Contents API to confirm the VDD file is committed."""
    url = f"{GITHUB_API}/repos/{cfg.repo}/contents/VDDs/VDD-{tag}{ext}?ref=main"
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
        has_vdd = _vdd_exists(cfg, tag, ".md")
        has_docx = _vdd_exists(cfg, tag, ".docx")
        has_pdf = _vdd_exists(cfg, tag, ".pdf")
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
                vdd_docx_url=_vdd_docx_url(repo, tag) if has_docx else None,
                vdd_pdf_url=_vdd_pdf_url(repo, tag) if has_pdf else None,
            )
        )

    return ReleasesResponse(repo=repo, items=items)


# ---------------------------------------------------------------------------
# Create release
# ---------------------------------------------------------------------------


class CreateReleaseRequest(BaseModel):
    repo: str
    tag_name: str = Field(..., description="Git tag, e.g. 'v1.0.0'")
    name: str = Field(default="", description="Release title (defaults to tag_name)")
    body: str = Field(default="", description="Release notes (markdown)")
    prerelease: bool = Field(default=False)
    target_commitish: str = Field(default="main", description="Branch or SHA to tag")


class CreateReleaseResponse(BaseModel):
    id: int
    tag_name: str
    html_url: str
    published_at: Optional[str] = None


@router.post("", response_model=CreateReleaseResponse, status_code=201)
def create_release(req: CreateReleaseRequest) -> CreateReleaseResponse:
    """Publish a new GitHub release on the subject repository."""
    cfg = CiBridgeConfig.for_subject_repo(req.repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )
    if not req.tag_name.strip():
        raise HTTPException(status_code=400, detail="tag_name is required")

    payload = json.dumps({
        "tag_name": req.tag_name.strip(),
        "name": req.name.strip() or req.tag_name.strip(),
        "body": req.body.strip(),
        "prerelease": req.prerelease,
        "target_commitish": req.target_commitish.strip() or "main",
    }).encode()

    url = f"{GITHUB_API}/repos/{req.repo}/releases"
    http_req = urllib.request.Request(
        url,
        data=payload,
        headers={**cfg.headers(), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_req, timeout=15) as resp:
            raw = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read()[:400].decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=exc.code,
            detail=f"GitHub returned {exc.code} creating release: {body}",
        ) from exc

    return CreateReleaseResponse(
        id=raw["id"],
        tag_name=raw["tag_name"],
        html_url=raw["html_url"],
        published_at=raw.get("published_at"),
    )
