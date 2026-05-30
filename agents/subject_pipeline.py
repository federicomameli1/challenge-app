"""
Multi-stage analysis pipeline for subject-repo (external repo) evaluation.

This pipeline is used when Verdict is asked to evaluate a third-party
repository (e.g. wayside-monitor). It combines:

  Stage 1 — Deterministic pre-checks
      Hard blockers that always produce HOLD regardless of LLM output:
      - CI tests failed or report unavailable
      - APCS bundle completely missing

  Stage 2 — LLM synthesis
      One comprehensive LLM call with all available evidence:
      - APCS document bundle (truncated to token budget)
      - Test execution summary (pass/fail + failed test names)
      - Commit diff info (changed files, diff stat, commit message)

  The deterministic stage can short-circuit to HOLD before the LLM is called,
  saving tokens and avoiding hallucinated GO decisions when tests are red.

Output schema is identical to LLMBundleAgent so run_ci_analysis.py can
consume either without branching.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ._sanitize import (
    SECURITY_GUARDRAIL,
    SanitizationError,
    annotate_unverified,
    cap_string,
    unverified_ids,
    validate_choice,
)
from .llm_client import LLMError, OpenRouterClient
from .test_report_parser import format_test_summary_for_prompt

logger = logging.getLogger(__name__)

_MAX_DOC_CHARS = 4_000   # per APCS doc — tighter budget to leave room for test/diff context
_MAX_DIFF_CHARS = 2_000  # diff stat / changed files block

_SYSTEM_PROMPT = SECURITY_GUARDRAIL + "\n\n" + """\
You are a Test Evidence analyst for a Hitachi Rail railway safety \
project. The reference subsystem is the Wayside Monitoring System \
(WMS). The project follows the Hitachi Rail GBMS documentation \
framework — in particular:

- Requirements are identified as **REQ-WMS-XXX** and traced to test \
cases following the GBMS verification matrix convention.
- Test cases are identified as **TC-WMS-XXX** and described in the \
project Test Procedure (G-PRC test-procedure style).
- Module versions are tracked in the Module Version Inventory and \
must match the entries declared in the upcoming VDD \
(G-TMP S0203 rev.01).
- Email threads (nulla osta, change requests, post-deploy errors) \
carry binding stakeholder decisions until they are absorbed into the \
formal documents.

You will receive a release evidence bundle containing:
  1. APCS documents (Requirements, Module Inventory, Test Procedure, VDD, Emails)
  2. Automated test execution results from the CI pipeline
  3. Code change information (commit message, changed files, diff stat)

Your task: decide whether this commit is ready to be promoted from \
the DEV environment to the TEST environment.

Evaluation rules (apply in order):
  1. Any failing or erroring automated test → HOLD. Tests are mandatory.
  2. A [MUST] REQ-WMS-* requirement clearly unmet → HOLD.
  3. An open unresolved BLOCKER in the email thread → HOLD.
  4. A module version mismatch vs Module Version Inventory, or a missing \
TC-WMS-* expected result → HOLD.
  5. Safety-critical files changed without corresponding documentation \
update (Test Procedure, VDD section, Module Inventory) → HOLD.
  6. Threshold / model / classifier changes without a corresponding \
model re-validation run (REQ-WMS-007 pattern) → HOLD.
  7. [SHOULD] / [COULD] misses → WARN only, never a standalone HOLD.
  8. If all MUST requirements are satisfied and tests pass → GO.

Cite the exact REQ-WMS-* and TC-WMS-* identifiers in your findings \
whenever the evidence supports it. Do not invent identifiers or \
quote passages that do not appear in the bundle.

Respond ONLY with a valid JSON object — no markdown fences, no extra text:
{
  "decision": "GO" or "HOLD",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence explaining the decision>",
  "findings": [
    {
      "rule": "<REQ-WMS-XXX, TC-WMS-XXX, or free-text label>",
      "status": "PASS" or "FAIL" or "WARN",
      "detail": "<short explanation>"
    }
  ],
  "human_action": "<what the operator should do next>"
}
"""


class SubjectRepoPipeline:
    """
    Orchestrates deterministic pre-checks and LLM synthesis for a subject repo.

    Pass client=None to run deterministic checks only (useful when no API key
    is configured or in tests).
    """

    def __init__(self, client: Optional[OpenRouterClient]) -> None:
        self.client = client

    def analyze(
        self,
        *,
        bundle: Dict[str, str],
        test_summary: Dict[str, Any],
        commit_info: Dict[str, Any],
        subject_repo: str = "",
        ref: str = "",
    ) -> Dict[str, Any]:
        """
        Run the full pipeline and return a structured decision dict.

        Always returns a usable result — errors fall back to a HOLD with
        an explanation so the CI pipeline is never left without a decision.
        """
        hard_blocks = _deterministic_checks(bundle, test_summary)

        if hard_blocks:
            return _hold_from_blocks(hard_blocks, test_summary)

        if self.client is None:
            return _no_llm_result(test_summary)

        user_msg = self._build_prompt(
            bundle=bundle,
            test_summary=test_summary,
            commit_info=commit_info,
            subject_repo=subject_repo,
            ref=ref,
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        try:
            raw = self.client.complete_json(messages, max_tokens=900)
            verification_context = "\n\n".join(bundle.values()) + "\n\n" + str(
                commit_info.get("diff_stat") or ""
            )
            return _normalize(raw, verification_context=verification_context)
        except Exception as exc:
            logger.warning("LLM synthesis failed (%s) — falling back to deterministic result", exc)
            return _no_llm_result(test_summary)

    def _build_prompt(
        self,
        *,
        bundle: Dict[str, str],
        test_summary: Dict[str, Any],
        commit_info: Dict[str, Any],
        subject_repo: str,
        ref: str,
    ) -> str:
        parts: List[str] = []

        if subject_repo:
            parts.append(f"Subject repository: {subject_repo}")
        if ref:
            parts.append(f"Commit ref: {ref[:12]}")
        parts.append("")

        # Test results block
        parts.append("=== CI TEST RESULTS ===")
        parts.append(format_test_summary_for_prompt(test_summary))
        parts.append("")

        # Code change info block
        parts.append("=== CODE CHANGE INFO ===")
        if commit_info.get("commit_message"):
            parts.append(f"Commit message: {commit_info['commit_message'].splitlines()[0][:200]}")
        if commit_info.get("author"):
            parts.append(f"Author: {commit_info['author']}")
        if commit_info.get("diff_stat"):
            stat = str(commit_info["diff_stat"])[:_MAX_DIFF_CHARS]
            parts.append(f"Diff stat: {stat}")
        changed = commit_info.get("changed_files", [])
        if changed:
            parts.append(f"Changed files ({len(changed)}):")
            for f in changed[:20]:
                parts.append(f"  - {f}")
            if len(changed) > 20:
                parts.append(f"  ... and {len(changed) - 20} more")
        parts.append("")

        # APCS docs block
        doc_order = [
            "APCS_Requirements.txt",
            "APCS_Module_Version_Inventory.txt",
            "APCS_Test_Procedure.txt",
            "APCS_VDD.txt",
            "APCS_Emails.txt",
        ]
        for name in doc_order:
            content = bundle.get(name, "")
            if not content:
                parts.append(f"=== {name} ===\n[NOT AVAILABLE]\n")
                continue
            truncated = self.client.truncate_to_tokens(content, _MAX_DOC_CHARS)
            parts.append(f"=== {name} ===\n{truncated}\n")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Deterministic pre-checks
# ---------------------------------------------------------------------------


def _deterministic_checks(
    bundle: Dict[str, str],
    test_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return a list of hard-blocker findings. Empty list means no hard blocks."""
    blocks: List[Dict[str, Any]] = []

    if not bundle:
        blocks.append({
            "rule": "APCS_BUNDLE_MISSING",
            "status": "FAIL",
            "detail": "No APCS documents available — cannot perform release readiness review.",
        })

    if not test_summary.get("available"):
        blocks.append({
            "rule": "TEST_REPORT_UNAVAILABLE",
            "status": "FAIL",
            "detail": f"Test report could not be retrieved: {test_summary.get('parse_error', 'unknown')}. "
                      "Cannot confirm test status.",
        })
    elif not test_summary.get("all_passed"):
        failed_count = test_summary.get("failed", 0) + test_summary.get("error", 0)
        failed_names = [t["name"] for t in test_summary.get("failed_tests", [])[:5]]
        detail = f"{failed_count} test(s) failed or errored."
        if failed_names:
            detail += " First failures: " + ", ".join(failed_names)
        blocks.append({
            "rule": "CI_TESTS_FAILED",
            "status": "FAIL",
            "detail": detail,
        })

    return blocks


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------


def _hold_from_blocks(
    blocks: List[Dict[str, Any]],
    test_summary: Dict[str, Any],
) -> Dict[str, Any]:
    summary_parts = [b["detail"] for b in blocks[:2]]
    return {
        "decision": "HOLD",
        "decision_type": "deterministic_block",
        "confidence": 1.0,
        "summary": " | ".join(summary_parts),
        "human_action": "Resolve all blocking issues listed in findings before requesting promotion.",
        "findings": blocks,
        "reasons": [
            {
                "title": b["rule"],
                "detail": b["detail"],
                "rule_code": b["rule"],
                "status": b["status"],
            }
            for b in blocks
        ],
        "policy_version": "subject-pipeline-v1",
        "test_summary": test_summary,
    }


def _no_llm_result(test_summary: Dict[str, Any]) -> Dict[str, Any]:
    all_passed = test_summary.get("all_passed", False)
    return {
        "decision": "GO" if all_passed else "HOLD",
        "decision_type": "deterministic_only",
        "confidence": 0.7 if all_passed else 1.0,
        "summary": (
            "All tests passed. LLM not configured — APCS review skipped."
            if all_passed
            else "Tests failed. LLM not configured."
        ),
        "human_action": "Configure OPENROUTER_API_KEY to enable full APCS analysis." if all_passed else "Fix failing tests.",
        "findings": [],
        "reasons": [],
        "policy_version": "subject-pipeline-v1",
        "test_summary": test_summary,
    }


def _error_result(message: str) -> Dict[str, Any]:
    return {
        "decision": "HOLD",
        "decision_type": "llm_error",
        "confidence": None,
        "summary": f"LLM synthesis failed: {message}",
        "human_action": "Review the APCS bundle and test results manually.",
        "findings": [],
        "reasons": [{"title": "LLM error", "detail": message, "rule_code": "", "status": "FAIL"}],
        "policy_version": "subject-pipeline-v1",
    }


def _normalize(raw: Dict[str, Any], verification_context: str = "") -> Dict[str, Any]:
    """Validate and sanitize the LLM JSON.

    - Decision must be in {GO, HOLD}; unknown values fall back to HOLD
      (safer than letting them through).
    - Confidence clipped to [0, 1] or set None.
    - Findings list bounded (the model occasionally floods).
    - REQ-WMS-* / TC-WMS-* identifiers cited by the model are
      cross-checked against `verification_context` (APCS bundle +
      commit diff stat). Unverified IDs get an inline tag so the
      reviewer cannot mistake them for grounded references.
    - Per-field length caps prevent runaway text.
    """
    try:
        decision = validate_choice(raw.get("decision"), ["GO", "HOLD"], "decision")
    except SanitizationError:
        # Soft fallback: the surrounding CI pipeline must always have a
        # decision; HOLD is the safe default when output is corrupt.
        decision = "HOLD"

    confidence = raw.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = None

    findings_raw = raw.get("findings", [])
    if not isinstance(findings_raw, list):
        findings_raw = []

    # Identifier verification — scan everything the model claimed.
    cited_blob = " ".join(
        str(raw.get(field) or "") for field in ("summary", "human_action")
    ) + " " + " ".join(
        " ".join(
            str((f or {}).get(field) or "")
            for field in ("rule", "detail", "status")
        )
        for f in findings_raw
        if isinstance(f, dict)
    )
    unverified = unverified_ids(cited_blob, verification_context)

    findings = []
    for f in findings_raw[:50]:
        if not isinstance(f, dict):
            continue
        findings.append(
            {
                "rule": cap_string(str(f.get("rule") or "Finding"), max_chars=200, label="rule"),
                "status": cap_string(str(f.get("status") or "INFO"), max_chars=20, label="status"),
                "detail": cap_string(
                    annotate_unverified(str(f.get("detail") or ""), unverified),
                    max_chars=2_000,
                    label="finding detail",
                ),
            }
        )

    summary = cap_string(
        annotate_unverified(str(raw.get("summary") or "No summary."), unverified),
        max_chars=2_000,
        label="summary",
    )
    human_action = cap_string(
        str(raw.get("human_action") or "Review the analysis and approve manually."),
        max_chars=1_000,
        label="human_action",
    )

    return {
        "decision": decision,
        "decision_type": "llm_synthesis",
        "confidence": confidence,
        "summary": summary,
        "human_action": human_action,
        "findings": findings,
        "reasons": [
            {
                "title": f.get("rule", "Finding"),
                "detail": f.get("detail", ""),
                "rule_code": f.get("rule", ""),
                "status": f.get("status", "INFO"),
            }
            for f in findings
        ],
        "policy_version": "subject-pipeline-v1",
    }
