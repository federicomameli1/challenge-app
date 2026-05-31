"""End-to-end runner for the PR review agent.

Pipeline:
  1. Chunk the docs directory
  2. Embed all chunks (HF Inference API)
  3. Embed a representative slice of the diff
  4. Retrieve top-K most relevant chunks via cosine similarity
  5. Build the prompt and call the LLM
  6. Parse JSON response and render the markdown report
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Set

from agents._sanitize import (
    SanitizationError,
    annotate_unverified,
    cap_string,
    unverified_ids,
    validate_choice,
)
from agents.llm_client import LLMError, OpenRouterClient
from agents.rag import (
    Chunk,
    HFEmbeddingsClient,
    HFEmbeddingsError,
    chunk_directory,
    top_k,
)

from .models import Highlight, PRReviewInput, PRReviewOutput, Severity, Verdict
from .prompts import SYSTEM_PROMPT, build_context_block, build_user_prompt

logger = logging.getLogger(__name__)


class PRReviewError(Exception):
    """Raised when the PR review pipeline cannot complete."""


_DIFF_EMBEDDING_MAX_CHARS = 2000


class PRReviewRunner:
    """Orchestrates the PR review pipeline.

    Dependencies are injected so tests can stub them. In production use
    `PRReviewRunner.from_env()` which wires the real LLM and HF clients.
    """

    def __init__(
        self,
        llm_client: OpenRouterClient,
        embeddings_client: HFEmbeddingsClient,
    ) -> None:
        self.llm = llm_client
        self.embed = embeddings_client

    @classmethod
    def from_env(cls) -> Optional["PRReviewRunner"]:
        llm = OpenRouterClient.from_env()
        if llm is None:
            logger.warning("PRReviewRunner: no OpenRouter client (OPENROUTER_API_KEY missing)")
            return None
        embed = HFEmbeddingsClient.from_env()
        if embed is None:
            logger.warning("PRReviewRunner: no HF embeddings client (HUGGINGFACE_TOKEN missing)")
            return None
        return cls(llm_client=llm, embeddings_client=embed)

    def run(self, input: PRReviewInput) -> PRReviewOutput:
        chunks = chunk_directory(
            input.docs_dir,
            extensions=tuple(input.docs_extensions),
            relative_to=input.relative_to,
        )
        if not chunks:
            logger.info("PRReviewRunner: no chunks from docs_dir=%s", input.docs_dir)

        retrieved = self._retrieve(chunks, input.diff_unified, input.top_k)

        # Fix 2: keyword boost — always include chunks that contain REQ/TC IDs
        # explicitly cited in the diff, regardless of cosine score.
        retrieved = _boost_by_ids(input.diff_unified, chunks, retrieved)

        # Fix 1: always include the full requirements doc as mandatory context.
        # APCS_Requirements.txt is compact (~200 lines) and is the primary
        # reference — RAG alone is too unreliable when relevance scores are low.
        mandatory_context = _read_mandatory_context(input.docs_dir)

        meta_lines = [
            f"number: #{input.pr_meta.number}",
            f"title: {input.pr_meta.title}",
            f"author: {input.pr_meta.author}",
            f"branch: {input.pr_meta.branch} → {input.pr_meta.base}",
            f"head_sha: {input.pr_meta.head_sha}",
        ]
        user_prompt = build_user_prompt(
            diff_unified=input.diff_unified,
            pr_meta_lines=meta_lines,
            context_block=build_context_block(retrieved),
            mandatory_context=mandatory_context,
            diff_summary=_summarize_diff(input.diff_unified),
            open_tickets=input.open_tickets or [],
        )

        try:
            llm_payload = self.llm.complete_json(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except LLMError as exc:
            raise PRReviewError(f"LLM call failed: {exc}") from exc

        verification_context = (
            "\n\n".join(c.text for c, _ in retrieved)
            + "\n\n"
            + mandatory_context
            + "\n\n"
            + input.diff_unified
        )
        verdict, summary, highlights, required_actions, tickets_addressed = _coerce_llm_payload(
            llm_payload, verification_context=verification_context
        )
        report_md = _render_markdown_report(
            input.pr_meta, verdict, summary, highlights, retrieved,
            required_actions=required_actions,
            tickets_addressed=tickets_addressed,
            open_tickets=input.open_tickets or [],
        )
        report_md = cap_string(report_md, label="PR review markdown")

        return PRReviewOutput(
            verdict=verdict,
            summary=summary,
            highlights=highlights,
            required_actions=required_actions,
            tickets_possibly_addressed=tickets_addressed,
            report_markdown=report_md,
            chunks_used=[chunk.id for chunk, _ in retrieved],
            model=self.llm.model,
        )

    def _retrieve(
        self,
        chunks: List[Chunk],
        diff_unified: str,
        k: int,
    ) -> list:
        if not chunks:
            return []

        diff_query = diff_unified[:_DIFF_EMBEDDING_MAX_CHARS] or "(empty diff)"

        try:
            chunk_vectors = self.embed.embed_texts([c.text for c in chunks])
            query_vector = self.embed.embed_texts([diff_query])[0]
        except HFEmbeddingsError as exc:
            raise PRReviewError(f"Embedding call failed: {exc}") from exc

        return top_k(query_vector, chunks, chunk_vectors, k=k)


_ID_RE = re.compile(r"\b(REQ-WMS-\d+|TC-WMS-\d+)\b", re.IGNORECASE)
_DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
_REQUIREMENTS_FILENAMES = ("APCS_Requirements.txt", "requirements.txt")
_TEST_PROCEDURE_FILENAMES = ("APCS_Test_Procedure.txt",)
_SCHEMA_PATTERNS = re.compile(r"models\.py|schemas?/|schema\.py|_schema\.py", re.IGNORECASE)
_CONFIG_PATTERNS = re.compile(r"\.(yaml|yml|json|cfg|ini|toml)$", re.IGNORECASE)


def _read_mandatory_context(docs_dir: str) -> str:
    """Return Requirements + Test Procedure as a single mandatory context block.

    Both docs are small and authoritative — always injecting them avoids the
    RAG retrieval gap where critical requirements score below top-k.
    """
    base = Path(docs_dir)
    parts: List[str] = []
    for names, label in (
        (_REQUIREMENTS_FILENAMES, "REQUIREMENTS"),
        (_TEST_PROCEDURE_FILENAMES, "TEST PROCEDURE"),
    ):
        for name in names:
            candidate = base / name
            if candidate.exists():
                try:
                    text = candidate.read_text(encoding="utf-8", errors="replace")
                    parts.append(f"=== {label} ({name}) ===\n{text}")
                    break
                except OSError:
                    pass
    return "\n\n".join(parts)


def _summarize_diff(diff: str) -> str:
    """Extract a structured pre-processed summary of the diff for the LLM.

    Surfaces changed files, detected file categories (config/schema/test/prod),
    and schema change warnings so the LLM doesn't have to parse raw patch lines.
    """
    changed_files = _DIFF_FILE_RE.findall(diff)
    if not changed_files:
        return ""

    prod_files, test_files, config_files, schema_files = [], [], [], []
    for f in changed_files:
        if re.search(r"tests?/|test_", f):
            test_files.append(f)
        elif _CONFIG_PATTERNS.search(f):
            config_files.append(f)
        elif _SCHEMA_PATTERNS.search(f):
            schema_files.append(f)
        else:
            prod_files.append(f)

    lines = [f"Changed files ({len(changed_files)} total):"]
    if prod_files:
        lines.append(f"  Production  : {', '.join(prod_files)}")
    if test_files:
        lines.append(f"  Tests       : {', '.join(test_files)}")
    if config_files:
        lines.append(f"  Config      : {', '.join(config_files)}")
    if schema_files:
        lines.append(f"  Schema/model: {', '.join(schema_files)}")

    if prod_files and not test_files:
        lines.append(
            "⚠ No test files changed — verify each production change is covered "
            "by existing tests or is non-behavioral."
        )
    if schema_files:
        lines.append(
            "⚠ Schema/model files changed — check backward compatibility "
            "per REQ-WMS-018/019."
        )
    if config_files:
        lines.append(
            "⚠ Config files changed — if thresholds or model params are modified, "
            "REQ-WMS-007 validation run may be required."
        )

    return "\n".join(lines)


_MAX_BOOSTED = 5


def _boost_by_ids(diff: str, all_chunks: List[Chunk], retrieved: list) -> list:
    """Ensure chunks containing REQ/TC IDs cited in the diff are always included.

    Avoids situations where a requirement is mentioned in comments or variable
    names in the diff but the corresponding doc chunk scored below top-k.
    Capped at _MAX_BOOSTED extra chunks to avoid token bloat.
    Deduplicated by chunk.id — no chunk appears twice.
    """
    ids_in_diff: Set[str] = {m.upper() for m in _ID_RE.findall(diff)}
    if not ids_in_diff:
        return retrieved

    already: Set[str] = {chunk.id for chunk, _ in retrieved}
    boosted = list(retrieved)
    n_boosted = 0
    for chunk in all_chunks:
        if n_boosted >= _MAX_BOOSTED:
            break
        if chunk.id in already:
            continue
        ids_in_chunk = {m.upper() for m in _ID_RE.findall(chunk.text)}
        if ids_in_diff & ids_in_chunk:
            boosted.append((chunk, 0.0))
            already.add(chunk.id)
            n_boosted += 1
            logger.debug("Boosted chunk %s (contains %s)", chunk.id, ids_in_diff & ids_in_chunk)
    return boosted


def _coerce_llm_payload(payload: dict, verification_context: str = "") -> tuple:
    # Returns (verdict, summary, highlights, required_actions, tickets_addressed)
    # Fix 1: reasoning field is consumed here and discarded — it drove the LLM's
    # chain-of-thought but is not surfaced to users.
    reasoning = payload.get("reasoning", "")
    if reasoning:
        logger.debug("LLM reasoning: %s", reasoning[:500])

    try:
        verdict_raw = validate_choice(
            payload.get("verdict"), ["GO", "HOLD", "GO_WITH_ACTIONS"], "verdict"
        )
    except SanitizationError as exc:
        raise PRReviewError(str(exc)) from exc
    verdict = Verdict(verdict_raw)

    summary = cap_string(
        str(payload.get("summary", "")).strip() or "(no summary provided)",
        max_chars=2_000,
        label="summary",
    )

    highlights_raw = payload.get("highlights") or []
    if not isinstance(highlights_raw, list):
        raise PRReviewError("LLM 'highlights' is not a list")

    # Cross-check every identifier the model cited against the input
    # context. Any ID not found there is fabricated; tag it so the user
    # cannot mistake it for a real reference.
    cited_blob = summary + " " + " ".join(
        " ".join(
            str((h or {}).get(field) or "")
            for field in ("title", "description", "file_ref", "doc_ref")
        )
        for h in highlights_raw
        if isinstance(h, dict)
    )
    unverified = unverified_ids(cited_blob, verification_context)
    summary = annotate_unverified(summary, unverified)

    highlights: List[Highlight] = []
    for item in highlights_raw[:50]:  # hard cap: 50 highlights is more than plenty
        if not isinstance(item, dict):
            continue
        try:
            severity = Severity(str(item.get("severity", "info")).strip().lower())
        except ValueError:
            severity = Severity.INFO
        title = cap_string(
            str(item.get("title", "")).strip() or "(untitled)",
            max_chars=300,
            label="highlight title",
        )
        description = cap_string(
            annotate_unverified(str(item.get("description", "")).strip(), unverified),
            max_chars=2_000,
            label="highlight description",
        )
        highlights.append(
            Highlight(
                severity=severity,
                title=title,
                description=description,
                file_ref=_nullable_str(item.get("file_ref")),
                doc_ref=_nullable_str(item.get("doc_ref")),
            )
        )
    # Fix 7: required_actions for GO_WITH_ACTIONS
    required_actions_raw = payload.get("required_actions") or []
    required_actions: List[str] = []
    if isinstance(required_actions_raw, list):
        for item in required_actions_raw[:10]:
            s = cap_string(str(item).strip(), max_chars=500, label="required_action")
            if s:
                required_actions.append(s)

    tickets_raw = payload.get("tickets_possibly_addressed") or []
    tickets_addressed: List[int] = []
    if isinstance(tickets_raw, list):
        for item in tickets_raw:
            try:
                tickets_addressed.append(int(item))
            except (TypeError, ValueError):
                pass

    return verdict, summary, highlights, required_actions, tickets_addressed


def _nullable_str(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "null":
        return None
    return s


_SEVERITY_BADGE = {
    Severity.BLOCKER: "🛑 Blocker",
    Severity.WARNING: "⚠️ Warning",
    Severity.INFO: "ℹ️ Info",
}


def _render_markdown_report(
    pr_meta,
    verdict: Verdict,
    summary: str,
    highlights: List[Highlight],
    retrieved: list,
    *,
    required_actions: List[str] | None = None,
    tickets_addressed: List[int] | None = None,
    open_tickets=None,
) -> str:
    if verdict is Verdict.GO:
        verdict_badge = "✅ **GO**"
    elif verdict is Verdict.GO_WITH_ACTIONS:
        verdict_badge = "🔵 **GO WITH ACTIONS**"
    else:
        verdict_badge = "🟠 **HOLD**"
    parts: List[str] = [
        "## [Verdict] LLM Review",
        "",
        f"**Verdict:** {verdict_badge}",
        "",
        f"**Summary:** {summary}",
        "",
    ]
    if highlights:
        parts.append("### Findings")
        parts.append("")
        for h in highlights:
            badge = _SEVERITY_BADGE.get(h.severity, "ℹ️ Info")
            line = f"- **{badge} — {h.title}**"
            parts.append(line)
            parts.append(f"  {h.description}")
            refs = []
            if h.file_ref:
                refs.append(f"`{h.file_ref}`")
            if h.doc_ref:
                refs.append(f"_{h.doc_ref}_")
            if refs:
                parts.append(f"  Refs: {', '.join(refs)}")
        parts.append("")
    else:
        parts.append("_No specific findings — the diff looks aligned with the documented requirements._")
        parts.append("")

    if required_actions:
        parts.append("### Required actions before next release")
        parts.append("")
        for action in required_actions:
            parts.append(f"- [ ] {action}")
        parts.append("")

    if tickets_addressed:
        ticket_map = {t.number: t.title for t in (open_tickets or [])}
        parts.append("### Tickets possibly addressed")
        parts.append("")
        parts.append("> ⚠️ Advisory only — verify before closing.")
        parts.append("")
        for n in tickets_addressed:
            title = ticket_map.get(n, "")
            parts.append(f"- #{n}{f': {title}' if title else ''}")
        parts.append("")

    if retrieved:
        rag_chunks = [(c, s) for c, s in retrieved if s > 0.0]
        boosted_chunks = [(c, s) for c, s in retrieved if s == 0.0]
        parts.append("<details>")
        parts.append("<summary>Documentation context</summary>")
        parts.append("")
        if rag_chunks:
            parts.append("**Retrieved (RAG)**")
            parts.append("")
            for chunk, score in rag_chunks:
                parts.append(f"- `{chunk.id}` (relevance {score:.2f})")
            parts.append("")
        if boosted_chunks:
            parts.append("**Injected (keyword match)**")
            parts.append("")
            for chunk, _ in boosted_chunks:
                parts.append(f"- `{chunk.id}`")
            parts.append("")
        parts.append("</details>")
    parts.append("")
    parts.append(f"_PR #{pr_meta.number} · head `{pr_meta.head_sha[:8] if pr_meta.head_sha else 'n/a'}` · automated review_")
    return "\n".join(parts)
