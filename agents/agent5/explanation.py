"""
Agent 5 explanation layer.

This module provides:
1) deterministic explanation generation from Phase 5 rule findings
2) optional LLM-assisted narrative refinement that cannot override policy gates

Design constraint:
- GO/HOLD is always determined by deterministic policy findings.
- LLM output is advisory text only (summary, reason phrasing, human action wording).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import (
    Agent5Output,
    Confidence,
    Decision,
    DecisionType,
    ReasonItem,
    RuleFindings,
    SourceRef,
    build_agent5_output,
    confidence_from_findings,
    default_human_action,
)


class ExplanationError(Exception):
    """Raised when explanation generation fails in a non-recoverable way."""


@dataclass(frozen=True)
class ExplanationContext:
    scenario_id: str
    release_id: str
    findings: RuleFindings
    evidence_conflict: bool = False
    evidence_incomplete: bool = False
    policy_version: str = "phase5-policy-v1"
    missing_artifacts: Tuple[str, ...] = tuple()
    cross_phase_continuity_flags: Optional[Dict[str, Any]] = None


def _dedupe_evidence(evidence: Iterable[SourceRef]) -> Tuple[SourceRef, ...]:
    seen = set()
    out: List[SourceRef] = []
    for ref in evidence:
        key = (ref.file_path, ref.line_start, ref.line_end, ref.snippet)
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return tuple(out)


def _title_from_rule_code(code: str) -> str:
    return code.replace("_", " ").title()


def _reasons_from_findings(findings: RuleFindings) -> Tuple[ReasonItem, ...]:
    reasons: List[ReasonItem] = []

    for finding in findings.findings:
        if finding.triggered:
            reasons.append(
                ReasonItem(
                    title=_title_from_rule_code(finding.code.value),
                    detail=finding.reason,
                    rule_code=finding.code.value,
                    evidence=tuple(finding.evidence),
                )
            )

    if not reasons:
        reasons.append(
            ReasonItem(
                title="All hard release gates passed",
                detail=(
                    "No mandatory requirement coverage gaps, failed/blocked mandatory outcomes, "
                    "open critical/high defects, mandatory evidence incompleteness, unmet retest "
                    "conditions, or unresolved Agent 4 continuity blockers were detected."
                ),
                rule_code=None,
                evidence=tuple(),
            )
        )

    return tuple(reasons)


def _summary_from_findings(findings: RuleFindings) -> str:
    if findings.decision == Decision.HOLD:
        triggered = findings.triggered_rule_codes
        if triggered:
            return (
                "HOLD recommended because one or more hard test-analysis gates were triggered: "
                + ", ".join(triggered)
                + "."
            )
        return "HOLD recommended due to policy findings indicating unresolved test-analysis risk."
    return "GO recommended because no hard test-analysis gate was triggered in the available evidence."


def _collect_evidence(findings: RuleFindings) -> Tuple[SourceRef, ...]:
    refs: List[SourceRef] = []
    for f in findings.findings:
        refs.extend(list(f.evidence))
    return _dedupe_evidence(refs)


def _reason_evidence_coverage(reasons: Sequence[ReasonItem]) -> float:
    if not reasons:
        return 0.0
    covered = 0
    for r in reasons:
        if r.evidence:
            covered += 1
    return round(covered / len(reasons), 4)


def build_deterministic_explanation(context: ExplanationContext) -> Agent5Output:
    reasons = _reasons_from_findings(context.findings)
    evidence = _collect_evidence(context.findings)
    summary = _summary_from_findings(context.findings)

    confidence = confidence_from_findings(
        context.findings,
        evidence_conflict=context.evidence_conflict,
        evidence_incomplete=context.evidence_incomplete,
    )

    coverage = {
        "reason_evidence_coverage": _reason_evidence_coverage(reasons),
        "triggered_rules_count": len(context.findings.triggered_rule_codes),
    }

    if context.missing_artifacts:
        coverage["missing_artifacts_count"] = len(context.missing_artifacts)

    human_action = default_human_action(context.findings.decision)

    return build_agent5_output(
        scenario_id=context.scenario_id,
        release_id=context.release_id,
        findings=context.findings,
        reasons=reasons,
        evidence=evidence,
        summary=summary,
        decision_type=DecisionType.DETERMINISTIC,
        confidence=confidence,
        human_action=human_action,
        policy_version=context.policy_version,
        coverage_metrics=coverage,
        missing_artifacts=list(context.missing_artifacts),
        cross_phase_continuity_flags=context.cross_phase_continuity_flags,
    )


def _build_llm_prompt(
    context: ExplanationContext,
    reasons: Sequence[ReasonItem],
    evidence: Sequence[SourceRef],
    deterministic_summary: str,
) -> str:
    payload = {
        "task": "Refine readability of a Phase 5 release-test-analysis explanation. Do not change decision.",
        "policy_constraints": {
            "decision_is_locked": context.findings.decision.value,
            "triggered_rules": context.findings.triggered_rule_codes,
            "must_not_override_hard_gates": True,
            "must_not_invent_evidence": True,
            "must_not_change_rule_codes": True,
        },
        "input": {
            "scenario_id": context.scenario_id,
            "release_id": context.release_id,
            "deterministic_summary": deterministic_summary,
            "reasons": [
                {"title": r.title, "detail": r.detail, "rule_code": r.rule_code}
                for r in reasons
            ],
            "evidence_refs": [
                {
                    "file_path": e.file_path,
                    "line_start": e.line_start,
                    "line_end": e.line_end,
                    "snippet": e.snippet,
                }
                for e in evidence
            ],
            "cross_phase_continuity_flags": context.cross_phase_continuity_flags or {},
            "missing_artifacts": list(context.missing_artifacts),
        },
        "output_schema": {
            "summary": "string",
            "human_action": "string",
            "reasons": [
                {"title": "string", "detail": "string", "rule_code": "string|null"}
            ],
            "confidence": "high|medium|low (optional)",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _parse_llm_response(raw: str) -> Dict[str, Any]:
    # Strict JSON first.
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fallback: extract first JSON object if wrapped in prose.
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ExplanationError("LLM response is not a valid JSON object.")


def _confidence_from_text(
    value: Optional[str], default_value: Confidence
) -> Confidence:
    if not value:
        return default_value
    v = value.strip().lower()
    if v == Confidence.HIGH.value:
        return Confidence.HIGH
    if v == Confidence.MEDIUM.value:
        return Confidence.MEDIUM
    if v == Confidence.LOW.value:
        return Confidence.LOW
    return default_value


def _merge_reason_text(
    deterministic_reasons: Sequence[ReasonItem],
    llm_reasons: Any,
) -> Tuple[ReasonItem, ...]:
    """
    Conservative merge strategy:
    - keep deterministic reason count and rule_code mapping
    - allow LLM to refine title/detail text only
    """
    if not isinstance(llm_reasons, list):
        return tuple(deterministic_reasons)

    merged: List[ReasonItem] = []
    for idx, base in enumerate(deterministic_reasons):
        if idx >= len(llm_reasons) or not isinstance(llm_reasons[idx], dict):
            merged.append(base)
            continue

        item = llm_reasons[idx]
        title = str(item.get("title", base.title)).strip() or base.title
        detail = str(item.get("detail", base.detail)).strip() or base.detail

        merged.append(
            ReasonItem(
                title=title,
                detail=detail,
                rule_code=base.rule_code,
                evidence=base.evidence,
            )
        )
    return tuple(merged)


def build_explanation_with_optional_llm(
    context: ExplanationContext,
    llm_generate: Optional[Callable[[str], str]] = None,
) -> Agent5Output:
    """
    Build Agent 5 recommendation with deterministic policy and optional LLM phrasing.

    `llm_generate` contract:
        Callable[[prompt: str], str]

    The callable should return JSON text containing any of:
    - summary: string
    - human_action: string
    - reasons: list[{title, detail, rule_code?}]
    - confidence: high|medium|low
    """
    deterministic = build_deterministic_explanation(context)

    if llm_generate is None:
        return deterministic

    prompt = _build_llm_prompt(
        context=context,
        reasons=deterministic.reasons,
        evidence=deterministic.evidence,
        deterministic_summary=deterministic.summary,
    )

    try:
        raw = llm_generate(prompt)
        parsed = _parse_llm_response(raw)

        merged_reasons = _merge_reason_text(
            deterministic.reasons, parsed.get("reasons")
        )
        summary = (
            str(parsed.get("summary", deterministic.summary)).strip()
            or deterministic.summary
        )
        human_action = (
            str(parsed.get("human_action", deterministic.human_action)).strip()
            or deterministic.human_action
        )

        base_conf = deterministic.confidence
        llm_conf = _confidence_from_text(parsed.get("confidence"), base_conf)

        # Conservative confidence merge: allow downgrade, not optimistic upgrade.
        order = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
        final_confidence = llm_conf if order[llm_conf] < order[base_conf] else base_conf

        return build_agent5_output(
            scenario_id=context.scenario_id,
            release_id=context.release_id,
            findings=context.findings,
            reasons=merged_reasons,
            evidence=deterministic.evidence,
            summary=summary,
            decision_type=DecisionType.DETERMINISTIC_WITH_LLM_SUMMARY,
            confidence=final_confidence,
            human_action=human_action,
            policy_version=context.policy_version,
            coverage_metrics=deterministic.coverage_metrics,
            missing_artifacts=deterministic.missing_artifacts,
            cross_phase_continuity_flags=deterministic.cross_phase_continuity_flags,
        )
    except Exception:
        # Fallback safety: never fail readiness decision because explanation failed.
        return deterministic


__all__ = [
    "ExplanationError",
    "ExplanationContext",
    "build_deterministic_explanation",
    "build_explanation_with_optional_llm",
]
