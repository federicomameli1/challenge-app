from __future__ import annotations

from typing import Dict, Mapping, Optional

import pytest

from agent6.consistency import (
    VersionConflict,
    build_consistency_audit,
    check_cross_phase_version_consistency,
)
from agent6.models import SourceRef
from agent6.normalization import (
    NormalizedAgent4Context,
    NormalizedAgent5Context,
    NormalizedApprovalItem,
    NormalizedPhase6Bundle,
)


def _ref(path: str = "handoff") -> SourceRef:
    return SourceRef(file_path=path)


def _a4_ctx(
    decision: str = "GO",
    module_versions: Optional[Mapping[str, str]] = None,
) -> NormalizedAgent4Context:
    return NormalizedAgent4Context(
        decision=decision,
        triggered_rules=(),
        open_blocker_detected=False,
        critical_service_unhealthy=False,
        module_versions=dict(module_versions or {}),
        unresolved_conditions=(),
        closure_confirmed=False,
        source=_ref("agent4_handoff"),
    )


def _a5_ctx(
    coverage_ratio: float = 1.0,
    module_versions: Optional[Mapping[str, str]] = None,
) -> NormalizedAgent5Context:
    return NormalizedAgent5Context(
        decision="GO",
        triggered_rules=(),
        critical_defect_open=False,
        open_critical_defect_ids=(),
        requirements_coverage_ratio=coverage_ratio,
        agent4_closure_confirmed=False,
        agent4_unresolved_conditions=(),
        module_versions=dict(module_versions or {}),
        vdd_completeness={},
        conditional_approval_triggers=(),
        source=_ref("agent5_handoff"),
    )


def _bundle(
    a4_versions: Optional[Mapping[str, str]] = None,
    a5_versions: Optional[Mapping[str, str]] = None,
    coverage_ratio: float = 1.0,
    approvals: Optional[list] = None,
) -> NormalizedPhase6Bundle:
    a4 = _a4_ctx(module_versions=a4_versions) if a4_versions is not None else None
    a5 = _a5_ctx(coverage_ratio=coverage_ratio, module_versions=a5_versions) if a5_versions is not None else None

    # cross_phase_version_mismatch is computed by check_cross_phase_version_consistency
    # from the module_versions fields directly, so we set it False here and let the
    # consistency checker derive the real value.
    return NormalizedPhase6Bundle(
        scenario_id="TEST-CONS-001",
        release_id="REL-CONS-1",
        environment="RELEASE",
        agent4_context=a4,
        agent5_context=a5,
        approval_items=tuple(approvals or []),
        cross_phase_version_mismatch=False,
        agent5_critical_defect_open=False,
        agent4_blocker_unconfirmed=False,
        requirements_coverage_gap=coverage_ratio < 1.0,
        vdd_incomplete=False,
        missing_approval_trigger=False,
        continuity_notes=(),
    )


def _empty_bundle() -> NormalizedPhase6Bundle:
    return NormalizedPhase6Bundle(
        scenario_id="TEST-CONS-001",
        release_id="REL-CONS-1",
        environment="RELEASE",
        agent4_context=None,
        agent5_context=None,
        approval_items=(),
        cross_phase_version_mismatch=False,
        agent5_critical_defect_open=False,
        agent4_blocker_unconfirmed=False,
        requirements_coverage_gap=False,
        vdd_incomplete=False,
        missing_approval_trigger=False,
        continuity_notes=(),
    )


# ---------------------------------------------------------------------------
# Version consistency check
# ---------------------------------------------------------------------------


def test_version_consistent_no_conflicts() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0", "payment": "1.5"},
        a5_versions={"auth": "2.0", "payment": "1.5"},
    )
    conflicts, has_conflicts = check_cross_phase_version_consistency(bundle)

    assert has_conflicts is False
    assert len(conflicts) == 0


def test_version_mismatch_detected() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0"},
        a5_versions={"auth": "2.1"},
    )
    conflicts, has_conflicts = check_cross_phase_version_consistency(bundle)

    assert has_conflicts is True
    assert len(conflicts) == 1
    assert conflicts[0].module == "auth"
    assert conflicts[0].conflict_type == "mismatch"
    assert conflicts[0].a4_version == "2.0"
    assert conflicts[0].a5_version == "2.1"


def test_module_missing_in_a5() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0", "payment": "1.5"},
        a5_versions={"auth": "2.0"},
    )
    conflicts, has_conflicts = check_cross_phase_version_consistency(bundle)

    assert has_conflicts is True
    assert len(conflicts) == 1
    assert conflicts[0].module == "payment"
    assert conflicts[0].conflict_type == "missing_in_a5"


def test_module_missing_in_a4_informational() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0"},
        a5_versions={"auth": "2.0", "reporting": "1.0"},
    )
    conflicts, has_conflicts = check_cross_phase_version_consistency(bundle)

    # missing_in_a4 is informational only, does NOT create hard conflict
    assert has_conflicts is False
    assert len(conflicts) == 1
    assert conflicts[0].module == "reporting"
    assert conflicts[0].conflict_type == "missing_in_a4"


def test_both_contexts_none_no_conflicts() -> None:
    bundle = _empty_bundle()
    conflicts, has_conflicts = check_cross_phase_version_consistency(bundle)

    assert has_conflicts is False
    assert len(conflicts) == 0


def test_a4_context_none_no_conflicts() -> None:
    bundle = _bundle(a4_versions=None, a5_versions={"auth": "2.0"})
    conflicts, has_conflicts = check_cross_phase_version_consistency(bundle)

    assert has_conflicts is False
    assert len(conflicts) == 0


# ---------------------------------------------------------------------------
# Build consistency audit
# ---------------------------------------------------------------------------


def test_consistency_audit_clean() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0"},
        a5_versions={"auth": "2.0"},
        coverage_ratio=1.0,
        approvals=[NormalizedApprovalItem(role="qa", required=True, signed=True, signed_by="qa1", source=_ref())],
    )
    audit = build_consistency_audit(bundle)

    assert len(audit.version_conflicts) == 0
    assert len(audit.traceability_gaps) == 0
    assert len(audit.approval_gaps) == 0


def test_consistency_audit_with_version_conflict() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0"},
        a5_versions={"auth": "2.1"},
        coverage_ratio=1.0,
        approvals=[NormalizedApprovalItem(role="qa", required=True, signed=True, signed_by="qa1", source=_ref())],
    )
    audit = build_consistency_audit(bundle)

    assert len(audit.version_conflicts) == 1
    assert "module:auth:A4=2.0≠A5=2.1" in audit.version_conflicts[0]


def test_consistency_audit_missing_in_a5() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0"},
        a5_versions={},
        coverage_ratio=1.0,
        approvals=[NormalizedApprovalItem(role="qa", required=True, signed=True, signed_by="qa1", source=_ref())],
    )
    audit = build_consistency_audit(bundle)

    assert len(audit.version_conflicts) == 1
    assert "module:auth:A4=2.0:not_in_agent5" in audit.version_conflicts[0]


def test_consistency_audit_missing_approval_gap() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0"},
        a5_versions={"auth": "2.0"},
        coverage_ratio=1.0,
        approvals=[
            NormalizedApprovalItem(role="supplier", required=True, signed=False, signed_by=None, source=_ref()),
        ],
    )
    audit = build_consistency_audit(bundle)

    assert len(audit.approval_gaps) == 1
    assert "supplier" in audit.approval_gaps[0]


def test_consistency_audit_coverage_gap() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0"},
        a5_versions={"auth": "2.0"},
        coverage_ratio=0.80,
        approvals=[NormalizedApprovalItem(role="qa", required=True, signed=True, signed_by="qa1", source=_ref())],
    )
    audit = build_consistency_audit(bundle)

    assert len(audit.traceability_gaps) == 1
    assert "80%" in audit.traceability_gaps[0]


# ---------------------------------------------------------------------------
# VersionConflict dataclass
# ---------------------------------------------------------------------------


def test_version_conflict_dataclass() -> None:
    vc = VersionConflict(
        module="auth",
        a4_version="2.0",
        a5_version="2.1",
        conflict_type="mismatch",
    )
    assert vc.module == "auth"
    assert vc.a4_version == "2.0"
    assert vc.a5_version == "2.1"
    assert vc.conflict_type == "mismatch"


# ---------------------------------------------------------------------------
# Multi-module scenarios
# ---------------------------------------------------------------------------


def test_multi_module_some_match_some_mismatch() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0", "payment": "1.5", "reporting": "3.0"},
        a5_versions={"auth": "2.0", "payment": "1.6", "reporting": "3.0"},
    )
    conflicts, has_conflicts = check_cross_phase_version_consistency(bundle)

    assert has_conflicts is True
    assert len(conflicts) == 1
    assert conflicts[0].module == "payment"


def test_multi_module_all_match() -> None:
    bundle = _bundle(
        a4_versions={"auth": "2.0", "payment": "1.5", "reporting": "3.0"},
        a5_versions={"auth": "2.0", "payment": "1.5", "reporting": "3.0", "analytics": "1.0"},
    )
    conflicts, has_conflicts = check_cross_phase_version_consistency(bundle)

    assert has_conflicts is False
    assert len(conflicts) == 1  # analytics missing_in_a4 (informational)
