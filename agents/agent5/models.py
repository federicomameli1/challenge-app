"""
Agent 5 core data models and output schema helpers.

This module defines:
- Canonical enums for Phase 5 test-analysis decisions
- Dataclasses for rule findings, reasons, evidence, and final output
- Lightweight schema validation for machine-consumable responses

Design goals:
- Deterministic and auditable GO/HOLD outcomes
- Stable output contract for evaluation and downstream automation
- Zero third-party dependencies
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Decision(str, Enum):
    GO = "GO"
    HOLD = "HOLD"


class DecisionType(str, Enum):
    DETERMINISTIC = "deterministic"
    DETERMINISTIC_WITH_LLM_SUMMARY = "deterministic_with_llm_summary"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RuleCode(str, Enum):
    MANDATORY_REQUIREMENT_UNCOVERED = "mandatory_requirement_uncovered"
    MANDATORY_REQUIREMENT_FAILED_OR_BLOCKED = "mandatory_requirement_failed_or_blocked"
    CRITICAL_DEFECT_OPEN = "critical_defect_open"
    TEST_EVIDENCE_INCOMPLETE = "test_evidence_incomplete"
    CONDITIONAL_RETEST_UNMET = "conditional_retest_unmet"
    AGENT4_UNRESOLVED_HARD_BLOCKER_UNCLOSED = "agent4_unresolved_hard_blocker_unclosed"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_human_action(decision: Decision) -> str:
    if decision == Decision.HOLD:
        return (
            "Do not proceed past Phase 5 test-analysis gate. "
            "Resolve triggered findings and re-run assessment."
        )
    return "Ready for human review to proceed past Phase 5 gate."


def _to_confidence(value: str, fallback: Confidence = Confidence.MEDIUM) -> Confidence:
    v = (value or "").strip().lower()
    if v == Confidence.HIGH.value:
        return Confidence.HIGH
    if v == Confidence.MEDIUM.value:
        return Confidence.MEDIUM
    if v == Confidence.LOW.value:
        return Confidence.LOW
    return fallback


# ---------------------------------------------------------------------------
# Evidence + Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRef:
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuleFinding:
    code: RuleCode
    triggered: bool
    reason: str
    evidence: Tuple[SourceRef, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.value,
            "triggered": self.triggered,
            "reason": self.reason,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass(frozen=True)
class RuleFindings:
    mandatory_requirement_uncovered: bool = False
    mandatory_requirement_failed_or_blocked: bool = False
    critical_defect_open: bool = False
    test_evidence_incomplete: bool = False
    conditional_retest_unmet: bool = False
    agent4_unresolved_hard_blocker_unclosed: bool = False
    findings: Tuple[RuleFinding, ...] = field(default_factory=tuple)

    @property
    def hold_required(self) -> bool:
        return any(
            [
                self.mandatory_requirement_uncovered,
                self.mandatory_requirement_failed_or_blocked,
                self.critical_defect_open,
                self.test_evidence_incomplete,
                self.conditional_retest_unmet,
                self.agent4_unresolved_hard_blocker_unclosed,
            ]
        )

    @property
    def decision(self) -> Decision:
        return Decision.HOLD if self.hold_required else Decision.GO

    @property
    def triggered_rule_codes(self) -> List[str]:
        return [f.code.value for f in self.findings if f.triggered]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mandatory_requirement_uncovered": self.mandatory_requirement_uncovered,
            "mandatory_requirement_failed_or_blocked": self.mandatory_requirement_failed_or_blocked,
            "critical_defect_open": self.critical_defect_open,
            "test_evidence_incomplete": self.test_evidence_incomplete,
            "conditional_retest_unmet": self.conditional_retest_unmet,
            "agent4_unresolved_hard_blocker_unclosed": self.agent4_unresolved_hard_blocker_unclosed,
            "hold_required": self.hold_required,
            "decision": self.decision.value,
            "triggered_rule_codes": self.triggered_rule_codes,
            "findings": [f.to_dict() for f in self.findings],
        }


def confidence_from_findings(
    findings: RuleFindings,
    *,
    evidence_conflict: bool = False,
    evidence_incomplete: bool = False,
) -> Confidence:
    """
    Conservative confidence heuristic:
    - low when evidence is conflicting/incomplete
    - medium for HOLD with clear triggered gates
    - high for GO with no red flags
    """
    if evidence_conflict or evidence_incomplete:
        return Confidence.LOW
    if findings.decision == Decision.HOLD:
        return Confidence.MEDIUM
    return Confidence.HIGH


@dataclass(frozen=True)
class ReasonItem:
    title: str
    detail: str
    rule_code: Optional[str] = None
    evidence: Tuple[SourceRef, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "detail": self.detail,
            "rule_code": self.rule_code,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass(frozen=True)
class Agent5Output:
    scenario_id: str
    release_id: str
    decision: Decision
    decision_type: DecisionType
    reasons: Tuple[ReasonItem, ...]
    evidence: Tuple[SourceRef, ...]
    confidence: Confidence
    human_action: str
    summary: str
    policy_version: str = "phase5-policy-v1"
    timestamp_utc: str = field(default_factory=utc_now_iso)
    rule_findings: Optional[RuleFindings] = None
    coverage_metrics: Optional[Dict[str, Any]] = None
    missing_artifacts: Optional[List[str]] = None
    cross_phase_continuity_flags: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "scenario_id": self.scenario_id,
            "release_id": self.release_id,
            "decision": self.decision.value,
            "decision_type": self.decision_type.value,
            "reasons": [r.to_dict() for r in self.reasons],
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence.value,
            "human_action": self.human_action,
            "summary": self.summary,
            "policy_version": self.policy_version,
            "timestamp_utc": self.timestamp_utc,
        }

        if self.rule_findings is not None:
            payload["rule_findings"] = self.rule_findings.to_dict()
        if self.coverage_metrics is not None:
            payload["coverage_metrics"] = dict(self.coverage_metrics)
        if self.missing_artifacts is not None:
            payload["missing_artifacts"] = list(self.missing_artifacts)
        if self.cross_phase_continuity_flags is not None:
            payload["cross_phase_continuity_flags"] = dict(
                self.cross_phase_continuity_flags
            )

        return payload


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_agent5_output(
    *,
    scenario_id: str,
    release_id: str,
    findings: RuleFindings,
    reasons: Sequence[ReasonItem],
    evidence: Sequence[SourceRef],
    summary: str,
    decision_type: DecisionType = DecisionType.DETERMINISTIC,
    confidence: Optional[Confidence] = None,
    human_action: Optional[str] = None,
    policy_version: str = "phase5-policy-v1",
    coverage_metrics: Optional[Dict[str, Any]] = None,
    missing_artifacts: Optional[List[str]] = None,
    cross_phase_continuity_flags: Optional[Dict[str, Any]] = None,
) -> Agent5Output:
    decision = findings.decision
    final_confidence = confidence or confidence_from_findings(findings)
    action = human_action or default_human_action(decision)

    return Agent5Output(
        scenario_id=scenario_id,
        release_id=release_id,
        decision=decision,
        decision_type=decision_type,
        reasons=tuple(reasons),
        evidence=tuple(evidence),
        confidence=final_confidence,
        human_action=action,
        summary=summary.strip(),
        policy_version=policy_version,
        rule_findings=findings,
        coverage_metrics=coverage_metrics,
        missing_artifacts=missing_artifacts,
        cross_phase_continuity_flags=cross_phase_continuity_flags,
    )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


REQUIRED_TOP_LEVEL_KEYS = {
    "scenario_id",
    "release_id",
    "decision",
    "decision_type",
    "reasons",
    "evidence",
    "confidence",
    "human_action",
    "summary",
    "policy_version",
    "timestamp_utc",
    "rule_findings",
}


def _is_valid_decision(value: Any) -> bool:
    return str(value) in {Decision.GO.value, Decision.HOLD.value}


def _is_valid_decision_type(value: Any) -> bool:
    return str(value) in {
        DecisionType.DETERMINISTIC.value,
        DecisionType.DETERMINISTIC_WITH_LLM_SUMMARY.value,
    }


def _is_valid_confidence(value: Any) -> bool:
    return str(value) in {
        Confidence.HIGH.value,
        Confidence.MEDIUM.value,
        Confidence.LOW.value,
    }


def validate_output_schema(payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Lightweight output contract validator for Agent 5 responses.
    """
    errors: List[str] = []

    missing = sorted(REQUIRED_TOP_LEVEL_KEYS - set(payload.keys()))
    if missing:
        errors.append("Missing required top-level keys: " + ", ".join(missing))

    if "decision" in payload and not _is_valid_decision(payload.get("decision")):
        errors.append("Invalid decision. Expected GO or HOLD.")

    if "decision_type" in payload and not _is_valid_decision_type(
        payload.get("decision_type")
    ):
        errors.append(
            "Invalid decision_type. Expected deterministic or deterministic_with_llm_summary."
        )

    if "confidence" in payload and not _is_valid_confidence(payload.get("confidence")):
        errors.append("Invalid confidence. Expected high|medium|low.")

    reasons = payload.get("reasons")
    if reasons is not None and not isinstance(reasons, list):
        errors.append("`reasons` must be a list.")
    elif isinstance(reasons, list):
        for idx, r in enumerate(reasons):
            if not isinstance(r, dict):
                errors.append("reasons[{0}] must be an object.".format(idx))
                continue
            if "title" not in r or "detail" not in r:
                errors.append(
                    "reasons[{0}] missing required keys `title` or `detail`.".format(
                        idx
                    )
                )

    evidence = payload.get("evidence")
    if evidence is not None and not isinstance(evidence, list):
        errors.append("`evidence` must be a list.")
    elif isinstance(evidence, list):
        for idx, e in enumerate(evidence):
            if not isinstance(e, dict):
                errors.append("evidence[{0}] must be an object.".format(idx))
                continue
            if "file_path" not in e:
                errors.append(
                    "evidence[{0}] missing required key `file_path`.".format(idx)
                )

    rule_findings = payload.get("rule_findings")
    if rule_findings is not None and not isinstance(rule_findings, dict):
        errors.append("`rule_findings` must be an object.")

    return len(errors) == 0, errors


__all__ = [
    "Decision",
    "DecisionType",
    "Confidence",
    "RuleCode",
    "SourceRef",
    "RuleFinding",
    "RuleFindings",
    "ReasonItem",
    "Agent5Output",
    "utc_now_iso",
    "default_human_action",
    "confidence_from_findings",
    "build_agent5_output",
    "validate_output_schema",
]
