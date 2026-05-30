"""Tests for agents/vdd_drafter/ — section audit, code fence stripping, prompt building."""

import pytest

from agents.vdd_drafter.runner import _audit_sections, _strip_code_fences
from agents.vdd_drafter.prompts import CANONICAL_SECTIONS, build_user_prompt
from agents.vdd_drafter.models import VDDDraftInput


def _make_input(**kwargs) -> VDDDraftInput:
    defaults = dict(
        release_tag="v1.0.0",
        release_name="Release 1.0.0",
        release_body="Initial release.",
        repo="owner/wayside-monitor",
        head_sha="abc123",
        diff_unified="diff --git a/file.py b/file.py\n+print('hello')",
        diff_stat="1 file changed, 1 insertion(+)",
    )
    defaults.update(kwargs)
    return VDDDraftInput(**defaults)


# ---------------------------------------------------------------------------
# _strip_code_fences
# ---------------------------------------------------------------------------

class TestStripCodeFences:
    def test_no_fence_unchanged(self):
        text = "## Introduction\nSome content."
        assert _strip_code_fences(text) == text

    def test_plain_fence_stripped(self):
        text = "```\n## Introduction\nContent\n```"
        result = _strip_code_fences(text)
        assert "```" not in result
        assert "## Introduction" in result

    def test_language_tagged_fence_stripped(self):
        text = "```markdown\n## Introduction\nContent\n```"
        result = _strip_code_fences(text)
        assert "```" not in result
        assert "## Introduction" in result

    def test_single_fence_no_newline_unchanged(self):
        text = "```"
        result = _strip_code_fences(text)
        assert result == "```"

    def test_whitespace_stripped(self):
        text = "  \n## Intro\nContent\n  "
        result = _strip_code_fences(text)
        assert result == result.strip()


# ---------------------------------------------------------------------------
# _audit_sections
# ---------------------------------------------------------------------------

class TestAuditSections:
    def _full_vdd(self) -> str:
        return "\n\n".join(f"## {s}\nSome content." for s in CANONICAL_SECTIONS)

    def test_all_sections_present(self):
        present, missing = _audit_sections(self._full_vdd())
        assert set(present) == set(CANONICAL_SECTIONS)
        assert missing == []

    def test_missing_section_detected(self):
        md = "## Introduction\nContent.\n## Version Description\nContent."
        present, missing = _audit_sections(md)
        assert "Introduction" in present
        assert "Version Description" in present
        assert len(missing) > 0

    def test_empty_markdown_all_missing(self):
        present, missing = _audit_sections("")
        assert present == []
        assert set(missing) == set(CANONICAL_SECTIONS)

    def test_case_insensitive_detection(self):
        md = "## INTRODUCTION\nContent.\n## sw version build\nContent."
        present, _ = _audit_sections(md)
        assert "Introduction" in present
        assert "Sw Version Build" in present


# ---------------------------------------------------------------------------
# build_user_prompt
# ---------------------------------------------------------------------------

class TestBuildUserPrompt:
    def test_prompt_contains_release_tag(self):
        inp = _make_input(release_tag="v2.3.4")
        prompt = build_user_prompt(input_payload=inp)
        assert "v2.3.4" in prompt

    def test_prompt_contains_repo(self):
        inp = _make_input(repo="owner/wayside-monitor")
        prompt = build_user_prompt(input_payload=inp)
        assert "owner/wayside-monitor" in prompt

    def test_prompt_contains_all_canonical_sections(self):
        inp = _make_input()
        prompt = build_user_prompt(input_payload=inp)
        for section in CANONICAL_SECTIONS:
            assert section in prompt

    def test_prompt_contains_diff(self):
        inp = _make_input(diff_unified="+ added line")
        prompt = build_user_prompt(input_payload=inp)
        assert "+ added line" in prompt

    def test_long_diff_truncated_in_prompt(self):
        long_diff = "+" + "x" * 100_000
        inp = _make_input(diff_unified=long_diff, diff_max_chars=1000)
        prompt = build_user_prompt(input_payload=inp)
        assert "truncated" in prompt

    def test_prompt_contains_footer_instruction(self):
        inp = _make_input(release_tag="v1.0.0")
        prompt = build_user_prompt(input_payload=inp)
        assert "v1.0.0" in prompt
        assert "Auto-drafted" in prompt or "footer" in prompt.lower() or "---" in prompt

    def test_no_docs_bundle_placeholder(self):
        inp = _make_input(docs_bundle={})
        prompt = build_user_prompt(input_payload=inp)
        assert "No APCS documents" in prompt

    def test_docs_bundle_included(self):
        inp = _make_input(docs_bundle={"APCS_Requirements.txt": "REQ-WMS-001: ..."})
        prompt = build_user_prompt(input_payload=inp)
        assert "REQ-WMS-001" in prompt
