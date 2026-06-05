"""
Deterministic Phase 7 production-deployment policy engine.

Policy objective:
- Recommend HOLD if any hard gate is violated.
- Recommend GO only when all hard gates pass and deployment is cleared.

Hard HOLD conditions:
1) Agent 6 GO decision missing
2) Nulla Osta (approval sign-off) incomplete
3) Outside deployment window
4) Rollback plan missing or not reviewed
5) Dependency version mismatch with production
6) Staging health checks failed
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .models import Decision, RuleCode, RuleFinding, RuleFindings, SourceRef
from .normalization import NormalizedPhase7Bundle


@dataclass(frozen=True)
class PolicyConfig:
    target_environment: str = "PRODUCTION"
    stabilization_window_seconds: int = 300


class Phase7PolicyEngine:
    """
    Deterministic rule engine for Phase 7 production deployment.

    Evaluates pre-deployment gates: A6 clearance, approvals, deployment window,
    rollback plan, dependency consistency, and staging health.
    """

    def __init__(self, config: Optional[PolicyConfig] = None) -> None:
        self.config = config or PolicyConfig()

    def evaluate(self, bundle: NormalizedPhase7Bundle) -> RuleFindings:
        r1_t, r1_reason, r1_evd = self._check_agent6_go(bundle)
        r2_t, r2_reason, r2_evd = self._check_nulla_osta(bundle)
        r3_t, r3_reason, r3_evd = self._check_deployment_window(bundle)
        r4_t, r4_reason, r4_evd = self._check_rollback_plan(bundle)
        r5_t, r5_reason, r5_evd = self._check_dependencies(bundle)
        r6_t, r6_reason, r6_evd = self._check_staging_health(bundle)

        findings: Tuple[RuleFinding, ...] = (
            RuleFinding(
                code=RuleCode.AGENT6_GO_MISSING,
                triggered=r1_t,
                reason=r1_reason,
                evidence=tuple(r1_evd),
            ),
            RuleFinding(
                code=RuleCode.NULLA_OSTA_INCOMPLETE,
                triggered=r2_t,
                reason=r2_reason,
                evidence=tuple(r2_evd),
            ),
            RuleFinding(
                code=RuleCode.DEPLOYMENT_WINDOW_VIOLATED,
                triggered=r3_t,
                reason=r3_reason,
                evidence=tuple(r3_evd),
            ),
            RuleFinding(
                code=RuleCode.ROLLBACK_PLAN_MISSING,
                triggered=r4_t,
                reason=r4_reason,
                evidence=tuple(r4_evd),
            ),
            RuleFinding(
                code=RuleCode.DEPENDENCY_MISMATCH,
                triggered=r5_t,
                reason=r5_reason,
                evidence=tuple(r5_evd),
            ),
            RuleFinding(
                code=RuleCode.STAGING_HEALTH_CHECK_FAILED,
                triggered=r6_t,
                reason=r6_reason,
                evidence=tuple(r6_evd),
            ),
        )

        return RuleFindings(
            agent6_go_missing=r1_t,
            nulla_osta_incomplete=r2_t,
            deployment_window_violated=r3_t,
            rollback_plan_missing=r4_t,
            dependency_mismatch=r5_t,
            staging_health_check_failed=r6_t,
            findings=findings,
        )

    def decide(self, bundle: NormalizedPhase7Bundle) -> Decision:
        return self.evaluate(bundle).decision

    # -------------------------------------------------------------------------
    # Rule checks
    # -------------------------------------------------------------------------

    def _check_agent6_go(
        self, bundle: NormalizedPhase7Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        Agent 6 must have issued GO and VDD must be complete.
        GO only if A6 decision == GO.
        In BrainOrchestrator mode (agent6_context present): requires GO.
        In standalone mode (agent6_context absent): passes — rely on other gates.
        """
        if bundle.agent6_context is None:
            return (
                False,
                "Agent 6 handoff absent; running in standalone mode — other gates apply.",
                [],
            )

        a6 = bundle.agent6_context
        if a6.decision != "GO":
            return (
                True,
                f"Agent 6 decision is {a6.decision}; GO required for production deployment.",
                [SourceRef(file_path="agent6_handoff:decision")],
            )

        if not a6.vdd_complete:
            return (
                True,
                "Agent 6 VDD draft is incomplete; GO cannot be issued without complete documentation.",
                [SourceRef(file_path="agent6_handoff:vdd_draft")],
            )

        return (
            False,
            "Agent 6 issued GO with complete VDD draft.",
            [SourceRef(file_path="agent6_handoff")],
        )

    def _check_nulla_osta(
        self, bundle: NormalizedPhase7Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        All required Nulla Osta sign-offs must be present.
        GO only if all required roles have signed.
        """
        missing: List[str] = []
        for item in bundle.approval_items:
            if item.required and not item.signed:
                missing.append(item.role)

        if missing:
            return (
                True,
                f"Required Nulla Osta sign-offs missing: {', '.join(sorted(missing))}.",
                [SourceRef(file_path="approval_workflow_manifest")],
            )

        return (
            False,
            "All required Nulla Osta sign-offs are present.",
            [SourceRef(file_path="approval_workflow_manifest")],
        )

    def _check_deployment_window(
        self, bundle: NormalizedPhase7Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        Deployment must be within the scheduled production deployment window.
        GO only if current time is within the window.
        """
        dw = bundle.deployment_window
        if dw is None:
            return (
                False,
                "No deployment window defined; deployment allowed at any time.",
                [SourceRef(file_path="deployment_manifest")],
            )

        if dw.is_active:
            return (
                False,
                f"Deployment window {dw.window_id} is active ({dw.start_utc} to {dw.end_utc}).",
                [SourceRef(file_path="deployment_manifest")],
            )

        return (
            True,
            f"Current time is outside deployment window {dw.window_id} ({dw.start_utc} to {dw.end_utc}).",
            [SourceRef(file_path="deployment_manifest")],
        )

    def _check_rollback_plan(
        self, bundle: NormalizedPhase7Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        A rollback plan must exist and be reviewed.
        GO only if rollback_plan_exists == True.
        """
        if bundle.rollback_plan_exists:
            return (
                False,
                "Rollback plan is present and reviewed.",
                [SourceRef(file_path="rollback_plan")],
            )

        return (
            True,
            "Rollback plan is missing or not reviewed.",
            [SourceRef(file_path="rollback_plan")],
        )

    def _check_dependencies(
        self, bundle: NormalizedPhase7Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        All production dependencies must match expected versions.
        GO only if all dependencies have match == True.
        """
        mismatches: List[str] = []
        for dep in bundle.dependencies:
            if not dep.match:
                expected = dep.expected_version
                actual = dep.actual_version or "unknown"
                mismatches.append(
                    f"{dep.service_name}: expected {expected}, got {actual}"
                )

        if mismatches:
            return (
                True,
                f"Dependency version mismatch detected: {'; '.join(mismatches)}.",
                [SourceRef(file_path="dependency_matrix")],
            )

        return (
            False,
            "All production dependency versions are consistent.",
            [SourceRef(file_path="dependency_matrix")],
        )

    def _check_staging_health(
        self, bundle: NormalizedPhase7Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        Pre-deployment staging health checks must pass.
        GO only if all required health probes return HEALTHY.
        """
        failures: List[str] = []
        for check in bundle.health_checks:
            if check.status.value != "healthy":
                failures.append(
                    f"{check.check_name}: {check.status.value}"
                    + (f" ({check.error_message})" if check.error_message else "")
                )

        if failures:
            return (
                True,
                f"Staging health check failures: {'; '.join(failures)}.",
                [SourceRef(file_path="staging_health_checks")],
            )

        return (
            False,
            "All staging health checks passed.",
            [SourceRef(file_path="staging_health_checks")],
        )


__all__ = [
    "PolicyConfig",
    "Phase7PolicyEngine",
]
