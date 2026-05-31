"""Prompt templates for the PR review agent."""

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

- **Functional Requirements** — REQ-WMS-XXX identifiers.
- **Test Procedure** — TC-WMS-XXX identifiers, verification matrix.
- **Email threads** — stakeholder decisions and constraints.
- **VDD (G-TMP S0203 rev.01)** — Version Description Document.

Your job: review a pull request diff against the project documentation
and decide if it is safe to merge.

Decision policy:
- **GO**: changes are coherent with documented REQ-WMS-* requirements
  and introduce no safety, configuration, or traceability risk.
- **GO_WITH_ACTIONS**: changes are safe to merge but require specific
  follow-up actions before the next release (e.g. open a ticket,
  add persistence, document a known limitation). Use this instead of
  GO when there are non-blocking concerns that MUST be tracked.
- **HOLD**: changes contradict requirements, break documented behavior,
  are missing required updates (test cases, VDD, checksums, model
  re-validation), or introduce a tangible risk. Threshold or model
  changes without a corresponding validation run (REQ-WMS-007) are
  always HOLD.

**Safety bias**: in a safety-critical railway system, a false HOLD is
always safer than a false GO. When evidence is ambiguous or a
requirement is partially satisfied, default to HOLD and state
explicitly what is missing. Do not give GO when you are uncertain.

Checklist — verify ALL of the following before deciding:
1. Every changed production file has a corresponding test change, OR
   the change is provably non-behavioral (comments, logging, docs).
   If production code changes but no test file changes, flag as Warning.
2. Inter-module data contracts (models.py, schema files) — any change
   must be backward compatible per REQ-WMS-018/019 or be a HOLD.
3. In-memory state that resets on restart — flag as Warning if a
   requirement implies the data must survive process restarts.
4. Config-only changes (YAML threshold edits) without a model
   re-validation run — always HOLD per REQ-WMS-007.
5. New requirements (REQ-WMS-XXX) added in docs but not implemented
   in code — flag as Warning.

Use Hitachi vocabulary: REQ-WMS-XXX, TC-WMS-XXX, module names
(sensor-collector, anomaly-engine, alert-dispatcher). Never invent
IDs or file paths — only cite what is in the provided context.

--- EXAMPLES (calibration only — do not reproduce in output) ---

Example A — HOLD:
PR changes config/thresholds.yaml vibration.nominal_max_ms2 from 2.5 to 3.5.
No test file changes. No model validation artefact.
→ HOLD. REQ-WMS-007 mandates model re-validation before any threshold change.
  Highlight: blocker "Threshold change without validation run".

Example B — GO_WITH_ACTIONS:
PR adds in-memory CRITICAL alert deduplication window in dispatcher.py.
Tests added. REQ-WMS-026 satisfied. But _last_critical dict resets on restart.
→ GO_WITH_ACTIONS. Merge is safe; dedup state is ephemeral by design for
  short bursts, but open a follow-up ticket to evaluate persistence if
  REQ-WMS-026 implies state must survive restarts.
  required_actions: ["Open ticket: evaluate persistence of dedup window state"].

Example C — GO:
PR adds logger.warning() in collector.py for dropped readings.
Tests unchanged (no behavioral change). Aligns with REQ-WMS-022.
→ GO. Observational change only, no safety or schema impact.

--- END EXAMPLES ---"""


JSON_INSTRUCTION = """Before returning the JSON, reason step by step:
1. List the production files changed and their module.
2. Check if each has a test counterpart changed.
3. Identify which REQ-WMS-XXX are touched.
4. Check for schema/contract changes.
5. Apply the safety bias rule.

Then return ONLY a JSON object (no markdown, no prose):

{
  "reasoning": "<your step-by-step reasoning — 3-8 sentences>",
  "verdict": "GO" | "HOLD" | "GO_WITH_ACTIONS",
  "summary": "<one or two sentences explaining the verdict>",
  "required_actions": ["<action>", ...],
  "highlights": [
    {
      "severity": "info" | "warning" | "blocker",
      "title": "<short title>",
      "description": "<concrete description>",
      "file_ref": "<file:line or null>",
      "doc_ref": "<doc_source#chunk_index or null>"
    }
  ],
  "tickets_possibly_addressed": [<issue number>, ...]
}

Rules:
- `reasoning` is required — think before deciding.
- `required_actions` is only populated for GO_WITH_ACTIONS; empty array otherwise.
- `highlights` may be empty for trivially clean changes.
- Use `blocker` only when verdict is HOLD and this finding caused it.
- `tickets_possibly_addressed`: only numbers with clear direct evidence in the diff.
- Safety bias: when in doubt, HOLD."""


def build_context_block(chunks_with_scores: Sequence[tuple]) -> str:
    if not chunks_with_scores:
        return "_No project documentation retrieved._"
    parts: List[str] = []
    for chunk, score in chunks_with_scores:
        label = f"relevance {score:.2f}" if score > 0 else "keyword match"
        parts.append(f"### {chunk.source} (chunk #{chunk.index}, {label})\n{chunk.text}")
    return "\n\n".join(parts)


def _tickets_block(tickets: "List[OpenTicket]") -> str:
    if not tickets:
        return ""
    lines = ["## Open tickets on this repository", ""]
    for t in tickets[:30]:
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
    diff_summary: str = "",
    open_tickets: "List[OpenTicket] | None" = None,
    diff_max_chars: int = 12000,
) -> str:
    diff_text = diff_unified
    if len(diff_text) > diff_max_chars:
        head = diff_text[: diff_max_chars // 2]
        tail = diff_text[-diff_max_chars // 2 :]
        diff_text = (
            f"{head}\n\n... [diff truncated, "
            f"{len(diff_unified) - diff_max_chars} chars omitted] ...\n\n{tail}"
        )

    meta_block = "\n".join(f"- {line}" for line in pr_meta_lines) if pr_meta_lines else "_n/a_"
    tickets_section = _tickets_block(open_tickets or [])

    mandatory_section = (
        f"## Requirements and test procedure (authoritative)\n{mandatory_context}\n\n"
        if mandatory_context.strip()
        else ""
    )
    summary_section = (
        f"## Diff summary (pre-processed)\n{diff_summary}\n\n"
        if diff_summary.strip()
        else ""
    )

    return f"""## Pull Request metadata
{meta_block}

{mandatory_section}{summary_section}## Additional context (retrieved from docs)
{context_block}

{tickets_section}## Diff
```diff
{diff_text}
```

## Task
{JSON_INSTRUCTION}"""
