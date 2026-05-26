"""Pydantic models for the PR review agent input/output."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    GO = "GO"
    HOLD = "HOLD"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class Highlight(BaseModel):
    """A single concrete finding from the analysis."""

    severity: Severity
    title: str
    description: str
    file_ref: Optional[str] = Field(
        default=None,
        description="Optional code location, e.g. 'sensor_collector/collector.py:42'",
    )
    doc_ref: Optional[str] = Field(
        default=None,
        description="Optional documentation reference, e.g. 'docs/APCS_Requirements.txt#3'",
    )


class PRMeta(BaseModel):
    number: int
    title: str = ""
    author: str = ""
    branch: str = ""
    base: str = "main"
    head_sha: str = ""


class PRReviewInput(BaseModel):
    diff_unified: str = Field(..., description="The unified diff of the PR")
    docs_dir: str = Field(..., description="Filesystem path to the docs directory to RAG over")
    pr_meta: PRMeta
    top_k: int = Field(default=5, ge=1, le=20)
    docs_extensions: List[str] = Field(default_factory=lambda: [".txt", ".md"])
    relative_to: Optional[str] = Field(
        default=None,
        description="Strip this prefix from chunk source paths in references",
    )


class PRReviewOutput(BaseModel):
    verdict: Verdict
    summary: str
    highlights: List[Highlight] = Field(default_factory=list)
    report_markdown: str = Field(..., description="Pre-rendered markdown ready to post as a PR comment")
    chunks_used: List[str] = Field(
        default_factory=list,
        description="IDs of retrieved chunks that fed the prompt — for traceability",
    )
    model: Optional[str] = Field(default=None, description="LLM model id used")
