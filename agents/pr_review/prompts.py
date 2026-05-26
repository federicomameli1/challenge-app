"""Prompt templates for the PR review agent.

The LLM is asked to return a strict JSON object. The runner then renders
a markdown report from the structured output, so the prompt does not need
to instruct the model on markdown formatting (one less thing to get wrong).
"""

from __future__ import annotations

from typing import List, Sequence

from agents.rag import Chunk


SYSTEM_PROMPT = """You are Verdict, an AI release readiness analyst.

Your job: review a pull request diff against the project's documentation
(requirements, test procedures, design documents, email threads) and decide
if it is safe to merge.

Decision policy:
- GO: changes are coherent with documented requirements and introduce no
  obvious risk. Minor stylistic/structural concerns can still be GO with
  warnings.
- HOLD: changes contradict requirements, break documented behavior, are
  missing required updates (tests, docs), or introduce a tangible risk
  that a human should review before merging.

Be concrete. When you raise a finding, cite the file (and line if known) or
the documentation section that supports it. Do not invent file paths or
documentation passages — only reference what is provided in the context."""


JSON_INSTRUCTION = """Return ONLY a JSON object with this exact schema (no
markdown, no prose around it):

{
  "verdict": "GO" | "HOLD",
  "summary": "<one or two sentences explaining the verdict>",
  "highlights": [
    {
      "severity": "info" | "warning" | "blocker",
      "title": "<short title>",
      "description": "<concrete description of the finding>",
      "file_ref": "<file:line or null>",
      "doc_ref": "<doc_source#chunk_index or null>"
    }
  ]
}

Rules:
- `highlights` may be empty (e.g. a trivially GO change).
- Use `blocker` only when the verdict is HOLD AND the finding is the reason.
- Refer to documentation chunks by their source path; only use refs that
  appear in the 'Project context' section."""


def build_context_block(chunks_with_scores: Sequence[tuple]) -> str:
    """Render retrieved chunks as a readable context block for the prompt.

    `chunks_with_scores` is a sequence of (Chunk, score) tuples.
    """
    if not chunks_with_scores:
        return "_No project documentation retrieved._"
    parts: List[str] = []
    for chunk, score in chunks_with_scores:
        parts.append(
            f"### {chunk.source} (chunk #{chunk.index}, relevance {score:.2f})\n{chunk.text}"
        )
    return "\n\n".join(parts)


def build_user_prompt(
    diff_unified: str,
    pr_meta_lines: Sequence[str],
    context_block: str,
    *,
    diff_max_chars: int = 12000,
) -> str:
    """Assemble the user-turn prompt."""
    diff_text = diff_unified
    if len(diff_text) > diff_max_chars:
        head = diff_text[: diff_max_chars // 2]
        tail = diff_text[-diff_max_chars // 2 :]
        diff_text = f"{head}\n\n... [diff truncated, {len(diff_unified) - diff_max_chars} chars omitted] ...\n\n{tail}"

    meta_block = "\n".join(f"- {line}" for line in pr_meta_lines) if pr_meta_lines else "_n/a_"

    return f"""## Pull Request metadata
{meta_block}

## Project context (retrieved from docs)
{context_block}

## Diff
```diff
{diff_text}
```

## Task
{JSON_INSTRUCTION}"""
