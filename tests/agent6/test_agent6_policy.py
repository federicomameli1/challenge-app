from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence

import pytest

from agent6.models import Decision, RuleCode, SourceRef
from agent6.normalization import (
    NormalizedAgent4Context,
    NormalizedAgent5Context,
    NormalizedApprovalItem,
    NormalizedPhase6Bundle,
)
from agent6.policy import PolicyConfig, Phase6PolicyEngine, evaluate_phase6_readiness


def _make_ref(path: str = "handoff") -> SourceRef:
    return SourceRef(file_path=path)


def _a4_ctx(
    decision: str = "GO",
    open_blocker: bool = False,
    module_versions: Optional[Mapping[str, str]] = None,
    triggered_rules: Optional[Sequence[str]] = None,
    unresolved: Optional[Sequence[str]] = None,
) -> NormalizedAgent4Context:
    return NormalizedAgent4Context(
        decision=decision,
        triggered_rules=tuple(triggered_rules or []),
        open_blocker_detected=open_blocker,
        critical_service_unhealthy=False,
        module_versions=dict(module_versions or {}),
        unresolved_conditions=tuple(unresolved or []),
        closure_confirmed=False,
        source=_make_ref("agent4_handoff"),
    )


def _a5_ctx(
    decision: str = "GO",
    critical_defect_open: bool = False,
    open_critical_ids: Optional[Sequence[str]] = None,
    coverage_ratio: Optional[float] = 1.0,
    a4_closure_confirmed: bool = False,
    a4_unresolved: Optional[Sequence[str]] = None,
    module_versions: Optional[Mapping[str, str]] = None,
) -> NormalizedAgent5Context:
    return NormalizedAgent5Context(
        decision=decision,
        triggered_rules=(),
        critical_defect_open=critical_defect_open,
        open_critical_defect_ids=tuple(open_critical_ids or []),
        requirements_coverage_ratio=coverage_ratio,
        agent4_closure_confirmed=a4_closure_confirmed,
        agent4_unresolved_conditions=tuple(a4_unresolved or []),
        module_versions=dict(module_versions or {}),
        vdd_completeness={},
        conditional_approval_triggers=(),
        source=_make_ref("agent5_handoff"),
    )


def _approval(
    role: str,
    required: bool = True,
    signed: bool = False,
) -> NormalizedApprovalItem:
    return NormalizedApprovalItem(
        role=role,
        required=required,
        signed=signed,
        signed_by="test" if signed else None,
        source=_make_ref("approval"),
    )


def _bundle(
    a4: Optional[NormalizedAgent4Context] = None,
    a5: Optional[NormalizedAgent5Context] = None,
    approvals: Optional[Sequence[NormalizedApprovalItem]] = None,
    cross_phase_mismatch: bool = False,
    agent5_defect_open: bool = False,
    agent4_blocker_unconf: bool = False,
    coverage_gap: bool = False,
    vdd_incomplete: bool = False,
    missing_approval: bool = False,
    continuity_notes: Optional[Sequence[str]] = None,
) -> NormalizedPhase6Bundle:
    return NormalizedPhase6Bundle(
        scenario_id="TEST-S6-001",
        release_id="REL-001",
        environment="RELEASE",
        agent4_context=a4,
        agent5_context=a5,
        approval_items=tuple(approvals or []),
        cross_phase_version_mismatch=cross_phase_mismatch,
        agent5_critical_defect_open=agent5_defect_open,
        agent4_blocker_unconfirmed=agent4_blocker_unconf,
        requirements_coverage_gap=coverage_gap,
        vdd_incomplete=vdd_incomplete,
        missing_approval_trigger=missing_approval,
        continuity_notes=tuple(continuity_notes or []),
    )


# ---------------------------------------------------------------------------
# GO path tests (all gates pass)
# ---------------------------------------------------------------------------


def test_all_gates_pass_decision_go() -> None:
    """When all 6 rule flags are False, policy recommends GO."""
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=1.0),
        approvals=[_approval("supplier", signed=True), _approval("customer", signed=True)],
    )
    engine = Phase6PolicyEngine()
    findings = engine.evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.hold_required is False
    assert findings.triggered_rule_codes == []


def test_empty_bundle_go_when_both_handoffs_clean() -> None:
    """Minimal clean bundle: GO."""
    bundle = _bundle(
        a4=_a4_ctx(decision="GO", open_blocker=False, module_versions={"auth": "2.0"}),
        a5=_a5_ctx(
            decision="GO",
            critical_defect_open=False,
            coverage_ratio=1.0,
            a4_closure_confirmed=True,
        ),
        approvals=[_approval("qa_lead", signed=True)],
    )
    engine = Phase6PolicyEngine()
    findings = engine.evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.hold_required is False


# ---------------------------------------------------------------------------
# R1: CROSS_PHASE_VERSION_MISMATCH
# ---------------------------------------------------------------------------


def test_r1_cross_phase_mismatch_triggers_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO", module_versions={"auth": "2.0"}),
        a5=_a5_ctx(),
        cross_phase_mismatch=True,
        continuity_notes=["version_mismatch:auth:A4=2.0:A5=2.1"],
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.HOLD
    assert findings.cross_phase_version_mismatch is True
    assert RuleCode.CROSS_PHASE_VERSION_MISMATCH.value in findings.triggered_rule_codes


def test_r1_no_mismatch_no_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO", module_versions={"auth": "2.0"}),
        a5=_a5_ctx(),
        cross_phase_mismatch=False,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.cross_phase_version_mismatch is False


# ---------------------------------------------------------------------------
# R2: AGENT5_CRITICAL_DEFECT_OPEN
# ---------------------------------------------------------------------------


def test_r2_agent5_critical_defect_open_triggers_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(critical_defect_open=True, open_critical_ids=["DF-CRIT-1"]),
        agent5_defect_open=True,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.HOLD
    assert findings.agent5_critical_defect_open is True
    assert RuleCode.AGENT5_CRITICAL_DEFECT_OPEN.value in findings.triggered_rule_codes


def test_r2_agent5_no_critical_defect_no_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(critical_defect_open=False, coverage_ratio=1.0),
        approvals=[_approval("qa_lead", signed=True)],
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.agent5_critical_defect_open is False


def test_r2_agent5_context_absent_triggers_hold() -> None:
    bundle = _bundle(a4=_a4_ctx(decision="GO"), a5=None)
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.HOLD
    assert findings.agent5_critical_defect_open is True


# ---------------------------------------------------------------------------
# R3: AGENT4_BLOCKER_UNCONFIRMED
# ---------------------------------------------------------------------------


def test_r3_a4_hold_unconfirmed_triggers_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="HOLD", open_blocker=True, unresolved=["backend_version_mismatch"]),
        a5=_a5_ctx(),
        approvals=[],
        agent4_blocker_unconf=True,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.HOLD
    assert findings.agent4_blocker_unconfirmed is True
    assert RuleCode.AGENT4_BLOCKER_UNCONFIRMED.value in findings.triggered_rule_codes


def test_r3_a4_hold_but_a5_confirmed_closure_no_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="HOLD", open_blocker=True),
        a5=_a5_ctx(a4_closure_confirmed=True, coverage_ratio=1.0),
        approvals=[_approval("qa_lead", signed=True)],
        agent4_blocker_unconf=False,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.agent4_blocker_unconfirmed is False


def test_r3_a4_hold_but_vdd_signed_no_hold() -> None:
    """A5 didn't confirm, but Phase 6 approval sign-off exists."""
    bundle = _bundle(
        a4=_a4_ctx(decision="HOLD", open_blocker=True),
        a5=_a5_ctx(coverage_ratio=1.0),
        approvals=[_approval("supplier", signed=True), _approval("customer", signed=True)],
        agent4_blocker_unconf=False,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.agent4_blocker_unconfirmed is False


def test_r3_a4_go_clean_no_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO", open_blocker=False),
        a5=_a5_ctx(coverage_ratio=1.0),
        approvals=[_approval("qa_lead", signed=True)],
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.agent4_blocker_unconfirmed is False


def test_r3_a4_context_absent_triggers_hold() -> None:
    bundle = _bundle(a4=None, a5=None, approvals=[])
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.HOLD
    assert findings.agent4_blocker_unconfirmed is True


# ---------------------------------------------------------------------------
# R4: REQUIREMENTS_COVERAGE_GAP
# ---------------------------------------------------------------------------


def test_r4_coverage_below_threshold_triggers_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=0.80),
        approvals=[_approval("qa_lead", signed=True)],
        coverage_gap=True,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.HOLD
    assert findings.requirements_coverage_gap is True
    assert RuleCode.REQUIREMENTS_COVERAGE_GAP.value in findings.triggered_rule_codes


def test_r4_coverage_at_threshold_no_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=1.0),
        approvals=[_approval("qa_lead", signed=True)],
        coverage_gap=False,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.requirements_coverage_gap is False


def test_r4_no_coverage_ratio_from_a5_no_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=None),
        approvals=[_approval("qa_lead", signed=True)],
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.GO


# ---------------------------------------------------------------------------
# R5: VDD_INCOMPLETE
# ---------------------------------------------------------------------------


def test_r5_vdd_incomplete_triggers_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=1.0),
        approvals=[_approval("qa_lead", signed=True)],
        vdd_incomplete=True,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.HOLD
    assert findings.vdd_incomplete is True
    assert RuleCode.VDD_INCOMPLETE.value in findings.triggered_rule_codes


def test_r5_vdd_complete_no_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=1.0),
        approvals=[_approval("qa_lead", signed=True)],
        vdd_incomplete=False,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.vdd_incomplete is False


# ---------------------------------------------------------------------------
# R6: MISSING_APPROVAL_TRIGGER
# ---------------------------------------------------------------------------


def test_r6_missing_approval_triggers_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=1.0),
        approvals=[
            _approval("supplier", signed=True),
            _approval("customer", signed=False, required=True),
        ],
        missing_approval=True,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.HOLD
    assert findings.missing_approval_trigger is True
    assert RuleCode.MISSING_APPROVAL_TRIGGER.value in findings.triggered_rule_codes


def test_r6_all_approvals_signed_no_hold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=1.0),
        approvals=[
            _approval("supplier", signed=True),
            _approval("customer", signed=True),
        ],
        missing_approval=False,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.GO
    assert findings.missing_approval_trigger is False


# ---------------------------------------------------------------------------
# Multiple HOLD triggers
# ---------------------------------------------------------------------------


def test_multiple_holds_all_codes_in_output() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="HOLD", open_blocker=True),
        a5=_a5_ctx(critical_defect_open=True, coverage_ratio=0.70),
        approvals=[_approval("supplier", signed=False, required=True)],
        cross_phase_mismatch=True,
        agent5_defect_open=True,
        agent4_blocker_unconf=True,
        coverage_gap=True,
        vdd_incomplete=True,
        missing_approval=True,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)

    assert findings.decision == Decision.HOLD
    assert findings.hold_required is True
    codes = findings.triggered_rule_codes
    assert RuleCode.CROSS_PHASE_VERSION_MISMATCH.value in codes
    assert RuleCode.AGENT5_CRITICAL_DEFECT_OPEN.value in codes
    assert RuleCode.AGENT4_BLOCKER_UNCONFIRMED.value in codes
    assert RuleCode.REQUIREMENTS_COVERAGE_GAP.value in codes
    assert RuleCode.VDD_INCOMPLETE.value in codes
    assert RuleCode.MISSING_APPROVAL_TRIGGER.value in codes


# ---------------------------------------------------------------------------
# Convenience functional API
# ---------------------------------------------------------------------------


def test_evaluate_phase6_readiness_functional_api() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=1.0),
        approvals=[_approval("qa_lead", signed=True)],
    )
    findings = evaluate_phase6_readiness(bundle)
    assert findings.decision == Decision.GO


def test_policy_config_threshold() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(coverage_ratio=0.95),
        approvals=[_approval("qa_lead", signed=True)],
    )
    # Default threshold is 1.0, so 0.95 should trigger gap
    findings = Phase6PolicyEngine(PolicyConfig(min_requirements_coverage_ratio=1.0)).evaluate(bundle)
    assert findings.requirements_coverage_gap is True
    assert findings.decision == Decision.HOLD

    # With 0.90 threshold, 0.95 passes
    findings = Phase6PolicyEngine(PolicyConfig(min_requirements_coverage_ratio=0.90)).evaluate(bundle)
    assert findings.requirements_coverage_gap is False
    assert findings.decision == Decision.GO


def test_findings_to_dict() -> None:
    bundle = _bundle(
        a4=_a4_ctx(decision="GO"),
        a5=_a5_ctx(critical_defect_open=True),
        agent5_defect_open=True,
    )
    findings = Phase6PolicyEngine().evaluate(bundle)
    d = findings.to_dict()

    assert "hold_required" in d
    assert "decision" in d
    assert "triggered_rule_codes" in d
    assert "findings" in d
    assert d["decision"] == "HOLD"
