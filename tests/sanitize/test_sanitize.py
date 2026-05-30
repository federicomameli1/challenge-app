"""Tests for agents/_sanitize.py — the shared LLM output guardrail layer."""

import pytest

from agents._sanitize import (
    SECURITY_GUARDRAIL,
    SanitizationError,
    annotate_unverified,
    cap_string,
    extract_known_ids,
    unverified_ids,
    validate_choice,
)


# ---------------------------------------------------------------------------
# cap_string
# ---------------------------------------------------------------------------

class TestCapString:
    def test_short_text_unchanged(self):
        text = "hello world"
        assert cap_string(text, max_chars=100) == text

    def test_exact_limit_unchanged(self):
        text = "a" * 100
        assert cap_string(text, max_chars=100) == text

    def test_long_text_truncated(self):
        text = "a" * 1000
        result = cap_string(text, max_chars=500)
        assert len(result) < 1000
        assert "[Verdict:" in result
        assert "truncated" in result

    def test_truncation_marker_includes_original_length(self):
        text = "x" * 1000
        result = cap_string(text, max_chars=300, label="summary")
        assert "1000" in result
        assert "summary" in result

    def test_non_string_passthrough(self):
        assert cap_string(None, max_chars=10) is None  # type: ignore
        assert cap_string(42, max_chars=10) == 42  # type: ignore

    def test_empty_string_unchanged(self):
        assert cap_string("", max_chars=10) == ""


# ---------------------------------------------------------------------------
# validate_choice
# ---------------------------------------------------------------------------

class TestValidateChoice:
    def test_valid_value_returned_uppercased(self):
        assert validate_choice("go", ["GO", "HOLD"], "verdict") == "GO"

    def test_case_insensitive(self):
        assert validate_choice("HoLd", ["GO", "HOLD"], "verdict") == "HOLD"

    def test_invalid_value_raises(self):
        with pytest.raises(SanitizationError, match="verdict"):
            validate_choice("MAYBE", ["GO", "HOLD"], "verdict")

    def test_empty_value_raises(self):
        with pytest.raises(SanitizationError):
            validate_choice("", ["GO", "HOLD"], "verdict")

    def test_none_value_raises(self):
        with pytest.raises(SanitizationError):
            validate_choice(None, ["GO", "HOLD"], "verdict")

    def test_whitespace_stripped(self):
        assert validate_choice("  GO  ", ["GO", "HOLD"], "verdict") == "GO"


# ---------------------------------------------------------------------------
# extract_known_ids
# ---------------------------------------------------------------------------

class TestExtractKnownIds:
    def test_extracts_req_ids(self):
        text = "See REQ-WMS-001 and REQ-WMS-042 for details."
        ids = extract_known_ids(text)
        assert "REQ-WMS-001" in ids
        assert "REQ-WMS-042" in ids

    def test_extracts_tc_ids(self):
        text = "TC-WMS-007 passes."
        assert "TC-WMS-007" in extract_known_ids(text)

    def test_case_insensitive_extraction(self):
        text = "req-wms-005 and tc-wms-010"
        ids = extract_known_ids(text)
        assert "REQ-WMS-005" in ids
        assert "TC-WMS-010" in ids

    def test_empty_text_returns_empty_set(self):
        assert extract_known_ids("") == set()
        assert extract_known_ids(None) == set()  # type: ignore

    def test_no_ids_returns_empty_set(self):
        assert extract_known_ids("no identifiers here") == set()

    def test_returns_uppercase(self):
        ids = extract_known_ids("req-wms-001")
        assert all(i == i.upper() for i in ids)


# ---------------------------------------------------------------------------
# unverified_ids
# ---------------------------------------------------------------------------

class TestUnverifiedIds:
    def test_all_grounded_returns_empty(self):
        output = "This satisfies REQ-WMS-001."
        context = "REQ-WMS-001: The system shall..."
        assert unverified_ids(output, context) == set()

    def test_ungrounded_id_returned(self):
        output = "Violates REQ-WMS-999."
        context = "REQ-WMS-001: The system shall..."
        assert "REQ-WMS-999" in unverified_ids(output, context)

    def test_empty_output_returns_empty(self):
        assert unverified_ids("", "REQ-WMS-001") == set()

    def test_mixed_grounded_and_ungrounded(self):
        output = "REQ-WMS-001 OK. REQ-WMS-999 invented."
        context = "REQ-WMS-001 is defined here."
        result = unverified_ids(output, context)
        assert "REQ-WMS-999" in result
        assert "REQ-WMS-001" not in result


# ---------------------------------------------------------------------------
# annotate_unverified
# ---------------------------------------------------------------------------

class TestAnnotateUnverified:
    def test_tags_unverified_id(self):
        text = "See REQ-WMS-999 for details."
        result = annotate_unverified(text, {"REQ-WMS-999"})
        assert "REQ-WMS-999 [unverified citation]" in result

    def test_does_not_tag_empty_set(self):
        text = "See REQ-WMS-001."
        assert annotate_unverified(text, set()) == text

    def test_idempotent(self):
        text = "REQ-WMS-999 is cited."
        once = annotate_unverified(text, {"REQ-WMS-999"})
        twice = annotate_unverified(once, {"REQ-WMS-999"})
        assert once == twice
        assert once.count("[unverified citation]") == 1

    def test_empty_text_unchanged(self):
        assert annotate_unverified("", {"REQ-WMS-001"}) == ""

    def test_case_insensitive_tagging(self):
        text = "req-wms-999 is cited."
        result = annotate_unverified(text, {"REQ-WMS-999"})
        assert "[unverified citation]" in result


# ---------------------------------------------------------------------------
# SECURITY_GUARDRAIL
# ---------------------------------------------------------------------------

class TestSecurityGuardrail:
    def test_guardrail_is_non_empty_string(self):
        assert isinstance(SECURITY_GUARDRAIL, str)
        assert len(SECURITY_GUARDRAIL) > 50

    def test_guardrail_mentions_key_threats(self):
        lower = SECURITY_GUARDRAIL.lower()
        assert "ignore" in lower or "instruction" in lower
        assert "data" in lower or "untrusted" in lower
