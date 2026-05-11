"""
Deterministic Phase 6 release-documentation & approvals policy engine.

Policy objective:
- Recommend HOLD if any hard gate is violated.
- Recommend GO only when all hard gates pass.

Hard HOLD conditions:
1) Cross-phase version mismatch (A4 deployed ≠ A5 tested)
2) Agent 5 critical/high defect remains open
3) Agent 4 unresolved blocker not confirmed closed
4) Requirements coverage gap exists
5) VDD draft is incomplete
6) Required approval sign-off is missing
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .models import Decision, RuleCode, RuleFinding, RuleFindings, SourceRef
from .normalization import NormalizedPhase6Bundle


@dataclass(frozen=True)
class PolicyConfig:
    target_environment: str = "RELEASE"
    min_requirements_coverage_ratio: float = 1.0
    vdd_completeness_threshold: float = 1.0


class Phase6PolicyEngine:
    """
    Deterministic rule engine for Phase 6 release-documentation & approvals.

    Evaluates cross-phase consistency (A4 vs A5), VDD completeness,
    and approval readiness. All gates are hard -- GO only when all pass.
    """

    def __init__(self, config: Optional[PolicyConfig] = None) -> None:
        self.config = config or PolicyConfig()

    def evaluate(
        self,
        bundle: NormalizedPhase6Bundle,
        *,
        environment: Optional[str] = None,
    ) -> RuleFindings:
        _ = (environment or bundle.environment or "RELEASE").upper()

        r1_t, r1_reason, r1_evd = self._check_cross_phase_version_consistency(bundle)
        r2_t, r2_reason, r2_evd = self._check_agent5_critical_defect_open(bundle)
        r3_t, r3_reason, r3_evd = self._check_agent4_blocker_confirmed(bundle)
        r4_t, r4_reason, r4_evd = self._check_requirements_coverage(bundle)
        r5_t, r5_reason, r5_evd = self._check_vdd_completeness(bundle)
        r6_t, r6_reason, r6_evd = self._check_missing_approval_triggers(bundle)

        findings: Tuple[RuleFinding, ...] = (
            RuleFinding(
                code=RuleCode.CROSS_PHASE_VERSION_MISMATCH,
                triggered=r1_t,
                reason=r1_reason,
                evidence=tuple(r1_evd),
            ),
            RuleFinding(
                code=RuleCode.AGENT5_CRITICAL_DEFECT_OPEN,
                triggered=r2_t,
                reason=r2_reason,
                evidence=tuple(r2_evd),
            ),
            RuleFinding(
                code=RuleCode.AGENT4_BLOCKER_UNCONFIRMED,
                triggered=r3_t,
                reason=r3_reason,
                evidence=tuple(r3_evd),
            ),
            RuleFinding(
                code=RuleCode.REQUIREMENTS_COVERAGE_GAP,
                triggered=r4_t,
                reason=r4_reason,
                evidence=tuple(r4_evd),
            ),
            RuleFinding(
                code=RuleCode.VDD_INCOMPLETE,
                triggered=r5_t,
                reason=r5_reason,
                evidence=tuple(r5_evd),
            ),
            RuleFinding(
                code=RuleCode.MISSING_APPROVAL_TRIGGER,
                triggered=r6_t,
                reason=r6_reason,
                evidence=tuple(r6_evd),
            ),
        )

        return RuleFindings(
            cross_phase_version_mismatch=r1_t,
            agent5_critical_defect_open=r2_t,
            agent4_blocker_unconfirmed=r3_t,
            requirements_coverage_gap=r4_t,
            vdd_incomplete=r5_t,
            missing_approval_trigger=r6_t,
            findings=findings,
        )

    def decide(
        self,
        bundle: NormalizedPhase6Bundle,
        *,
        environment: Optional[str] = None,
    ) -> Decision:
        """
        Convenience wrapper returning only GO/HOLD decision.
        """
        return self.evaluate(bundle, environment=environment).decision

    # ---------------------------------------------------------------------
    # Rule checks
    # ---------------------------------------------------------------------

    def _check_cross_phase_version_consistency(
        self, bundle: NormalizedPhase6Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        A4 says "module X version Y was deployed to DEV".
        A5 says "module X version Z was tested in TEST".
        GO if Y == Z or module not tracked in A5 (deemed not tested).
        HOLD if Y != Z.
        """
        if bundle.cross_phase_version_mismatch:
            conflicts: List[str] = []
            for note in bundle.continuity_notes:
                if note.startswith("version_mismatch:") or note.startswith("module_not_in_a5_evidence:"):
                    conflicts.append(note)
            detail = "; ".join(conflicts) if conflicts else "cross-phase version mismatch detected"
            return (
                True,
                "Cross-phase version mismatch detected: {0}.".format(detail),
                [SourceRef(file_path="agent4_handoff"), SourceRef(file_path="agent5_handoff")],
            )
        return (
            False,
            "Cross-phase version consistency confirmed.",
            [SourceRef(file_path="agent4_handoff"), SourceRef(file_path="agent5_handoff")],
        )

    def _check_agent5_critical_defect_open(
        self, bundle: NormalizedPhase6Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        A5 flagged critical/high defects as open.
        Phase 6 must not override that finding.
        GO only if A5's critical_defect_open is False.
        """
        if not bundle.agent5_context:
            return (
                True,
                "Agent 5 handoff absent; cannot confirm critical defect closure.",
                [],
            )

        if bundle.agent5_critical_defect_open:
            ids = bundle.agent5_context.open_critical_defect_ids
            if ids:
                id_str = ", ".join(sorted(ids))
                return (
                    True,
                    "Agent 5 critical/high defect open: {0}.".format(id_str),
                    [SourceRef(file_path="agent5_handoff:defect_register")],
                )
            return (
                True,
                "Agent 5 critical/high defect open.",
                [SourceRef(file_path="agent5_handoff")],
            )

        return (
            False,
            "No open critical/high defects confirmed by Agent 5.",
            [SourceRef(file_path="agent5_handoff")],
        )

    def _check_agent4_blocker_confirmed(
        self, bundle: NormalizedPhase6Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        A4 had unresolved blockers (HOLD or open_blocker_email flag).
        Phase 6 requires explicit closure evidence in the cross-phase record
        (A5 confirmed or Phase 6 approval sign-off exists).
        """
        if not bundle.agent4_context:
            return (
                True,
                "Agent 4 handoff absent; cannot verify blocker resolution.",
                [],
            )

        a4 = bundle.agent4_context

        # If A4 was clean (GO, no blockers), pass
        if a4.decision == "GO" and not a4.open_blocker_detected:
            return (
                False,
                "Agent 4 issued GO with no open blocker; no confirmation needed.",
                [SourceRef(file_path="agent4_handoff")],
            )

        # A4 had blockers -- require A5 or Phase 6 approval closure
        a5_confirmed = (
            bundle.agent5_context.agent4_closure_confirmed
            if bundle.agent5_context
            else False
        )
        vdd_confirmed = any(item.signed for item in bundle.approval_items)

        if a5_confirmed or vdd_confirmed:
            return (
                False,
                "Agent 4 blockers confirmed closed via A5 continuity or Phase 6 approval sign-off.",
                [SourceRef(file_path="agent4_handoff"), SourceRef(file_path="agent5_handoff")],
            )

        # Fallback: if A4 had HOLD, and A5 unresolved conditions are now empty,
        # and Phase 6 approval items are all signed, treat as confirmed.
        if a4.decision == "HOLD":
            a5_unresolved = (
                bundle.agent5_context.agent4_unresolved_conditions
                if bundle.agent5_context
                else ()
            )
            a5_all_resolved = not a5_unresolved
            if a5_all_resolved and vdd_confirmed:
                return (
                    False,
                    "Agent 4 blockers resolved: A5 confirms all unresolved conditions addressed.",
                    [SourceRef(file_path="agent4_handoff"), SourceRef(file_path="agent5_handoff")],
                )

        unresolved = list(a4.unresolved_conditions) if a4.unresolved_conditions else []
        detail = "; ".join(unresolved) if unresolved else "open_blocker_email"
        return (
            True,
            "Agent 4 blockers not confirmed closed in Phase 6 context: {0}.".format(detail),
            [SourceRef(file_path="agent4_handoff"), SourceRef(file_path="agent5_handoff")],
        )

    def _check_requirements_coverage(
        self, bundle: NormalizedPhase6Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        A5 reported requirements coverage ratio.
        Phase 6 applies a configurable minimum threshold (default 1.0 = 100%).
        """
        if not bundle.agent5_context:
            return (
                True,
                "Agent 5 handoff absent; cannot verify requirements coverage.",
                [],
            )

        ratio = bundle.agent5_context.requirements_coverage_ratio
        threshold = self.config.min_requirements_coverage_ratio

        if ratio is None:
            return (
                False,
                "No requirements coverage ratio available from Agent 5; cannot flag gap.",
                [SourceRef(file_path="agent5_handoff")],
            )

        if ratio >= threshold:
            return (
                False,
                "Requirements coverage at {0:.1%} meets threshold {1:.1%}.".format(ratio, threshold),
                [SourceRef(file_path="agent5_handoff:coverage_metrics")],
            )

        return (
            True,
            "Requirements coverage at {0:.1%} below Phase 6 threshold {1:.1%}.".format(ratio, threshold),
            [SourceRef(file_path="agent5_handoff:coverage_metrics")],
        )

    def _check_vdd_completeness(
        self, bundle: NormalizedPhase6Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        VDD completeness check.
        Phase 6 verifies all required VDD sections are populated.
        If bundle.vdd_incomplete is True, a VDD section is missing.
        """
        if bundle.vdd_incomplete:
            return (
                True,
                "VDD draft is incomplete: required sections missing or empty.",
                [SourceRef(file_path="vdd_draft")],
            )

        return (
            False,
            "VDD draft is complete with all required sections populated.",
            [SourceRef(file_path="vdd_draft")],
        )

    def _check_missing_approval_triggers(
        self, bundle: NormalizedPhase6Bundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        """
        Required approval sign-offs must be present.
        Phase 6 checks approval items for required-but-unsigned roles.
        """
        missing_roles: List[str] = []
        for item in bundle.approval_items:
            if item.required and not item.signed:
                missing_roles.append(item.role)

        if missing_roles:
            roles_str = ", ".join(sorted(set(missing_roles)))
            return (
                True,
                "Conditional approval missing sign-off: roles requiring sign-off: {0}.".format(roles_str),
                [SourceRef(file_path="approval_workflow_manifest")],
            )

        return (
            False,
            "All required approval sign-offs are present.",
            [SourceRef(file_path="approval_workflow_manifest")],
        )


def evaluate_phase6_readiness(
    bundle: NormalizedPhase6Bundle,
    *,
    environment: Optional[str] = None,
    config: Optional[PolicyConfig] = None,
) -> RuleFindings:
    """
    Convenience functional API for one-shot Phase 6 policy evaluation.
    """
    return Phase6PolicyEngine(config=config).evaluate(bundle, environment=environment)


__all__ = [
    "PolicyConfig",
    "Phase6PolicyEngine",
    "evaluate_phase6_readiness",
]
