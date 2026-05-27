"""Pydantic models for the VDD Drafter agent."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ModuleVersion(BaseModel):
    name: str
    version: str
    source_path: Optional[str] = None


class VDDDraftInput(BaseModel):
    """Inputs the runner needs to produce a release VDD.

    The runner is invoked once per release; all fields are populated by
    the wayside-monitor workflow before calling the agent. Optional
    fields can be omitted — the LLM is asked to mark missing sections
    explicitly rather than hallucinate."""

    release_tag: str = Field(..., description="The git tag of this release, e.g. 'v0.1.0'")
    release_name: str = Field(default="", description="Display name of the release")
    release_body: str = Field(default="", description="Release notes (free-form markdown)")
    release_url: Optional[str] = Field(default=None, description="GitHub release page URL")
    repo: str = Field(..., description="Subject repo, e.g. 'federicomameli1/wayside-monitor'")
    previous_tag: Optional[str] = Field(default=None, description="Previous tag this release builds on")
    head_sha: str = Field(..., description="Commit SHA the release points at")
    diff_unified: str = Field(default="", description="git diff <previous_tag>..<head_sha> output")
    diff_stat: str = Field(default="", description="git diff --stat for a compact change overview")
    docs_bundle: Dict[str, str] = Field(
        default_factory=dict,
        description="APCS docs as {filename: text}",
    )
    module_versions: List[ModuleVersion] = Field(
        default_factory=list,
        description="Module name/version pairs extracted from the codebase",
    )
    image_repository: Optional[str] = Field(
        default=None,
        description="Container image repository (for the artifact section)",
    )
    diff_max_chars: int = Field(default=16000, ge=1000, le=120_000)


class VDDDraftOutput(BaseModel):
    vdd_markdown: str = Field(..., description="The full markdown VDD ready to commit")
    sections_present: List[str] = Field(
        default_factory=list,
        description="Which canonical sections the LLM populated (for QA)",
    )
    sections_missing: List[str] = Field(
        default_factory=list,
        description="Canonical sections the LLM explicitly flagged as missing evidence",
    )
    model: Optional[str] = Field(default=None, description="LLM model id used")
