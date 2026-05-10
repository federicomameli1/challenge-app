"""
LLM-based APCS bundle analyst.

Sends the five APCS documents to an LLM (via OpenRouterClient) and asks
it to produce a structured GO / HOLD release-readiness decision.

Design constraints:
- The LLM decision is ADVISORY only. It does not replace the deterministic
  policy engines in agent4/policy.py and agent5/policy.py.
- Output schema is compatible with the existing agent pipeline so that
  run_ci_analysis.py and the dashboard can consume it without changes.
- Token budget is managed conservatively: each document is truncated before
  being sent to avoid exceeding free-tier context windows (~8K tokens).

Usage:
    from agents.llm_agent import LLMBundleAgent
    from agents.llm_client import OpenRouterClient

    client = OpenRouterClient.from_env()
    agent = LLMBundleAgent(client)
    result = agent.analyze(bundle, subject_repo="owner/repo", ref="abc123")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .llm_client import LLMError, OpenRouterClient

logger = logging.getLogger(__name__)

# Max characters per APCS document sent to the LLM.
# At ~4 chars/token this is ~1 500 tokens per doc, ~7 500 total for 5 docs.
# Leaves headroom for system prompt + response on free-tier models (8K ctx).
_MAX_DOC_CHARS = 6_000

_SYSTEM_PROMPT = """\
You are a release-readiness analyst for a railway safety system.
You will receive an APCS (Automated Pipeline Control System) release bundle \
containing five documents: Requirements, Module Version Inventory, Test Procedure, \
Version Description Document (VDD), and an email thread.

Your task is to evaluate whether the candidate release is ready to be promoted \
from the DEV environment to the TEST environment.

Rules:
1. A [MUST] requirement that is clearly unmet → HOLD.
2. An open unresolved BLOCKER in the email thread → HOLD.
3. A mandatory module version mismatch or missing test result → HOLD.
4. [SHOULD] misses are soft warnings, never a HOLD on their own.
5. If all MUST requirements appear satisfied → GO.

Respond ONLY with a valid JSON object, no markdown fences, no extra text:
{
  "decision": "GO" or "HOLD",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence>",
  "findings": [
    {"rule": "<REQ-id or free text>", "status": "PASS" or "FAIL" or "WARN", "detail": "<short text>"}
  ],
  "human_action": "<what the operator should do next>"
}
"""


class LLMBundleAgent:
    """
    Analyzes an APCS document bundle using an LLM and returns a
    structured decision compatible with the existing agent output schema.
    """

    def __init__(self, client: OpenRouterClient) -> None:
        self.client = client

    def analyze(
        self,
        bundle: Dict[str, str],
        *,
        subject_repo: str = "",
        ref: str = "",
    ) -> Dict[str, Any]:
        """
        Analyze the APCS bundle and return a structured result dict.

        Returns a fallback HOLD with an error note if the LLM call fails,
        so the pipeline always gets a usable result.
        """
        if not bundle:
            return _error_result("APCS bundle is empty — no documents to analyze.")

        user_message = self._build_user_message(bundle, subject_repo=subject_repo, ref=ref)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            raw = self.client.complete_json(messages, max_tokens=800)
            return _normalize_result(raw)
        except LLMError as exc:
            logger.error("LLM call failed: %s", exc)
            return _error_result(f"LLM call failed: {exc}")

    def _build_user_message(
        self,
        bundle: Dict[str, str],
        *,
        subject_repo: str,
        ref: str,
    ) -> str:
        parts = []
        if subject_repo:
            parts.append(f"Subject repository: {subject_repo}")
        if ref:
            parts.append(f"Commit ref: {ref[:12]}")
        parts.append("")

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


def _normalize_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce the LLM response into the expected output schema."""
    decision = str(raw.get("decision", "HOLD")).upper()
    if decision not in ("GO", "HOLD"):
        decision = "HOLD"

    confidence = raw.get("confidence")
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = None

    findings = raw.get("findings", [])
    if not isinstance(findings, list):
        findings = []

    return {
        "decision": decision,
        "decision_type": "llm_bundle_analysis",
        "confidence": confidence,
        "summary": str(raw.get("summary", "No summary provided.")),
        "human_action": str(raw.get("human_action", "Review the LLM analysis and approve manually.")),
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
        "policy_version": "llm-v1",
    }


def _error_result(message: str) -> Dict[str, Any]:
    return {
        "decision": "HOLD",
        "decision_type": "llm_error",
        "confidence": None,
        "summary": message,
        "human_action": "LLM analysis unavailable — review the APCS bundle manually.",
        "findings": [],
        "reasons": [{"title": "LLM error", "detail": message, "rule_code": "", "status": "FAIL"}],
        "policy_version": "llm-v1",
    }
