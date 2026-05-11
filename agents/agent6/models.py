"""
Agent 6 core data models and output schema helpers.

This module defines:
- Canonical enums for Phase 6 release-documentation & approvals decisions
- Dataclasses for rule findings, reasons, evidence, VDD draft, and final output
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
    CROSS_PHASE_VERSION_MISMATCH = "cross_phase_version_mismatch"
    AGENT5_CRITICAL_DEFECT_OPEN = "agent5_critical_defect_open"
    AGENT4_BLOCKER_UNCONFIRMED = "agent4_blocker_unconfirmed"
    REQUIREMENTS_COVERAGE_GAP = "requirements_coverage_gap"
    VDD_INCOMPLETE = "vdd_incomplete"
    MISSING_APPROVAL_TRIGGER = "missing_approval_trigger"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_human_action(decision: Decision) -> str:
    if decision == Decision.HOLD:
        return (
            "Do not proceed past Phase 6 release-documentation gate. "
            "Resolve triggered findings, complete VDD sections, and obtain required approvals."
        )
    return "Ready for human review to proceed past Phase 6 gate toward production deployment."


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
    cross_phase_version_mismatch: bool = False
    agent5_critical_defect_open: bool = False
    agent4_blocker_unconfirmed: bool = False
    requirements_coverage_gap: bool = False
    vdd_incomplete: bool = False
    missing_approval_trigger: bool = False
    findings: Tuple[RuleFinding, ...] = field(default_factory=tuple)

    @property
    def hold_required(self) -> bool:
        return any([
            self.cross_phase_version_mismatch,
            self.agent5_critical_defect_open,
            self.agent4_blocker_unconfirmed,
            self.requirements_coverage_gap,
            self.vdd_incomplete,
            self.missing_approval_trigger,
        ])

    @property
    def decision(self) -> Decision:
        return Decision.HOLD if self.hold_required else Decision.GO

    @property
    def triggered_rule_codes(self) -> List[str]:
        return [f.code.value for f in self.findings if f.triggered]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cross_phase_version_mismatch": self.cross_phase_version_mismatch,
            "agent5_critical_defect_open": self.agent5_critical_defect_open,
            "agent4_blocker_unconfirmed": self.agent4_blocker_unconfirmed,
            "requirements_coverage_gap": self.requirements_coverage_gap,
            "vdd_incomplete": self.vdd_incomplete,
            "missing_approval_trigger": self.missing_approval_trigger,
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
    if evidence_conflict or evidence_incomplete:
        return Confidence.LOW
    if findings.decision == Decision.HOLD:
        return Confidence.MEDIUM
    return Confidence.HIGH


# ---------------------------------------------------------------------------
# Reason + Evidence Items
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# VDD Draft Sections
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VDDSection:
    name: str
    present: bool
    populated: bool
    evidence_refs: Tuple[SourceRef, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "present": self.present,
            "populated": self.populated,
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
        }


@dataclass(frozen=True)
class ModuleInventoryEntry:
    module: str
    planned_version: str
    deployed_version: str
    tested_version: str
    source: SourceRef

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "planned_version": self.planned_version,
            "deployed_version": self.deployed_version,
            "tested_version": self.tested_version,
            "source": self.source.to_dict(),
        }


@dataclass(frozen=True)
class VDDDraft:
    release_summary: str
    scope: Tuple[str, ...]
    module_inventory: Tuple[ModuleInventoryEntry, ...]
    requirements_coverage: Dict[str, Any]
    test_evidence_summary: str
    open_issues: Tuple[str, ...]
    change_log: str
    approval_checklist: Dict[str, Any]
    sections: Tuple[VDDSection, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "release_summary": self.release_summary,
            "scope": list(self.scope),
            "module_inventory": [e.to_dict() for e in self.module_inventory],
            "requirements_coverage": dict(self.requirements_coverage),
            "test_evidence_summary": self.test_evidence_summary,
            "open_issues": list(self.open_issues),
            "change_log": self.change_log,
            "approval_checklist": dict(self.approval_checklist),
            "sections": [s.to_dict() for s in self.sections],
        }


# ---------------------------------------------------------------------------
# Consistency Audit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsistencyAudit:
    version_conflicts: Tuple[str, ...]
    traceability_gaps: Tuple[str, ...]
    approval_gaps: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_conflicts": list(self.version_conflicts),
            "traceability_gaps": list(self.traceability_gaps),
            "approval_gaps": list(self.approval_gaps),
        }


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalItem:
    role: str
    required: bool
    signed: bool
    signed_by: Optional[str] = None
    signed_at_utc: Optional[str] = None
    source: SourceRef = field(default_factory=lambda: SourceRef(file_path="unknown"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "required": self.required,
            "signed": self.signed,
            "signed_by": self.signed_by,
            "signed_at_utc": self.signed_at_utc,
            "source": self.source.to_dict(),
        }


@dataclass(frozen=True)
class NotificationDraft:
    recipient_role: str
    subject: str
    body: str
    priority: str = "normal"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recipient_role": self.recipient_role,
            "subject": self.subject,
            "body": self.body,
            "priority": self.priority,
        }


# ---------------------------------------------------------------------------
# Agent 6 Output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Agent6Output:
    scenario_id: str
    release_id: str
    decision: Decision
    decision_type: DecisionType
    reasons: Tuple[ReasonItem, ...]
    evidence: Tuple[SourceRef, ...]
    confidence: Confidence
    human_action: str
    summary: str
    policy_version: str = "phase6-policy-v1"
    timestamp_utc: str = field(default_factory=utc_now_iso)
    rule_findings: Optional[RuleFindings] = None
    vdd_draft: Optional[VDDDraft] = None
    consistency_audit: Optional[ConsistencyAudit] = None
    notification_drafts: Tuple[NotificationDraft, ...] = field(default_factory=tuple)
    missing_artifacts: Optional[List[str]] = None
    cross_phase_context: Optional[Dict[str, Any]] = None

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
        if self.vdd_draft is not None:
            payload["vdd_draft"] = self.vdd_draft.to_dict()
        if self.consistency_audit is not None:
            payload["consistency_audit"] = self.consistency_audit.to_dict()
        if self.notification_drafts:
            payload["notification_drafts"] = [n.to_dict() for n in self.notification_drafts]
        if self.missing_artifacts is not None:
            payload["missing_artifacts"] = list(self.missing_artifacts)
        if self.cross_phase_context is not None:
            payload["cross_phase_context"] = dict(self.cross_phase_context)

        return payload


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_agent6_output(
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
    policy_version: str = "phase6-policy-v1",
    vdd_draft: Optional[VDDDraft] = None,
    consistency_audit: Optional[ConsistencyAudit] = None,
    notification_drafts: Sequence[NotificationDraft] = (),
    missing_artifacts: Optional[List[str]] = None,
    cross_phase_context: Optional[Dict[str, Any]] = None,
) -> Agent6Output:
    decision = findings.decision
    final_confidence = confidence or confidence_from_findings(findings)
    action = human_action or default_human_action(decision)

    return Agent6Output(
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
        vdd_draft=vdd_draft,
        consistency_audit=consistency_audit,
        notification_drafts=tuple(notification_drafts),
        missing_artifacts=missing_artifacts,
        cross_phase_context=cross_phase_context,
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
                    "reasons[{0}] missing required keys `title` or `detail`.".format(idx)
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
    "VDDSection",
    "ModuleInventoryEntry",
    "VDDDraft",
    "ConsistencyAudit",
    "ApprovalItem",
    "NotificationDraft",
    "Agent6Output",
    "utc_now_iso",
    "default_human_action",
    "confidence_from_findings",
    "build_agent6_output",
    "validate_output_schema",
]
