"""
Agent 4 core data models and output schema helpers.

This module defines:
- Canonical enums used across ingestion, normalization, rules, and output
- Dataclasses for normalized Phase 4 evidence
- Structured rule finding and recommendation models
- Output schema validation and serialization helpers

Design goals:
- Deterministic, auditable structure for hard readiness gates
- Stable JSON contract for downstream phases and UI/reporting
- Lightweight implementation with zero third-party dependencies
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


class Environment(str, Enum):
    DEV = "DEV"
    TEST = "TEST"
    STAGE = "STAGE"
    PROD = "PROD"


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EmailStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    CONDITIONAL_UNMET = "CONDITIONAL_UNMET"
    NONE = "NONE"


class RuleCode(str, Enum):
    CRITICAL_SERVICE_UNHEALTHY = "critical_service_unhealthy"
    UNRESOLVED_ERROR_OR_CRITICAL_LOG = "unresolved_error_or_critical_log"
    OPEN_BLOCKER_EMAIL = "open_blocker_email"
    MANDATORY_VERSION_MISMATCH = "mandatory_version_mismatch"
    UNMET_CONDITIONAL_REQUIREMENT = "unmet_conditional_requirement"


# ---------------------------------------------------------------------------
# Basic normalization helpers
# ---------------------------------------------------------------------------


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def normalize_module_name(name: str) -> str:
    """
    Canonicalize module names to lowercase-kebab style.

    Example:
    - "Monitoring Core" -> "monitoring-core"
    - "monitoring_core" -> "monitoring-core"
    """
    return "-".join(str(name).strip().replace("_", " ").split()).lower()


def parse_iso8601(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Source traceability model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRef:
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Normalized evidence models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequirementRecord:
    requirement_id: str
    description: str
    priority: str
    module: str
    mandatory_for_phase4: bool

    @staticmethod
    def from_dict(row: Dict[str, Any]) -> "RequirementRecord":
        return RequirementRecord(
            requirement_id=str(row.get("requirement_id", "")).strip(),
            description=str(row.get("description", "")).strip(),
            priority=str(row.get("priority", "")).strip().upper(),
            module=normalize_module_name(str(row.get("module", ""))),
            mandatory_for_phase4=normalize_bool(row.get("mandatory_for_phase4")),
        )


@dataclass(frozen=True)
class ModuleVersionRecord:
    scenario_id: str
    release_id: str
    environment: str
    module: str
    planned_version: str
    deployed_version: str
    mandatory_for_phase4: bool
    version_match: bool

    @staticmethod
    def from_dict(row: Dict[str, Any]) -> "ModuleVersionRecord":
        planned = str(row.get("planned_version", "")).strip()
        deployed = str(row.get("deployed_version", "")).strip()
        explicit_version_match = row.get("version_match")
        return ModuleVersionRecord(
            scenario_id=str(row.get("scenario_id", "")).strip(),
            release_id=str(row.get("release_id", "")).strip(),
            environment=str(row.get("environment", "DEV")).strip().upper(),
            module=normalize_module_name(str(row.get("module", ""))),
            planned_version=planned,
            deployed_version=deployed,
            mandatory_for_phase4=normalize_bool(row.get("mandatory_for_phase4")),
            version_match=(
                normalize_bool(explicit_version_match)
                if explicit_version_match is not None
                else planned == deployed
            ),
        )


@dataclass(frozen=True)
class LogEvent:
    timestamp: Optional[str]
    severity: Severity
    component: str
    message: str
    source: SourceRef

    @property
    def is_blocking(self) -> bool:
        return self.severity in {Severity.ERROR, Severity.CRITICAL}


@dataclass(frozen=True)
class ServiceStatus:
    service: str
    status: str
    critical: bool
    reason: str
    source: Optional[SourceRef] = None

    @property
    def unhealthy(self) -> bool:
        return self.status.strip().lower() != "healthy"


@dataclass(frozen=True)
class HealthReport:
    scenario_id: str
    release_id: str
    environment: str
    generated_at: Optional[str]
    overall_status: str
    services: Tuple[ServiceStatus, ...]
    source: Optional[SourceRef] = None

    @property
    def has_critical_unhealthy(self) -> bool:
        return any(s.critical and s.unhealthy for s in self.services)


@dataclass(frozen=True)
class EmailSignal:
    scenario_id: str
    release_id: str
    status: EmailStatus
    has_open_blocker: bool
    has_unmet_conditional: bool
    summary: str
    source: SourceRef


@dataclass(frozen=True)
class ScenarioInputBundle:
    scenario_id: str
    release_id: str
    environment: str
    requirements: Tuple[RequirementRecord, ...]
    module_versions: Tuple[ModuleVersionRecord, ...]
    log_events: Tuple[LogEvent, ...]
    health_report: HealthReport
    email_signal: EmailSignal
    raw_sources: Tuple[SourceRef, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Rule findings and decision output models
# ---------------------------------------------------------------------------


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
    has_unhealthy_service: bool = False
    has_critical_log_error: bool = False
    has_open_blocker_email: bool = False
    has_version_mismatch: bool = False
    has_unmet_condition: bool = False
    findings: Tuple[RuleFinding, ...] = field(default_factory=tuple)

    @property
    def hold_required(self) -> bool:
        return any(
            [
                self.has_unhealthy_service,
                self.has_critical_log_error,
                self.has_open_blocker_email,
                self.has_version_mismatch,
                self.has_unmet_condition,
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
            "has_unhealthy_service": self.has_unhealthy_service,
            "has_critical_log_error": self.has_critical_log_error,
            "has_open_blocker_email": self.has_open_blocker_email,
            "has_version_mismatch": self.has_version_mismatch,
            "has_unmet_condition": self.has_unmet_condition,
            "hold_required": self.hold_required,
            "decision": self.decision.value,
            "triggered_rule_codes": self.triggered_rule_codes,
            "findings": [f.to_dict() for f in self.findings],
        }


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
class Agent4Output:
    scenario_id: str
    release_id: str
    environment: str
    decision: Decision
    decision_type: DecisionType
    reasons: Tuple[ReasonItem, ...]
    evidence: Tuple[SourceRef, ...]
    confidence: Confidence
    human_action: str
    summary: str
    policy_version: str = "phase4-policy-v1"
    timestamp_utc: str = field(default_factory=utc_now_iso)
    rule_findings: Optional[RuleFindings] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "release_id": self.release_id,
            "environment": self.environment,
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
        return payload


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


REQUIRED_TOP_LEVEL_KEYS = {
    "scenario_id",
    "release_id",
    "environment",
    "decision",
    "decision_type",
    "reasons",
    "evidence",
    "confidence",
    "human_action",
    "summary",
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
    Lightweight output contract validation for Agent 4 API/CLI responses.
    """
    errors: List[str] = []

    missing = sorted(REQUIRED_TOP_LEVEL_KEYS - set(payload.keys()))
    if missing:
        errors.append(f"Missing required top-level keys: {', '.join(missing)}")

    if "decision" in payload and not _is_valid_decision(payload["decision"]):
        errors.append("Invalid decision. Expected one of: GO, HOLD")

    if "decision_type" in payload and not _is_valid_decision_type(
        payload["decision_type"]
    ):
        errors.append(
            "Invalid decision_type. Expected one of: "
            "deterministic, deterministic_with_llm_summary"
        )

    if "confidence" in payload and not _is_valid_confidence(payload["confidence"]):
        errors.append("Invalid confidence. Expected one of: high, medium, low")

    reasons = payload.get("reasons")
    if reasons is not None:
        if not isinstance(reasons, list):
            errors.append("Field 'reasons' must be a list")
        else:
            for i, item in enumerate(reasons):
                if not isinstance(item, dict):
                    errors.append(f"reasons[{i}] must be an object")
                    continue
                if "title" not in item or "detail" not in item:
                    errors.append(f"reasons[{i}] must contain 'title' and 'detail'")

    evidence = payload.get("evidence")
    if evidence is not None:
        if not isinstance(evidence, list):
            errors.append("Field 'evidence' must be a list")
        else:
            for i, item in enumerate(evidence):
                if not isinstance(item, dict):
                    errors.append(f"evidence[{i}] must be an object")
                    continue
                if "file_path" not in item:
                    errors.append(f"evidence[{i}] must contain 'file_path'")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Output construction helpers
# ---------------------------------------------------------------------------


def confidence_from_findings(
    findings: RuleFindings,
    has_non_blocking_warning: bool = False,
    evidence_conflict: bool = False,
    evidence_incomplete: bool = False,
) -> Confidence:
    """
    Confidence policy:
    - low: conflicting or incomplete evidence
    - high: no blockers and clean evidence OR blockers with clear aligned evidence
    - medium: non-blocking warnings present
    """
    if evidence_conflict or evidence_incomplete:
        return Confidence.LOW
    if has_non_blocking_warning:
        return Confidence.MEDIUM
    return Confidence.HIGH


def default_human_action(decision: Decision) -> str:
    if decision == Decision.HOLD:
        return "Do not promote DEV->TEST. Resolve blockers and re-run readiness assessment."
    return "Ready for human review to proceed with DEV->TEST promotion."


def build_agent4_output(
    scenario_id: str,
    release_id: str,
    environment: str,
    findings: RuleFindings,
    reasons: Sequence[ReasonItem],
    evidence: Sequence[SourceRef],
    summary: str,
    decision_type: DecisionType = DecisionType.DETERMINISTIC_WITH_LLM_SUMMARY,
    confidence: Optional[Confidence] = None,
    human_action: Optional[str] = None,
    policy_version: str = "phase4-policy-v1",
) -> Agent4Output:
    decision = findings.decision
    resolved_confidence = confidence or confidence_from_findings(findings)
    resolved_human_action = human_action or default_human_action(decision)

    return Agent4Output(
        scenario_id=scenario_id,
        release_id=release_id,
        environment=environment.upper(),
        decision=decision,
        decision_type=decision_type,
        reasons=tuple(reasons),
        evidence=tuple(evidence),
        confidence=resolved_confidence,
        human_action=resolved_human_action,
        summary=summary.strip(),
        policy_version=policy_version,
        rule_findings=findings,
    )
