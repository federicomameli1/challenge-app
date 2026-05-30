"""Prompt templates for the VDD Drafter agent.

The LLM is asked to return a single markdown document following a fixed
section structure. We do NOT ask for JSON here — the output IS the
deliverable, so it's rendered straight to a file with no post-processing.
"""

from __future__ import annotations

from typing import List, Sequence

from agents._sanitize import SECURITY_GUARDRAIL


CANONICAL_SECTIONS: Sequence[str] = (
    "Introduction",
    "Version Description",
    "Documentation Related to the Baseline",
    "Sw Version Build",
    "Changes Incorporated",
    "Sw Version Limitation",
    "Installation Instructions",
)


# Sub-section hints rendered into the prompt so the LLM produces the
# same depth as the Hitachi template G-TMP S0203 rev.01.
SUB_SECTION_HINTS: Sequence[tuple] = (
    (
        "Introduction",
        [
            "Purpose",
            "Applicability",
            "Terms, Acronyms and Abbreviations",
            "Reference Documents (Contractual / Project / Tender / Standards / GBMS)",
            "Description of Changes from the Previous Revision",
        ],
    ),
    (
        "Version Description",
        [
            "Inventory of materials released",
            "Inventory of software configuration items contents — identification, checksums, reference of components used",
        ],
    ),
    (
        "Documentation Related to the Baseline",
        [
            "Requirements specification documents",
            "Software conception, design, programming documents",
            "Testing documentation",
            "Other documents",
        ],
    ),
    (
        "Sw Version Build",
        [
            "SW Configuration items list (source files) — list only application source modules and configuration files that constitute the released software (e.g. Python packages, config files, Helm chart). Exclude CI/CD workflow files (.github/), deployment scripts, and test infrastructure.",
            "Build Environment for Reproducibility",
        ],
    ),
    (
        "Changes Incorporated",
        [
            "List of changes taken into account in this SW version",
            "List of changes NOT taken into account in this SW version",
        ],
    ),
    ("Sw Version Limitation", []),
    ("Installation Instructions", []),
)


SYSTEM_PROMPT = SECURITY_GUARDRAIL + "\n\n" + """You are Verdict, an AI assistant specialized in drafting
Version Description Documents (VDDs) for railway safety software releases.

The VDD you produce MUST follow the structure of the official Hitachi
template G-TMP S0203 rev.01. The seven canonical top-level sections
are fixed and must appear in the prescribed order. Do not rename,
reorder, merge, or skip them.

The VDD is the formal handover artifact between engineering and
release management. It must be:

- **Factual** — every claim grounded in the evidence provided. Never
  invent test counts, module versions, requirement IDs, checksums, or
  reference documents.
- **Complete on what we have** — populate each sub-section possible
  from the inputs. When evidence for a sub-section is genuinely
  missing, write a single italic line "_Evidence not available in
  this release bundle._" instead of fabricating content.
- **Concise but specific** — short sentences, named modules, named
  requirements (REQ-WMS-XXX), named tests when present. No fluff,
  no marketing language."""


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

    section_lines: List[str] = []
    for i, (section, subs) in enumerate(SUB_SECTION_HINTS, start=1):
        section_lines.append(f"  {i}. {section}")
        for sub in subs:
            section_lines.append(f"      - {sub}")
    sections_list = "\n".join(section_lines)

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
        "Document for this release, following the Hitachi template "
        "G-TMP S0203 rev.01. Use exactly these top-level sections in "
        "this order, with the listed sub-sections rendered as `### "
        "<sub-section name>` underneath:",
        "",
        sections_list,
        "",
        "Render each top-level section as `## <name>` (e.g. `## "
        "Introduction`) and each sub-section as `### <name>` "
        "(e.g. `### Purpose`). For sub-sections without supporting "
        "evidence in the inputs, write a single italic line "
        "_Evidence not available in this release bundle._ instead of "
        "fabricating content. Cite module names, requirement IDs "
        "(REQ-WMS-XXX), and test cases by their identifier whenever "
        "the evidence supports it.",
        "",
        "End the document with a horizontal rule (`---`) and a "
        "one-line italic footer: _Auto-drafted by Verdict on release "
        f"`{input_payload.release_tag}`._",
        "",
        "Return ONLY the markdown — no surrounding code fences, no "
        "preamble, no 'Here is the VDD...' chatter.",
    ]
    return "\n".join(parts)
