"""Run the deterministic Brain orchestrator (Agents 4/5/6) against a
*real* subject repo — wayside-monitor — instead of one of the bundled
demo datasets.

Materializes the subject's APCS document bundle into a temp directory
by pulling each `docs/APCS_*.txt` file via the GitHub Contents API,
then drives Agent 4 (Release Readiness) via the brain orchestrator.

Why only Agent 4 today: the Brain's Agent 5 / Agent 6 stages require
phase-5 / phase-6 *structured* inputs (CSV traceability matrices,
defect register, test execution results, etc.) that wayside does not
publish in that shape. Synthesizing them from pytest output + the
APCS_Test_Procedure document is left as a follow-up — when it lands,
add the stages to `_build_stage_order()` and chain via the brain.

Endpoint:
    POST /brain/run-wayside
        body: { "repo": "owner/repo", "ref": "main"|tag|sha (optional) }
        returns: BrainRunReport.to_dict()
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .ci_bridge import CiBridgeConfig, _http_get  # noqa: F401

from agents.brain import (  # noqa: E402
    BrainOrchestrator,
    BrainOrchestratorError,
    BrainRunRequest,
    StageRegistry,
    build_agent4_stage,
)
from agents.brain.adapters import Agent4StageSettings  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brain", tags=["brain-wayside"])

GITHUB_API = "https://api.github.com"

# Files we need from the subject repo to feed the apcs_doc_bundle adapter.
# Order matters for `list_scenarios`, so keep this consistent.
APCS_FILES: Tuple[str, ...] = (
    "APCS_Requirements.txt",
    "APCS_Module_Version_Inventory.txt",
    "APCS_Test_Procedure.txt",
    "APCS_VDD.txt",
    "APCS_Emails.txt",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RunWaysideRequest(BaseModel):
    repo: str = Field(..., description="Subject repo, e.g. 'federicomameli1/wayside-monitor'")
    ref: Optional[str] = Field(
        default=None,
        description="Branch, tag, or SHA. Defaults to the repo default branch.",
    )
    head_sha: Optional[str] = Field(
        default=None,
        description="Commit SHA the run is about — only used in scenario_id; falls back to ref.",
    )
    docs_dir: str = Field(
        default="docs",
        description="Path within the repo where APCS_*.txt files live.",
    )
    use_llm_summary: bool = Field(
        default=True,
        description="If true and the pod has OPENROUTER_API_KEY, refine the deterministic explanation with an LLM narration pass.",
    )


# ---------------------------------------------------------------------------
# GitHub Contents API helpers
# ---------------------------------------------------------------------------


def _fetch_apcs_file(
    cfg: CiBridgeConfig,
    docs_dir: str,
    filename: str,
    ref: Optional[str],
) -> Optional[bytes]:
    """Return the raw bytes of a single APCS document or None if absent."""
    path = f"{docs_dir.rstrip('/')}/{filename}"
    url = f"{GITHUB_API}/repos/{cfg.repo}/contents/{path}"
    if ref:
        url += f"?ref={ref}"
    status, body, _ = _http_get(url, cfg.headers())
    if status == 404:
        return None
    if status != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                f"GitHub returned {status} fetching {path}@{ref or 'default'}: "
                f"{(body[:200] or b'').decode('utf-8', errors='replace')}"
            ),
        )
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Invalid GitHub JSON for {path}: {exc}"
        ) from exc

    encoding = payload.get("encoding")
    content = payload.get("content") or ""
    if encoding == "base64":
        # GitHub wraps base64 with newlines every 60 chars; base64.b64decode
        # tolerates that, so no preprocessing needed.
        return base64.b64decode(content)
    # Older / edge responses occasionally return UTF-8 directly.
    return content.encode("utf-8")


def materialize_apcs_bundle(
    cfg: CiBridgeConfig,
    ref: Optional[str],
    docs_dir: str,
    target_dir: Path,
) -> List[str]:
    """Download every APCS_*.txt from the subject repo into `target_dir`.

    Returns the list of file names actually fetched (subset of APCS_FILES).
    Raises HTTPException if not a single file is found — without a bundle
    Agent 4 has nothing to ingest.
    """
    fetched: List[str] = []
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in APCS_FILES:
        data = _fetch_apcs_file(cfg, docs_dir, name, ref)
        if data is None:
            logger.info("APCS bundle: %s not found at %s@%s", name, docs_dir, ref or "default")
            continue
        (target_dir / name).write_bytes(data)
        fetched.append(name)

    if not fetched:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No APCS_*.txt files found under {docs_dir}/ on {cfg.repo}@{ref or 'default'}. "
                "Agent 4 needs at least one document to ingest."
            ),
        )
    return fetched


# ---------------------------------------------------------------------------
# Orchestrator wiring
# ---------------------------------------------------------------------------


def _get_llm_generate(use_llm: bool):
    """Resolve the OpenRouter narration callable lazily.

    Imported from `backend.app` instead of duplicated so the chat /agents/run
    endpoint and this one share the same model + headers configuration."""
    if not use_llm:
        return None
    try:
        from .app import _build_llm_generate  # type: ignore
    except ImportError:
        try:
            from app import _build_llm_generate  # type: ignore
        except Exception:  # pragma: no cover - defensive
            return None
    try:
        return _build_llm_generate()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not build LLM generator: %s", exc)
        return None


def _scenario_id_for(ref: Optional[str], head_sha: Optional[str]) -> str:
    candidate = (head_sha or ref or "head").strip()
    short = candidate[:12] if candidate else "head"
    return f"WAYSIDE-{short}"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/run-wayside")
def run_wayside(req: RunWaysideRequest) -> Dict[str, Any]:
    cfg = CiBridgeConfig.for_subject_repo(req.repo)
    if not cfg.token:
        raise HTTPException(
            status_code=503,
            detail="SUBJECT_REPO_TOKEN is not configured in the backend env",
        )

    ref = (req.ref or "").strip() or None

    with tempfile.TemporaryDirectory(prefix="verdict-wayside-") as tmpdir:
        target = Path(tmpdir)
        fetched = materialize_apcs_bundle(cfg, ref, req.docs_dir, target)
        logger.info(
            "Materialized %d APCS files from %s@%s into %s",
            len(fetched), req.repo, ref or "default", target,
        )

        llm_generate = _get_llm_generate(req.use_llm_summary)

        stage = build_agent4_stage(
            settings=Agent4StageSettings(
                dataset_root=str(target),
                source_adapter_kind="apcs_doc_bundle",
                use_llm_summary=bool(llm_generate),
                strict_schema=False,
            ),
            llm_generate=llm_generate,
        )

        registry = StageRegistry()
        registry.register(stage)
        orchestrator = BrainOrchestrator(
            registry=registry,
            stage_order=("agent4",),
        )

        scenario_id = _scenario_id_for(ref, req.head_sha)
        run_request = BrainRunRequest(
            scenario_id=scenario_id,
            release_id=ref,
            metadata={
                "subject_repo": req.repo,
                "ref": ref or "(default branch)",
                "head_sha": req.head_sha,
                "docs_dir": req.docs_dir,
                "apcs_files_fetched": fetched,
                "runner": "backend/brain_wayside.py",
            },
        )

        try:
            report = orchestrator.run(run_request)
        except BrainOrchestratorError as exc:
            raise HTTPException(status_code=502, detail=f"Brain run failed: {exc}") from exc

    return report.to_dict()
