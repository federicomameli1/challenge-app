"""
Agent 7 normalization layer and derived policy flags.

This module converts raw ingestion artifacts (A6 handoff and Phase 7
deployment artifacts) into canonical structures and computes deterministic
rule-input flags for the Phase 7 policy engine.

Design goals:
- Keep policy inputs deterministic and auditable
- Preserve source traceability for deployment data
- Gracefully handle absent handoffs while surfacing readiness gaps
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from .models import DeploymentStatus, HealthProbeStatus, SourceRef

# ---------------------------------------------------------------------------
# Normalized records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedAgent6Context:
    decision: str
    triggered_rules: Tuple[str, ...]
    release_id: Optional[str]
    scenario_id: str
    vdd_complete: bool
    all_approvals_signed: bool
    source: SourceRef


@dataclass(frozen=True)
class NormalizedDeploymentWindow:
    window_id: str
    start_utc: str
    end_utc: str
    environment: str
    is_active: bool
    source: SourceRef


@dataclass(frozen=True)
class NormalizedHealthCheck:
    check_name: str
    status: HealthProbeStatus
    response_time_ms: Optional[float]
    error_message: Optional[str]
    checked_at_utc: str
    source: SourceRef


@dataclass(frozen=True)
class NormalizedDependency:
    service_name: str
    expected_version: str
    actual_version: Optional[str]
    match: bool
    source: SourceRef


@dataclass(frozen=True)
class NormalizedApprovalItem:
    role: str
    required: bool
    signed: bool
    signed_by: Optional[str]
    source: SourceRef


@dataclass(frozen=True)
class NormalizedPhase7Bundle:
    scenario_id: str
    release_id: Optional[str]
    environment: str = "PRODUCTION"

    # Cross-phase context from Agent 6
    agent6_context: Optional[NormalizedAgent6Context] = None

    # Phase 7 artifacts
    deployment_window: Optional[NormalizedDeploymentWindow] = None
    health_checks: Tuple[NormalizedHealthCheck, ...] = field(default_factory=tuple)
    dependencies: Tuple[NormalizedDependency, ...] = field(default_factory=tuple)
    rollback_plan_exists: bool = False
    approval_items: Tuple[NormalizedApprovalItem, ...] = field(default_factory=tuple)

    # Module versions for cross-phase consistency
    module_versions: Mapping[str, str] = field(default_factory=dict)

    # Derived policy flags
    agent6_go_missing: bool = False
    nulla_osta_incomplete: bool = False
    deployment_window_violated: bool = False
    rollback_plan_missing: bool = False
    dependency_mismatch: bool = False
    staging_health_check_failed: bool = False

    # Continuity notes for audit
    continuity_notes: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "release_id": self.release_id,
            "environment": self.environment,
            "agent6_context": (
                self.agent6_context.__dict__ if self.agent6_context else None
            ),
            "deployment_window": (
                self.deployment_window.__dict__ if self.deployment_window else None
            ),
            "health_checks": [
                {**h.__dict__, "source": h.source.to_dict()}
                for h in self.health_checks
            ],
            "dependencies": [
                {**d.__dict__, "source": d.source.to_dict()}
                for d in self.dependencies
            ],
            "rollback_plan_exists": self.rollback_plan_exists,
            "approval_items": [
                {**a.__dict__, "source": a.source.to_dict()}
                for a in self.approval_items
            ],
            "module_versions": dict(self.module_versions),
            "derived_flags": {
                "agent6_go_missing": self.agent6_go_missing,
                "nulla_osta_incomplete": self.nulla_osta_incomplete,
                "deployment_window_violated": self.deployment_window_violated,
                "rollback_plan_missing": self.rollback_plan_missing,
                "dependency_mismatch": self.dependency_mismatch,
                "staging_health_check_failed": self.staging_health_check_failed,
            },
        }


__all__ = [
    "NormalizedAgent6Context",
    "NormalizedDeploymentWindow",
    "NormalizedHealthCheck",
    "NormalizedDependency",
    "NormalizedApprovalItem",
    "NormalizedPhase7Bundle",
    "normalize_phase7_bundle",
]


def normalize_phase7_bundle(raw: "RawPhase7Bundle") -> NormalizedPhase7Bundle:
    """
    Convert raw Phase 7 artifacts into a normalized policy bundle.

    Computes derived flags and continuity notes for auditability.
    """
    from .ingestion import RawPhase7Bundle

    if not isinstance(raw, RawPhase7Bundle):
        raise ValueError("normalize_phase7_bundle requires RawPhase7Bundle")

    bundle = NormalizedPhase7Bundle(
        scenario_id=raw.scenario_id,
        release_id=raw.release_id,
        environment=raw.environment,
    )

    # Agent 6 context from handoff
    if raw.agent6_handoff:
        payload = raw.agent6_handoff
        decision = str(payload.get("decision", "")).strip().upper() or "UNKNOWN"
        triggered = []
        rf = payload.get("rule_findings", {})
        if isinstance(rf, dict):
            codes = rf.get("triggered_rule_codes", [])
            triggered = [str(c) for c in codes if c]

        vdd = payload.get("vdd_draft") or {}
        sections = vdd.get("sections", [])
        vdd_complete = all(
            s.get("present") and s.get("populated")
            for s in sections
        ) if sections else False

        approval_manifest = payload.get("approval_checklist", payload.get("vdd_draft", {}).get("approval_checklist", {}))
        all_signed = approval_manifest.get("all_signed", False) if isinstance(approval_manifest, dict) else False

        bundle = NormalizedPhase7Bundle(
            scenario_id=raw.scenario_id,
            release_id=raw.release_id,
            environment=raw.environment,
            agent6_context=NormalizedAgent6Context(
                decision=decision,
                triggered_rules=tuple(triggered),
                release_id=str(raw.release_id or "").strip() or None,
                scenario_id=raw.scenario_id,
                vdd_complete=vdd_complete,
                all_approvals_signed=all_signed,
                source=SourceRef(file_path="agent6_handoff"),
            ),
        )

    # Deployment window
    dm = raw.deployment_manifest
    dw = raw.production_calendar
    if dw or dm:
        window_id = str((dw or dm).get("window_id", raw.scenario_id))
        start_str = (dw or dm).get("window_start", "")
        end_str = (dw or dm).get("window_end", "")
        env = (dw or dm).get("environment", "PRODUCTION")
        is_active = _is_within_window(start_str, end_str)

        bundle = NormalizedPhase7Bundle(
            scenario_id=bundle.scenario_id,
            release_id=bundle.release_id,
            environment=bundle.environment,
            agent6_context=bundle.agent6_context,
            deployment_window=NormalizedDeploymentWindow(
                window_id=window_id,
                start_utc=start_str,
                end_utc=end_str,
                environment=env,
                is_active=is_active,
                source=SourceRef(file_path="deployment_manifest"),
            ),
        )

    # Health checks
    health_checks = []
    for row in raw.staging_health_checks:
        status_str = str(row.get("status", "unknown")).strip().lower()
        status = HealthProbeStatus(status_str) if status_str in ("healthy", "degraded", "unhealthy", "unknown") else HealthProbeStatus.UNKNOWN
        response_ms = _parse_float(row.get("response_time_ms"))
        health_checks.append(NormalizedHealthCheck(
            check_name=str(row.get("check_name", "unknown")).strip(),
            status=status,
            response_time_ms=response_ms,
            error_message=str(row.get("error_message", "")).strip() or None,
            checked_at_utc=str(row.get("checked_at_utc", _utc_now())).strip(),
            source=SourceRef(file_path="staging_health_checks"),
        ))
    health_checks = tuple(health_checks)

    # Dependencies
    dependencies = []
    for row in raw.dependencies:
        expected = str(row.get("expected_version", "")).strip()
        actual = str(row.get("actual_version", "")).strip()
        match = (actual == expected) if actual and expected else True
        dependencies.append(NormalizedDependency(
            service_name=str(row.get("service_name", "")).strip(),
            expected_version=expected,
            actual_version=actual or None,
            match=match,
            source=SourceRef(file_path="dependency_matrix"),
        ))
    dependencies = tuple(dependencies)

    # Approval items
    approval_items = []
    for row in raw.approval_items:
        signed_str = str(row.get("signed", "")).strip().lower()
        required_str = str(row.get("required", "")).strip().lower()
        signed = signed_str in ("true", "1", "yes", "signed")
        required = required_str not in ("false", "0", "no", "")
        approval_items.append(NormalizedApprovalItem(
            role=str(row.get("role", "")).strip(),
            required=required,
            signed=signed,
            signed_by=str(row.get("signed_by", "")).strip() or None,
            source=SourceRef(file_path="approval_workflow_manifest"),
        ))
    approval_items = tuple(approval_items)

    # Rollback plan
    rollback_plan_exists = raw.rollback_plan is not None and bool(raw.rollback_plan)

    # Derived flags
    agent6_go_missing = bundle.agent6_context is None or bundle.agent6_context.decision != "GO"
    nulla_osta_incomplete = any(item.required and not item.signed for item in approval_items)
    deployment_window_violated = (
        (bundle.deployment_window is not None) and
        (not bundle.deployment_window.is_active)
    )
    rollback_plan_missing = not rollback_plan_exists
    dependency_mismatch = any(not d.match for d in dependencies)
    staging_health_check_failed = any(
        h.status == HealthProbeStatus.UNHEALTHY for h in health_checks
    )

    # Continuity notes
    notes: List[str] = []
    if agent6_go_missing:
        notes.append("agent6_go_missing")
    if nulla_osta_incomplete:
        notes.append("nulla_osta_incomplete")
    if deployment_window_violated:
        notes.append("deployment_window_violated")
    if rollback_plan_missing:
        notes.append("rollback_plan_missing")
    if dependency_mismatch:
        notes.append("dependency_mismatch")
    if staging_health_check_failed:
        notes.append("staging_health_check_failed")

    return NormalizedPhase7Bundle(
        scenario_id=raw.scenario_id,
        release_id=raw.release_id,
        environment=raw.environment,
        agent6_context=bundle.agent6_context,
        deployment_window=bundle.deployment_window,
        health_checks=health_checks,
        dependencies=dependencies,
        rollback_plan_exists=rollback_plan_exists,
        approval_items=approval_items,
        module_versions=dict(bundle.module_versions),
        agent6_go_missing=agent6_go_missing,
        nulla_osta_incomplete=nulla_osta_incomplete,
        deployment_window_violated=deployment_window_violated,
        rollback_plan_missing=rollback_plan_missing,
        dependency_mismatch=dependency_mismatch,
        staging_health_check_failed=staging_health_check_failed,
        continuity_notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def _is_within_window(start_str: str, end_str: str) -> bool:
    if not start_str or not end_str:
        return True  # No window defined = always allowed
    try:
        start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return start <= now <= end
    except (ValueError, TypeError):
        return True  # Parse error = allow (don't block on malformed date)