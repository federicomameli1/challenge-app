"""
Deterministic Phase 5 test-analysis policy engine.

Policy objective:
- Recommend HOLD if any hard gate is violated.
- Recommend GO only when all hard gates pass.

Hard HOLD conditions:
1) Mandatory requirement lacks executed mapped test evidence
2) Mandatory requirement has failed/blocked effective test outcome
3) Critical/high defect remains open
4) Required test evidence package is incomplete for mandatory scope
5) Conditional/retest requirement is unmet
6) Agent 4 unresolved hard blockers are not explicitly closed in Phase 5 evidence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .models import Decision, RuleCode, RuleFinding, RuleFindings, SourceRef
from .normalization import NormalizedEvidenceBundle


@dataclass(frozen=True)
class PolicyConfig:
    """
    Configuration for deterministic Phase 5 policy checks.
    """

    target_environment: str = "TEST"


class Phase5PolicyEngine:
    """
    Deterministic rule engine for Phase 5 test-analysis readiness.

    This engine evaluates normalized evidence and returns structured findings
    that are stable and auditable across runs.
    """

    def __init__(self, config: Optional[PolicyConfig] = None) -> None:
        self.config = config or PolicyConfig()

    def evaluate(
        self,
        bundle: NormalizedEvidenceBundle,
        *,
        environment: Optional[str] = None,
    ) -> RuleFindings:
        """
        Evaluate deterministic Phase 5 policy checks.

        Args:
            bundle: Normalized Phase 5 evidence bundle.
            environment: Optional explicit environment override.

        Returns:
            RuleFindings with per-rule trigger status, reasons, and evidence.
        """
        _ = (environment or bundle.environment or "TEST").upper()

        r1_t, r1_reason, r1_evd = self._check_mandatory_requirement_uncovered(bundle)
        r2_t, r2_reason, r2_evd = self._check_mandatory_requirement_failed_or_blocked(
            bundle
        )
        r3_t, r3_reason, r3_evd = self._check_critical_defect_open(bundle)
        r4_t, r4_reason, r4_evd = self._check_test_evidence_incomplete(bundle)
        r5_t, r5_reason, r5_evd = self._check_conditional_retest_unmet(bundle)
        r6_t, r6_reason, r6_evd = self._check_agent4_unresolved_unclosed(bundle)

        findings: Tuple[RuleFinding, ...] = (
            RuleFinding(
                code=RuleCode.MANDATORY_REQUIREMENT_UNCOVERED,
                triggered=r1_t,
                reason=r1_reason,
                evidence=tuple(r1_evd),
            ),
            RuleFinding(
                code=RuleCode.MANDATORY_REQUIREMENT_FAILED_OR_BLOCKED,
                triggered=r2_t,
                reason=r2_reason,
                evidence=tuple(r2_evd),
            ),
            RuleFinding(
                code=RuleCode.CRITICAL_DEFECT_OPEN,
                triggered=r3_t,
                reason=r3_reason,
                evidence=tuple(r3_evd),
            ),
            RuleFinding(
                code=RuleCode.TEST_EVIDENCE_INCOMPLETE,
                triggered=r4_t,
                reason=r4_reason,
                evidence=tuple(r4_evd),
            ),
            RuleFinding(
                code=RuleCode.CONDITIONAL_RETEST_UNMET,
                triggered=r5_t,
                reason=r5_reason,
                evidence=tuple(r5_evd),
            ),
            RuleFinding(
                code=RuleCode.AGENT4_UNRESOLVED_HARD_BLOCKER_UNCLOSED,
                triggered=r6_t,
                reason=r6_reason,
                evidence=tuple(r6_evd),
            ),
        )

        return RuleFindings(
            mandatory_requirement_uncovered=r1_t,
            mandatory_requirement_failed_or_blocked=r2_t,
            critical_defect_open=r3_t,
            test_evidence_incomplete=r4_t,
            conditional_retest_unmet=r5_t,
            agent4_unresolved_hard_blocker_unclosed=r6_t,
            findings=findings,
        )

    def decide(
        self,
        bundle: NormalizedEvidenceBundle,
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

    def _check_mandatory_requirement_uncovered(
        self,
        bundle: NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        triggered = bool(bundle.mandatory_requirement_uncovered)
        evidence = self._dedupe_refs(
            [
                self._first_req_source(bundle),
                self._first_trace_source(bundle),
                self._first_exec_source(bundle),
            ]
        )

        if triggered:
            return (
                True,
                "One or more mandatory requirements are not fully covered by executed mapped tests.",
                evidence,
            )

        return (
            False,
            "All mandatory requirements are covered by executed mapped tests.",
            evidence,
        )

    def _check_mandatory_requirement_failed_or_blocked(
        self,
        bundle: NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        triggered = bool(bundle.mandatory_requirement_failed_or_blocked)

        failed_or_blocked_refs: List[SourceRef] = []
        for ex in bundle.executions:
            if ex.failed or ex.blocked:
                failed_or_blocked_refs.append(ex.source)
        evidence = self._dedupe_refs(
            failed_or_blocked_refs or [self._first_exec_source(bundle)]
        )

        if triggered:
            return (
                True,
                "At least one mandatory requirement has failed or blocked effective test outcome.",
                evidence,
            )

        return (
            False,
            "No failed/blocked effective test outcome was found for mandatory requirements.",
            evidence,
        )

    def _check_critical_defect_open(
        self,
        bundle: NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        open_critical_or_high = [
            d for d in bundle.defects if d.is_open and d.is_critical_or_high
        ]
        triggered = bool(bundle.critical_defect_open or open_critical_or_high)

        evidence = self._dedupe_refs([d.source for d in open_critical_or_high])
        if not evidence:
            evidence = self._dedupe_refs([self._first_defect_source(bundle)])

        if triggered:
            ids = ", ".join(sorted({d.defect_id for d in open_critical_or_high}))
            if ids:
                reason = "Open critical/high defects remain unresolved: {0}.".format(
                    ids
                )
            else:
                reason = "Open critical/high defects remain unresolved."
            return (True, reason, evidence)

        return (
            False,
            "No open critical/high defects were found.",
            evidence,
        )

    def _check_test_evidence_incomplete(
        self,
        bundle: NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        triggered = bool(bundle.test_evidence_incomplete)

        evidence = self._dedupe_refs(
            [
                self._first_req_source(bundle),
                self._first_test_case_source(bundle),
                self._first_trace_source(bundle),
                self._first_exec_source(bundle),
                self._first_defect_source(bundle),
            ]
        )

        if triggered:
            if bundle.incompleteness_reasons:
                reason = (
                    "Required test evidence package is incomplete for mandatory scope: "
                    + ", ".join(bundle.incompleteness_reasons)
                    + "."
                )
            else:
                reason = (
                    "Required test evidence package is incomplete for mandatory scope."
                )
            return (True, reason, evidence)

        return (
            False,
            "Required test evidence package is complete for mandatory scope.",
            evidence,
        )

    def _check_conditional_retest_unmet(
        self,
        bundle: NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        triggered = bool(bundle.conditional_retest_unmet)

        unmet_refs: List[SourceRef] = []
        for ex in bundle.executions:
            if ex.retest_required and not ex.retest_completed:
                unmet_refs.append(ex.source)
            elif ex.status == "CONDITIONAL_UNMET":
                unmet_refs.append(ex.source)

        evidence = self._dedupe_refs(unmet_refs or [self._first_exec_source(bundle)])

        if triggered:
            return (
                True,
                "Conditional or retest requirement is unmet.",
                evidence,
            )

        return (
            False,
            "No unmet conditional or retest requirement was detected.",
            evidence,
        )

    def _check_agent4_unresolved_unclosed(
        self,
        bundle: NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[SourceRef]]:
        triggered = bool(bundle.agent4_unresolved_hard_blocker_unclosed)

        refs: List[SourceRef] = []
        if bundle.agent4_context is not None:
            refs.append(bundle.agent4_context.source)
        evidence = self._dedupe_refs(refs)

        if triggered:
            if bundle.continuity_notes:
                reason = (
                    "Agent 4 unresolved hard blockers are not explicitly closed in Phase 5 evidence: "
                    + ", ".join(bundle.continuity_notes)
                    + "."
                )
            else:
                reason = "Agent 4 unresolved hard blockers are not explicitly closed in Phase 5 evidence."
            return (True, reason, evidence)

        return (
            False,
            "No unresolved Agent 4 hard blocker remained unclosed in Phase 5 evidence.",
            evidence,
        )

    # ---------------------------------------------------------------------
    # Source helpers
    # ---------------------------------------------------------------------

    def _first_req_source(
        self, bundle: NormalizedEvidenceBundle
    ) -> Optional[SourceRef]:
        if bundle.requirements:
            return bundle.requirements[0].source
        return None

    def _first_test_case_source(
        self, bundle: NormalizedEvidenceBundle
    ) -> Optional[SourceRef]:
        if bundle.test_cases:
            return bundle.test_cases[0].source
        return None

    def _first_trace_source(
        self, bundle: NormalizedEvidenceBundle
    ) -> Optional[SourceRef]:
        if bundle.traceability_links:
            return bundle.traceability_links[0].source
        return None

    def _first_exec_source(
        self, bundle: NormalizedEvidenceBundle
    ) -> Optional[SourceRef]:
        if bundle.executions:
            return bundle.executions[0].source
        return None

    def _first_defect_source(
        self, bundle: NormalizedEvidenceBundle
    ) -> Optional[SourceRef]:
        if bundle.defects:
            return bundle.defects[0].source
        return None

    @staticmethod
    def _dedupe_refs(values: Sequence[Optional[SourceRef]]) -> List[SourceRef]:
        out: List[SourceRef] = []
        seen = set()
        for ref in values:
            if ref is None:
                continue
            key = (ref.file_path, ref.line_start, ref.line_end, ref.snippet)
            if key in seen:
                continue
            seen.add(key)
            out.append(ref)
        return out


def evaluate_phase5_readiness(
    bundle: NormalizedEvidenceBundle,
    *,
    environment: Optional[str] = None,
    config: Optional[PolicyConfig] = None,
) -> RuleFindings:
    """
    Convenience functional API for one-shot Phase 5 policy evaluation.
    """
    return Phase5PolicyEngine(config=config).evaluate(bundle, environment=environment)


__all__ = [
    "PolicyConfig",
    "Phase5PolicyEngine",
    "evaluate_phase5_readiness",
]
