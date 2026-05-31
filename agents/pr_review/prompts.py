"""Prompt templates for the PR review agent.

The LLM is asked to return a strict JSON object. The runner then renders
a markdown report from the structured output, so the prompt does not need
to instruct the model on markdown formatting (one less thing to get wrong).
"""

from __future__ import annotations

from typing import List, Sequence, TYPE_CHECKING

from agents._sanitize import SECURITY_GUARDRAIL
from agents.rag import Chunk

if TYPE_CHECKING:
    from .models import OpenTicket


SYSTEM_PROMPT = SECURITY_GUARDRAIL + "\n\n" + """You are Verdict, an AI release readiness analyst for a
railway safety software project that follows the Hitachi Rail GBMS
documentation framework. The project lifecycle is governed by the
following authoritative artifacts (you do not have full access to
them — only what is retrieved into context):

- **Product Description** — high-level system overview.
- **SW Functional Architecture** — module decomposition and data flow.
- **Functional Requirements** — REQ-WMS-XXX identifiers, traced to
  test cases.
- **Test Procedure** — TC-WMS-XXX identifiers, verification matrix
  per the GBMS G-PRC test-procedure conventions.
- **Email threads** — stakeholder decisions and constraints not yet
  reflected in formal docs (e.g. nulla osta, change requests).
- **VDD (G-TMP S0203 rev.01)** — Version Description Document produced
  at release time.

Your job: review a pull request diff against the project's
documentation (the chunks retrieved into context) and decide if it is
safe to merge.

Decision policy:
- **GO**: changes are coherent with documented REQ-WMS-* requirements
  and introduce no obvious safety, configuration, or traceability
  risk. Minor stylistic/structural concerns can still be GO with
  warnings.
- **HOLD**: changes contradict requirements, break documented
  behavior, are missing required updates (test cases, VDD, module
  inventory checksums, model re-validation), or introduce a tangible
  risk that a human should review before merging. Threshold or model
  changes without a corresponding validation run (REQ-WMS-007
  pattern) are always HOLD.

Be concrete. When you raise a finding, cite the file (and line if
known) and/or the documentation section that supports it. Use
Hitachi vocabulary: REQ-WMS-XXX for requirements, TC-WMS-XXX for
test cases, the actual module names (sensor-collector, anomaly-engine,
alert-dispatcher). Do not invent file paths, requirement IDs, or
documentation passages — only reference what is in the retrieved
context.

Also flag any of the following operational risks when present in the diff:
- In-memory state that is lost on process restart (flag if a requirement
  implies the state must survive restarts).
- Missing persistence or replay capability for safety-relevant data.
- Configuration loaded at startup only, with no hot-reload when the
  requirement mandates it (REQ-WMS-003 pattern)."""


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
  ],
  "tickets_possibly_addressed": [<issue number>, ...]
}

Rules:
- `highlights` may be empty (e.g. a trivially GO change).
- Use `blocker` only when the verdict is HOLD AND the finding is the reason.
- Refer to documentation chunks by their source path; only use refs that
  appear in the 'Project context' section.
- `tickets_possibly_addressed`: list ONLY issue numbers where the diff
  contains clear, direct evidence (changed files, fixed logic, updated
  config) that the ticket's problem is being resolved. Do NOT include
  tickets that are merely related or tangentially mentioned. If no ticket
  is clearly addressed, return an empty array."""


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


def _tickets_block(tickets: "List[OpenTicket]") -> str:
    if not tickets:
        return ""
    lines = ["## Open tickets on this repository", ""]
    for t in tickets[:30]:  # cap at 30 to avoid bloating the prompt
        label_str = f" [{', '.join(t.labels)}]" if t.labels else ""
        body_preview = ""
        if t.body:
            first_line = t.body.strip().splitlines()[0][:120]
            body_preview = f" — {first_line}"
        lines.append(f"- #{t.number}: {t.title}{label_str}{body_preview}")
    lines.append("")
    return "\n".join(lines)


def build_user_prompt(
    diff_unified: str,
    pr_meta_lines: Sequence[str],
    context_block: str,
    *,
    mandatory_context: str = "",
    open_tickets: "List[OpenTicket] | None" = None,
    diff_max_chars: int = 12000,
) -> str:
    """Assemble the user-turn prompt."""
    diff_text = diff_unified
    if len(diff_text) > diff_max_chars:
        head = diff_text[: diff_max_chars // 2]
        tail = diff_text[-diff_max_chars // 2 :]
        diff_text = f"{head}\n\n... [diff truncated, {len(diff_unified) - diff_max_chars} chars omitted] ...\n\n{tail}"

    meta_block = "\n".join(f"- {line}" for line in pr_meta_lines) if pr_meta_lines else "_n/a_"
    tickets_section = _tickets_block(open_tickets or [])

    mandatory_section = (
        f"## Requirements (full — authoritative)\n{mandatory_context}\n\n"
        if mandatory_context.strip()
        else ""
    )

    return f"""## Pull Request metadata
{meta_block}

{mandatory_section}## Additional context (retrieved from docs)
{context_block}

{tickets_section}## Diff
```diff
{diff_text}
```

## Task
{JSON_INSTRUCTION}"""
