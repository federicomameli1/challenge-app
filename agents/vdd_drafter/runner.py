"""End-to-end runner for the VDD Drafter agent.

Pipeline:
  1. Build the LLM prompt from VDDDraftInput.
  2. Call OpenRouter for a long-form completion (the markdown VDD).
  3. Audit which canonical sections appear in the output for QA.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from agents.llm_client import LLMError, OpenRouterClient

from .models import VDDDraftInput, VDDDraftOutput
from .prompts import CANONICAL_SECTIONS, SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


class VDDDrafterError(Exception):
    """Raised when the VDD drafter pipeline cannot complete."""


# A VDD is a long document. Give the model a generous output budget.
_DEFAULT_MAX_TOKENS = 2000


class VDDDrafterRunner:
    """Orchestrates the VDD drafter pipeline."""

    def __init__(self, llm_client: OpenRouterClient) -> None:
        self.llm = llm_client

    @classmethod
    def from_env(cls) -> Optional["VDDDrafterRunner"]:
        llm = OpenRouterClient.from_env()
        if llm is None:
            logger.warning(
                "VDDDrafterRunner: no OpenRouter client (OPENROUTER_API_KEY missing)"
            )
            return None
        return cls(llm_client=llm)

    def run(self, input: VDDDraftInput) -> VDDDraftOutput:
        user_prompt = build_user_prompt(input_payload=input)

        try:
            text = self.llm.complete(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=_DEFAULT_MAX_TOKENS,
            )
        except LLMError as exc:
            raise VDDDrafterError(f"LLM call failed: {exc}") from exc

        if not text or not text.strip():
            raise VDDDrafterError("LLM returned empty content")

        markdown = _strip_code_fences(text.strip())
        present, missing = _audit_sections(markdown)

        return VDDDraftOutput(
            vdd_markdown=markdown,
            sections_present=present,
            sections_missing=missing,
            model=self.llm.model,
        )


def _strip_code_fences(text: str) -> str:
    """If the LLM wrapped the whole document in ``` fences despite our
    instruction, peel them off."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Drop the opening fence (which may include a language tag) and the
        # closing fence on the last line, if present.
        first_newline = stripped.find("\n")
        if first_newline == -1:
            return stripped
        inner = stripped[first_newline + 1 :]
        if inner.rstrip().endswith("```"):
            inner = inner.rstrip()[: -3]
        return inner.strip()
    return stripped


def _audit_sections(markdown: str) -> tuple:
    present: List[str] = []
    missing: List[str] = []
    lower = markdown.lower()
    for section in CANONICAL_SECTIONS:
        heading_token = section.lower()
        if heading_token in lower:
            present.append(section)
        else:
            missing.append(section)
    return present, missing
