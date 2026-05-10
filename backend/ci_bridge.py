"""
CI bridge — pulls Agent 4 / Agent 5 CI run results from GitHub Actions and
exposes a small set of operations the dashboard needs:

    GET  /ci/runs                  list recent CI runs of the configured repo
    GET  /ci/runs/{run_id}         fetch the parsed Agent 4 / Agent 5 reports
                                   contained in the run's artifacts
    POST /ci/approve               approve a pending environment deployment
                                   (i.e. unblock the test/prod gate)
    POST /ci/dispatch              trigger a `workflow_dispatch` event
                                   (used to manually re-run the pipeline)

Design notes:
- Configuration is read from environment variables. Nothing is required for
  the dashboard to render — endpoints degrade gracefully when the GitHub
  token / repo are missing, returning a structured "not_configured" payload
  instead of failing.
- We follow the GitHub-suggested approach: read the `ci-analysis-pre-test`
  and `ci-analysis-pre-prod` artifacts, unzip them in memory, and surface
  the `ci_report.json` that `scripts/eval/run_ci_analysis.py` produces.
- All upstream calls are made with a short timeout. The endpoints never
  block longer than a few seconds even on a slow network.

Environment variables:
    CI_BRIDGE_REPO        owner/repo (e.g. "federicomameli1/challenge-app")
    CI_BRIDGE_TOKEN       GitHub fine-grained PAT with Actions: read &
                          write (only "read" is strictly needed for runs +
                          artifacts; write is needed for /ci/approve and
                          /ci/dispatch)
    CI_BRIDGE_BRANCH      default branch to filter runs against (optional;
                          when unset, no branch filter is applied)
"""

from __future__ import annotations

import io
import json
import logging
import os
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
USER_AGENT = "challenge-app-ci-bridge/1.0"
DEFAULT_TIMEOUT = 8  # seconds
ARTIFACT_DOWNLOAD_TIMEOUT = 20  # GitHub redirects to blob storage which can be slow
ARTIFACT_NAMES = {
    "pre-test": "ci-analysis-pre-test",
    "pre-prod": "ci-analysis-pre-prod",
    "stage-results": "ci-stage-results",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class CiBridgeConfig:
    def __init__(self) -> None:
        self.repo = (os.environ.get("CI_BRIDGE_REPO") or "").strip()
        self.token = (os.environ.get("CI_BRIDGE_TOKEN") or "").strip()
        self.branch = (os.environ.get("CI_BRIDGE_BRANCH") or "").strip() or None

    @property
    def configured(self) -> bool:
        return bool(self.repo and self.token)

    def headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def to_status(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "repo": self.repo or None,
            "branch": self.branch,
            "token_present": bool(self.token),
        }

    @classmethod
    def for_subject_repo(cls, repo: str) -> "CiBridgeConfig":
        """Build a config targeting a subject repo, authenticated with SUBJECT_REPO_TOKEN."""
        instance = cls.__new__(cls)
        instance.repo = repo.strip()
        instance.token = (os.environ.get("SUBJECT_REPO_TOKEN") or "").strip()
        instance.branch = None
        return instance


def _config() -> CiBridgeConfig:
    return CiBridgeConfig()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


class _NoAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip the Authorization header when a redirect crosses to a different host.

    GitHub's artifact-download endpoint returns a 302 to a pre-signed blob
    storage URL (Azure/S3).  Forwarding the Bearer token to the storage host
    causes a 400 "conflicting auth" error, so we drop the header whenever the
    redirect destination host differs from the origin host.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Optional[urllib.request.Request]:
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None:
            orig_host = urllib.parse.urlparse(req.full_url).netloc
            new_host = urllib.parse.urlparse(newurl).netloc
            if orig_host != new_host:
                new_req.remove_header("Authorization")
                new_req.remove_header("authorization")
        return new_req


_opener = urllib.request.build_opener(_NoAuthRedirectHandler())


def _http_get(
    url: str,
    headers: Dict[str, str],
    timeout: int = DEFAULT_TIMEOUT,
) -> Tuple[int, bytes, Dict[str, str]]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        return exc.code, body, dict(exc.headers or {})
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub request failed: {exc.reason}") from exc


def _http_post(
    url: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[int, bytes]:
    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    headers = {**headers, "Content-Type": "application/json"} if body else dict(headers)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if hasattr(exc, "read") else b""
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub request failed: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# GitHub API operations
# ---------------------------------------------------------------------------


def _list_workflow_runs(cfg: CiBridgeConfig, limit: int = 10) -> List[Dict[str, Any]]:
    params = {"per_page": str(min(max(limit, 1), 30))}
    if cfg.branch:
        params["branch"] = cfg.branch
    url = f"{GITHUB_API}/repos/{cfg.repo}/actions/runs?{urllib.parse.urlencode(params)}"
    status, body, _ = _http_get(url, cfg.headers())
    if status >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned {status} listing workflow runs: {body[:200]!r}",
        )
    data = json.loads(body or b"{}")
    runs = data.get("workflow_runs") or []

    summaries = []
    for run in runs:
        head = run.get("head_commit") or {}
        actor = run.get("actor") or {}
        summaries.append(
            {
                "id": run.get("id"),
                "name": run.get("name"),
                "display_title": run.get("display_title"),
                "event": run.get("event"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "head_branch": run.get("head_branch"),
                "head_sha": (run.get("head_sha") or "")[:12],
                "head_commit_message": head.get("message", "").splitlines()[0] if head else "",
                "actor": actor.get("login"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "html_url": run.get("html_url"),
                "run_number": run.get("run_number"),
                "pull_requests": [
                    {"number": pr.get("number"), "url": pr.get("url")}
                    for pr in (run.get("pull_requests") or [])
                ],
            }
        )
    return summaries


def _list_run_artifacts(cfg: CiBridgeConfig, run_id: int) -> List[Dict[str, Any]]:
    url = f"{GITHUB_API}/repos/{cfg.repo}/actions/runs/{run_id}/artifacts"
    status, body, _ = _http_get(url, cfg.headers())
    if status >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned {status} listing artifacts for run {run_id}",
        )
    data = json.loads(body or b"{}")
    return data.get("artifacts") or []


def _download_artifact_zip(cfg: CiBridgeConfig, artifact_id: int) -> bytes:
    url = f"{GITHUB_API}/repos/{cfg.repo}/actions/artifacts/{artifact_id}/zip"
    status, body, _ = _http_get(url, cfg.headers(), timeout=ARTIFACT_DOWNLOAD_TIMEOUT)
    if status >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned {status} downloading artifact {artifact_id}",
        )
    return body


def _read_json_from_zip(zip_bytes: bytes, member: str) -> Optional[Dict[str, Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            try:
                with zf.open(member) as fh:
                    return json.loads(fh.read().decode("utf-8"))
            except KeyError:
                return None
    except zipfile.BadZipFile:
        return None


def _summarize_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a CI report down to what the dashboard renders directly.

    The full report is also attached, but the trimmed view keeps the table
    rows compact and avoids serializing very large diff/evidence blobs."""
    if not isinstance(report, dict):
        return {}
    rec = report.get("recommendation") or {}
    git_info = report.get("git") or {}
    evidence = report.get("evidence") or {}
    payload = (report.get("agent_output") or {}).get("payload") or {}
    # Extract only the summary line from diff_stat (e.g. "12 files changed, 340 insertions(+)")
    # instead of the full multi-line output which lists every changed file.
    diff_stat_raw = (git_info.get("diff_stat") or "").strip()
    diff_stat_lines = [l.strip() for l in diff_stat_raw.splitlines() if l.strip()]
    diff_stat_summary = diff_stat_lines[-1] if diff_stat_lines else ""

    return {
        "phase": report.get("phase"),
        "generated_at_utc": report.get("generated_at_utc"),
        "decision": rec.get("decision"),
        "decision_type": rec.get("decision_type"),
        "summary": rec.get("summary"),
        "human_action": rec.get("agent_human_action"),
        "human_gate": rec.get("human_gate"),
        "triggered_rules": rec.get("triggered_rules") or [],
        "confidence": rec.get("confidence"),
        "policy_version": rec.get("policy_version"),
        "head_sha": git_info.get("head_sha"),
        "diff_stat": diff_stat_summary,
        "release_docs_loaded": list((evidence.get("release_docs") or {}).keys()),
        "reason_count": len(payload.get("reasons") or []),
    }


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class ApproveDeploymentRequest(BaseModel):
    run_id: int
    environment_ids: List[int]
    state: str = "approved"  # "approved" | "rejected"
    comment: str = ""


class DispatchWorkflowRequest(BaseModel):
    workflow_file: str  # e.g. "ci.yml"
    ref: str  # branch or tag
    inputs: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


router = APIRouter(prefix="/ci", tags=["ci"])


@router.get("/status")
def ci_status() -> Dict[str, Any]:
    return _config().to_status()


@router.get("/subject-runs")
def list_subject_runs(repo: str = "", limit: int = 10) -> Dict[str, Any]:
    """List recent CI runs from a subject repo, authenticated via SUBJECT_REPO_TOKEN."""
    token = (os.environ.get("SUBJECT_REPO_TOKEN") or "").strip()
    if not repo or not token:
        return {
            "configured": False,
            "items": [],
            "repo": repo.strip() or None,
            "token_present": bool(token),
        }
    cfg = CiBridgeConfig.for_subject_repo(repo)
    runs = _list_workflow_runs(cfg, limit=limit)
    return {"configured": True, "items": runs, "repo": repo.strip()}


@router.get("/runs")
def list_runs(limit: int = 10) -> Dict[str, Any]:
    cfg = _config()
    if not cfg.configured:
        return {"configured": False, "items": [], "config": cfg.to_status()}

    runs = _list_workflow_runs(cfg, limit=limit)
    return {"configured": True, "items": runs, "config": cfg.to_status()}


@router.get("/runs/{run_id}")
def get_run_details(run_id: int) -> Dict[str, Any]:
    cfg = _config()
    if not cfg.configured:
        raise HTTPException(status_code=503, detail="CI bridge is not configured.")

    artifacts = _list_run_artifacts(cfg, run_id)
    by_name = {a.get("name"): a for a in artifacts if isinstance(a, dict)}

    reports: Dict[str, Any] = {}
    for phase, artifact_name in ARTIFACT_NAMES.items():
        artifact = by_name.get(artifact_name)
        if not artifact:
            continue
        try:
            zip_bytes = _download_artifact_zip(cfg, artifact["id"])
        except HTTPException as exc:
            reports[phase] = {"error": exc.detail}
            continue

        if phase == "stage-results":
            data = _read_json_from_zip(zip_bytes, "test_build_summary.json")
            reports[phase] = {"summary": data} if data else {"summary": None}
            continue

        report = _read_json_from_zip(zip_bytes, "ci_report.json")
        if report is None:
            reports[phase] = {"error": "ci_report.json not found in artifact"}
            continue

        reports[phase] = {
            "summary": _summarize_report(report),
            "report": report,
        }

    # Also surface raw run metadata so the dashboard can show conclusion etc.
    run_url = f"{GITHUB_API}/repos/{cfg.repo}/actions/runs/{run_id}"
    status_code, body, _ = _http_get(run_url, cfg.headers())
    run_meta = json.loads(body or b"{}") if status_code < 400 else {}

    return {
        "run_id": run_id,
        "configured": True,
        "reports": reports,
        "artifacts_available": sorted(by_name.keys()),
        "run": {
            "status": run_meta.get("status"),
            "conclusion": run_meta.get("conclusion"),
            "html_url": run_meta.get("html_url"),
            "head_branch": run_meta.get("head_branch"),
            "head_sha": (run_meta.get("head_sha") or "")[:12],
            "event": run_meta.get("event"),
        },
    }


@router.get("/runs/{run_id}/pending-deployments")
def list_pending_deployments(run_id: int) -> Dict[str, Any]:
    cfg = _config()
    if not cfg.configured:
        raise HTTPException(status_code=503, detail="CI bridge is not configured.")

    url = f"{GITHUB_API}/repos/{cfg.repo}/actions/runs/{run_id}/pending_deployments"
    status, body, _ = _http_get(url, cfg.headers())
    if status >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned {status} listing pending deployments for run {run_id}",
        )
    items = json.loads(body or b"[]")
    return {"items": items}


@router.post("/approve")
def approve_deployment(req: ApproveDeploymentRequest) -> Dict[str, Any]:
    cfg = _config()
    if not cfg.configured:
        raise HTTPException(status_code=503, detail="CI bridge is not configured.")
    if req.state not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="state must be 'approved' or 'rejected'.")

    url = f"{GITHUB_API}/repos/{cfg.repo}/actions/runs/{req.run_id}/pending_deployments"
    payload = {
        "environment_ids": req.environment_ids,
        "state": req.state,
        "comment": req.comment,
    }
    status, body = _http_post(url, cfg.headers(), payload=payload)
    if status >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned {status} approving run {req.run_id}: {body[:200]!r}",
        )
    return {"ok": True, "state": req.state, "run_id": req.run_id}


@router.post("/dispatch")
def dispatch_workflow(req: DispatchWorkflowRequest) -> Dict[str, Any]:
    cfg = _config()
    if not cfg.configured:
        raise HTTPException(status_code=503, detail="CI bridge is not configured.")

    url = f"{GITHUB_API}/repos/{cfg.repo}/actions/workflows/{req.workflow_file}/dispatches"
    payload = {"ref": req.ref, "inputs": req.inputs or {}}
    status, body = _http_post(url, cfg.headers(), payload=payload)
    if status >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned {status} dispatching workflow: {body[:200]!r}",
        )
    return {"ok": True, "workflow": req.workflow_file, "ref": req.ref}


__all__ = ["router"]
