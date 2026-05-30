"""Tests for agents/pr_review/ — models and prompt building (no LLM calls)."""

import pytest

from agents.pr_review.models import (
    Highlight,
    PRMeta,
    PRReviewInput,
    PRReviewOutput,
    Severity,
    Verdict,
)
from agents.pr_review.prompts import SYSTEM_PROMPT, build_user_prompt
from agents._sanitize import SECURITY_GUARDRAIL


def _make_input(**kwargs) -> PRReviewInput:
    defaults = dict(
        diff_unified="diff --git a/main.py b/main.py\n+print('hello')",
        docs_dir="/tmp/docs",
        pr_meta=PRMeta(number=42, title="Fix anomaly engine", author="alice", branch="fix/engine"),
    )
    defaults.update(kwargs)
    return PRReviewInput(**defaults)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestPRReviewModels:
    def test_verdict_enum_values(self):
        assert Verdict.GO == "GO"
        assert Verdict.HOLD == "HOLD"

    def test_severity_enum_values(self):
        assert Severity.INFO == "info"
        assert Severity.WARNING == "warning"
        assert Severity.BLOCKER == "blocker"

    def test_highlight_optional_refs(self):
        h = Highlight(severity=Severity.INFO, title="t", description="d")
        assert h.file_ref is None
        assert h.doc_ref is None

    def test_pr_review_input_defaults(self):
        inp = _make_input()
        assert inp.top_k == 5
        assert ".txt" in inp.docs_extensions
        assert ".md" in inp.docs_extensions

    def test_pr_review_output_valid(self):
        out = PRReviewOutput(
            verdict=Verdict.GO,
            summary="Looks good.",
            report_markdown="## Summary\nLooks good.",
        )
        assert out.verdict == Verdict.GO
        assert out.highlights == []
        assert out.chunks_used == []


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

class TestPRReviewPrompts:
    def test_system_prompt_contains_guardrail(self):
        assert SECURITY_GUARDRAIL in SYSTEM_PROMPT

    def test_system_prompt_mentions_gbms(self):
        lower = SYSTEM_PROMPT.lower()
        assert "gbms" in lower or "hitachi" in lower or "req-wms" in lower

    def _prompt(self, diff="+line", meta_lines=None, context_block=""):
        return build_user_prompt(
            diff_unified=diff,
            pr_meta_lines=meta_lines or ["PR #42", "author: alice"],
            context_block=context_block,
        )

    def test_user_prompt_contains_diff(self):
        prompt = self._prompt(diff="+new line added")
        assert "+new line added" in prompt

    def test_user_prompt_contains_pr_metadata(self):
        prompt = self._prompt(meta_lines=["PR #99 - My PR", "author: bob"])
        assert "99" in prompt
        assert "bob" in prompt

    def test_user_prompt_contains_context_block(self):
        prompt = self._prompt(context_block="REQ-WMS-001: system shall...")
        assert "REQ-WMS-001" in prompt

    def test_user_prompt_requests_json_output(self):
        prompt = self._prompt()
        assert "json" in prompt.lower()

    def test_user_prompt_requests_verdict_field(self):
        prompt = self._prompt()
        assert "verdict" in prompt.lower() or "GO" in prompt or "HOLD" in prompt

    def test_long_diff_truncated(self):
        long_diff = "+" + "x" * 50_000
        prompt = build_user_prompt(
            diff_unified=long_diff,
            pr_meta_lines=[],
            context_block="",
            diff_max_chars=1000,
        )
        assert "truncated" in prompt
