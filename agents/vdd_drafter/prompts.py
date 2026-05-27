"""Prompt templates for the VDD Drafter agent.

The LLM is asked to return a single markdown document following a fixed
section structure. We do NOT ask for JSON here — the output IS the
deliverable, so it's rendered straight to a file with no post-processing.
"""

from __future__ import annotations

from typing import List, Sequence


CANONICAL_SECTIONS: Sequence[str] = (
    "Release summary",
    "Scope of change",
    "Module inventory",
    "Requirements coverage",
    "Test evidence summary",
    "Risks and mitigations",
    "Operational impact",
    "Sign-off checklist",
)


SYSTEM_PROMPT = """You are Verdict, an AI assistant specialized in drafting
Version Description Documents (VDDs) for railway safety software releases.

A VDD is the formal handover artifact between engineering and release
management. It must be:

- **Factual** — every claim grounded in the evidence provided. Never
  invent test counts, module versions, or requirement IDs.
- **Complete on what we have** — populate every section possible from
  the inputs. When evidence for a section is genuinely missing, write
  "_Evidence not available in this release bundle._" rather than
  fabricating content.
- **Concise but specific** — short sentences, named modules, named
  requirements (REQ-WMS-XXX), named tests when present. No fluff."""


def _docs_block(docs_bundle: dict) -> str:
    if not docs_bundle:
        return "_No APCS documents provided._"
    parts: List[str] = []
    order = [
        "APCS_Requirements.txt",
        "APCS_Module_Version_Inventory.txt",
        "APCS_Test_Procedure.txt",
        "APCS_VDD.txt",
        "APCS_Emails.txt",
    ]
    seen = set()
    for name in order:
        text = docs_bundle.get(name)
        if text:
            parts.append(f"### {name}\n{text}")
            seen.add(name)
    for name, text in docs_bundle.items():
        if name in seen or not text:
            continue
        parts.append(f"### {name}\n{text}")
    return "\n\n".join(parts) if parts else "_No APCS documents provided._"


def _module_versions_block(modules: list) -> str:
    if not modules:
        return "_No module versions extracted._"
    lines = ["| Module | Version | Source |", "|---|---|---|"]
    for m in modules:
        lines.append(
            f"| {m.name} | {m.version} | {m.source_path or '_n/a_'} |"
        )
    return "\n".join(lines)


def build_user_prompt(*, input_payload, _truncate=lambda text, _max: text) -> str:
    """Assemble the user-turn prompt. `_truncate` is a hook for callers
    that want to enforce a per-doc cap (the runner injects the LLM
    client's truncate function)."""

    diff = input_payload.diff_unified or ""
    if len(diff) > input_payload.diff_max_chars:
        head = diff[: input_payload.diff_max_chars // 2]
        tail = diff[-input_payload.diff_max_chars // 2 :]
        diff = (
            f"{head}\n\n... [diff truncated, "
            f"{len(input_payload.diff_unified) - input_payload.diff_max_chars} chars omitted] ...\n\n{tail}"
        )

    sections_list = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(CANONICAL_SECTIONS))

    parts: List[str] = [
        f"## Release metadata",
        f"- Repository: {input_payload.repo}",
        f"- Tag: {input_payload.release_tag}",
        f"- Release name: {input_payload.release_name or '_n/a_'}",
        f"- Previous tag: {input_payload.previous_tag or '_n/a_'}",
        f"- Head SHA: {input_payload.head_sha}",
        f"- Release URL: {input_payload.release_url or '_n/a_'}",
        f"- Image repository: {input_payload.image_repository or '_n/a_'}",
        "",
        "## Author-provided release notes",
        input_payload.release_body or "_No release notes provided._",
        "",
        "## Module versions extracted from the codebase",
        _module_versions_block(input_payload.module_versions),
        "",
        "## Diff stat",
        "```",
        (input_payload.diff_stat or "_no diff stat available_").strip(),
        "```",
        "",
        "## Cumulative diff",
        "```diff",
        diff or "_no diff available_",
        "```",
        "",
        "## APCS document bundle",
        _docs_block(input_payload.docs_bundle),
        "",
        "## Task",
        "",
        "Produce a single markdown document — the Version Description "
        "Document for this release. Use exactly these top-level sections, "
        "in this order:",
        "",
        sections_list,
        "",
        "After each section heading, write the content as concise prose "
        "or a short bullet list. Cite module names, requirement IDs "
        "(REQ-WMS-XXX), and test cases by name whenever the evidence "
        "supports it. If a section has no supporting evidence, write a "
        "single italic line _Evidence not available in this release "
        "bundle._ instead of inventing content.",
        "",
        "End the document with a horizontal rule and a one-line "
        "italic footer: _Auto-drafted by Verdict on release "
        f"`{input_payload.release_tag}`._",
        "",
        "Return ONLY the markdown — no surrounding code fences, no "
        "preamble, no 'Here is the VDD...' chatter.",
    ]
    return "\n".join(parts)
