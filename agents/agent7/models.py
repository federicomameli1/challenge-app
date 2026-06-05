"""
Agent 7 core data models and output schema helpers.

This module defines:
- Canonical enums for Phase 7 production-deployment decisions
- Dataclasses for rule findings, deployment state, health checks, and live monitoring
- Schema validation for machine-consumable deployment responses

Design goals:
- Deterministic and auditable GO/HOLD outcomes
- Stable output contract for deployment automation
- Live monitoring state for real-time health tracking
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Decision(str, Enum):
    GO = "GO"
    HOLD = "HOLD"


class DecisionType(str, Enum):
    DETERMINISTIC = "deterministic"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RuleCode(str, Enum):
    AGENT6_GO_MISSING = "agent6_go_missing"
    NULLA_OSTA_INCOMPLETE = "nulla_osta_incomplete"
    DEPLOYMENT_WINDOW_VIOLATED = "deployment_window_violated"
    ROLLBACK_PLAN_MISSING = "rollback_plan_missing"
    DEPENDENCY_MISMATCH = "dependency_mismatch"
    STAGING_HEALTH_CHECK_FAILED = "staging_health_check_failed"


class DeploymentStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    STABILIZING = "stabilizing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class HealthProbeStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_human_action(decision: Decision) -> str:
    if decision == Decision.HOLD:
        return (
            "Do not proceed with production deployment. "
            "Resolve triggered findings before the deployment gate."
        )
    return "Ready for production deployment. Proceed with rollout and live monitoring."


# ---------------------------------------------------------------------------
# Evidence
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
# Rule Findings
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
    agent6_go_missing: bool = False
    nulla_osta_incomplete: bool = False
    deployment_window_violated: bool = False
    rollback_plan_missing: bool = False
    dependency_mismatch: bool = False
    staging_health_check_failed: bool = False
    findings: Tuple[RuleFinding, ...] = field(default_factory=tuple)

    @property
    def hold_required(self) -> bool:
        return any([
            self.agent6_go_missing,
            self.nulla_osta_incomplete,
            self.deployment_window_violated,
            self.rollback_plan_missing,
            self.dependency_mismatch,
            self.staging_health_check_failed,
        ])

    @property
    def decision(self) -> Decision:
        return Decision.HOLD if self.hold_required else Decision.GO

    @property
    def triggered_rule_codes(self) -> List[str]:
        return [f.code.value for f in self.findings if f.triggered]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent6_go_missing": self.agent6_go_missing,
            "nulla_osta_incomplete": self.nulla_osta_incomplete,
            "deployment_window_violated": self.deployment_window_violated,
            "rollback_plan_missing": self.rollback_plan_missing,
            "dependency_mismatch": self.dependency_mismatch,
            "staging_health_check_failed": self.staging_health_check_failed,
            "hold_required": self.hold_required,
            "decision": self.decision.value,
            "triggered_rule_codes": self.triggered_rule_codes,
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Health Checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthProbeResult:
    probe_name: str
    status: HealthProbeStatus
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    checked_at_utc: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "probe_name": self.probe_name,
            "status": self.status.value,
            "response_time_ms": self.response_time_ms,
            "error_message": self.error_message,
            "checked_at_utc": self.checked_at_utc,
        }


@dataclass(frozen=True)
class MonitoringSnapshot:
    timestamp_utc: str = field(default_factory=utc_now_iso)
    overall_status: HealthProbeStatus = HealthProbeStatus.UNKNOWN
    probe_results: Tuple[HealthProbeResult, ...] = field(default_factory=tuple)
    error_rate_percent: Optional[float] = None
    p99_latency_ms: Optional[float] = None
    active_instances: Optional[int] = None
    deployed_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "overall_status": self.overall_status.value,
            "probe_results": [p.to_dict() for p in self.probe_results],
            "error_rate_percent": self.error_rate_percent,
            "p99_latency_ms": self.p99_latency_ms,
            "active_instances": self.active_instances,
            "deployed_version": self.deployed_version,
        }


@dataclass(frozen=True)
class MonitoringState:
    deployment_status: DeploymentStatus = DeploymentStatus.NOT_STARTED
    snapshots: Tuple[MonitoringSnapshot, ...] = field(default_factory=tuple)
    stabilization_start_utc: Optional[str] = None
    stabilization_end_utc: Optional[str] = None
    stability_achieved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deployment_status": self.deployment_status.value,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "stabilization_start_utc": self.stabilization_start_utc,
            "stabilization_end_utc": self.stabilization_end_utc,
            "stability_achieved": self.stability_achieved,
        }


# ---------------------------------------------------------------------------
# Deployment Record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeploymentRecord:
    scenario_id: str
    release_id: str
    version: str
    deployed_at_utc: str = field(default_factory=utc_now_iso)
    deployment_status: DeploymentStatus = DeploymentStatus.NOT_STARTED
    monitoring: Optional[MonitoringState] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "release_id": self.release_id,
            "version": self.version,
            "deployed_at_utc": self.deployed_at_utc,
            "deployment_status": self.deployment_status.value,
            "monitoring": self.monitoring.to_dict() if self.monitoring else None,
        }


# ---------------------------------------------------------------------------
# Reason Items
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
# Agent 7 Output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Agent7Output:
    scenario_id: str
    release_id: str
    decision: Decision
    decision_type: DecisionType
    reasons: Tuple[ReasonItem, ...]
    evidence: Tuple[SourceRef, ...]
    confidence: Confidence
    human_action: str
    summary: str
    policy_version: str = "phase7-policy-v1"
    timestamp_utc: str = field(default_factory=utc_now_iso)
    rule_findings: Optional[RuleFindings] = None
    deployment_record: Optional[DeploymentRecord] = None
    monitoring_state: Optional[MonitoringState] = None

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
        if self.deployment_record is not None:
            payload["deployment_record"] = self.deployment_record.to_dict()
        if self.monitoring_state is not None:
            payload["monitoring_state"] = self.monitoring_state.to_dict()

        return payload


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


def validate_output_schema(payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    missing = sorted(REQUIRED_TOP_LEVEL_KEYS - set(payload.keys()))
    if missing:
        errors.append("Missing required top-level keys: " + ", ".join(missing))

    if "decision" in payload:
        v = str(payload.get("decision"))
        if v not in {Decision.GO.value, Decision.HOLD.value}:
            errors.append("Invalid decision. Expected GO or HOLD.")

    reasons = payload.get("reasons")
    if reasons is not None and not isinstance(reasons, list):
        errors.append("`reasons` must be a list.")
    elif isinstance(reasons, list):
        for idx, r in enumerate(reasons):
            if isinstance(r, dict):
                if "title" not in r or "detail" not in r:
                    errors.append(f"reasons[{idx}] missing required keys `title` or `detail`.")

    evidence = payload.get("evidence")
    if evidence is not None and not isinstance(evidence, list):
        errors.append("`evidence` must be a list.")

    return len(errors) == 0, errors


__all__ = [
    "Decision",
    "DecisionType",
    "Confidence",
    "RuleCode",
    "DeploymentStatus",
    "HealthProbeStatus",
    "SourceRef",
    "RuleFinding",
    "RuleFindings",
    "HealthProbeResult",
    "MonitoringSnapshot",
    "MonitoringState",
    "DeploymentRecord",
    "ReasonItem",
    "Agent7Output",
    "utc_now_iso",
    "default_human_action",
    "validate_output_schema",
]
