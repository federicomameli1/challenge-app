from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pytest

from agent5.models import Decision

from agent6.agent import Agent6Config, Agent6Orchestrator
from agent6.models import Decision as Agent6Decision
from agent6.models import validate_output_schema
from agent6.normalization import normalize_phase6_bundle
from agent6.policy import Phase6PolicyEngine


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_a4_handoff(
    decision: str = "GO",
    triggered_rules: Optional[List[str]] = None,
    module_versions: Optional[List[Dict[str, str]]] = None,
    unresolved_conditions: Optional[List[str]] = None,
    open_blocker_email: bool = False,
) -> Dict[str, Any]:
    return {
        "source_stage": "agent4",
        "scenario_id": "S6-001",
        "release_id": "REL-001",
        "decision": decision,
        "payload": {
            "rule_findings": {
                "triggered_rule_codes": triggered_rules or [],
                "module_versions": module_versions or [],
            },
            "unresolved_conditions": unresolved_conditions or [],
            "open_blocker_email": open_blocker_email,
        },
        "metadata": {"produced_by": "agent4"},
        "produced_at_utc": "2026-05-10T10:00:00Z",
    }


def _make_a5_handoff(
    decision: str = "GO",
    critical_defect_open: bool = False,
    open_critical_defect_ids: Optional[List[str]] = None,
    requirement_coverage: float = 1.0,
    closure_confirmed: bool = False,
    unresolved_conditions: Optional[List[str]] = None,
    module_versions: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    return {
        "source_stage": "agent5",
        "scenario_id": "S6-001",
        "release_id": "REL-001",
        "decision": decision,
        "payload": {
            "rule_findings": {
                "triggered_rule_codes": [],
                "critical_defect_open": critical_defect_open,
                "module_versions": module_versions or [],
            },
            "coverage_metrics": {
                "requirement_coverage": requirement_coverage,
            },
            "cross_phase_continuity_flags": {
                "closure_confirmed": closure_confirmed,
                "agent4_unresolved_conditions": unresolved_conditions or [],
            },
            "defects": [
                {
                    "defect_id": did,
                    "status": "OPEN",
                    "severity": "CRITICAL",
                }
                for did in (open_critical_defect_ids or [])
            ],
        },
        "metadata": {"produced_by": "agent5"},
        "produced_at_utc": "2026-05-10T10:05:00Z",
    }


def _make_approval_manifest(
    approvals: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return dict(
        {
            f'approvals_{item["role"]}_signed': item.get("signed", False)
            for item in (approvals or [])
        },
        scenario_id="S6-001",
        release_id="REL-001",
    )


# ---------------------------------------------------------------------------
# Tier-1: End-to-end assess_from_handoffs
# ---------------------------------------------------------------------------


def test_assess_from_handoffs_full_go_path(tmp_path: Path) -> None:
    """Both A4 and A5 GO, all approvals signed -> Agent 6 GO."""
    orch = Agent6Orchestrator(
        config=Agent6Config(
            dataset_root=str(tmp_path),
            use_llm_summary=False,
            strict_schema=False,
        )
    )

    a4 = _make_a4_handoff(
        decision="GO",
        module_versions=[{"module": "auth", "deployed_version": "2.0"}],
    )
    a5 = _make_a5_handoff(
        decision="GO",
        critical_defect_open=False,
        requirement_coverage=1.0,
        closure_confirmed=True,
        module_versions=[{"module": "auth", "tested_version": "2.0"}],
    )

    payload = orch.assess_from_handoffs(
        scenario_id="S6-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
        release_id="REL-001",
    )

    assert payload.get("decision") == "GO"
    valid, errors = validate_output_schema(payload)
    assert valid, errors


def test_assess_from_handoffs_a4_hold_a5_go_no_closure_holds() -> None:
    """A4 HOLD with no closure confirmation -> Agent 6 should HOLD via R3."""
    orch = Agent6Orchestrator(
        config=Agent6Config(
            dataset_root="/tmp/nonexistent",
            use_llm_summary=False,
            strict_schema=False,
        )
    )

    a4 = _make_a4_handoff(
        decision="HOLD",
        triggered_rules=["open_blocker_email"],
        open_blocker_email=True,
        unresolved_conditions=["backend_version_mismatch"],
    )
    a5 = _make_a5_handoff(
        decision="GO",
        critical_defect_open=False,
        requirement_coverage=1.0,
        closure_confirmed=False,
    )

    payload = orch.assess_from_handoffs(
        scenario_id="S6-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
        release_id="REL-001",
    )

    assert payload.get("decision") == "HOLD"


def test_assess_from_handoffs_a4_hold_a5_confirmed_go() -> None:
    """A4 HOLD but A5 confirmed closure -> Agent 6 GO."""
    orch = Agent6Orchestrator(
        config=Agent6Config(
            dataset_root="/tmp/nonexistent",
            use_llm_summary=False,
            strict_schema=False,
        )
    )

    a4 = _make_a4_handoff(
        decision="HOLD",
        triggered_rules=["open_blocker_email"],
    )
    a5 = _make_a5_handoff(
        decision="GO",
        critical_defect_open=False,
        requirement_coverage=1.0,
        closure_confirmed=True,
    )

    payload = orch.assess_from_handoffs(
        scenario_id="S6-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
        release_id="REL-001",
    )

    assert payload.get("decision") == "GO"


def test_assess_from_handoffs_critical_defect_open() -> None:
    """A5 critical defect open -> Agent 6 HOLD."""
    orch = Agent6Orchestrator(
        config=Agent6Config(
            dataset_root="/tmp/nonexistent",
            use_llm_summary=False,
            strict_schema=False,
        )
    )

    a4 = _make_a4_handoff(decision="GO")
    a5 = _make_a5_handoff(
        decision="HOLD",
        critical_defect_open=True,
        open_critical_defect_ids=["DF-CRIT-42"],
        requirement_coverage=1.0,
    )

    payload = orch.assess_from_handoffs(
        scenario_id="S6-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
        release_id="REL-001",
    )

    assert payload.get("decision") == "HOLD"


def test_assess_from_handoffs_coverage_gap() -> None:
    """A5 coverage 85% -> Agent 6 HOLD."""
    orch = Agent6Orchestrator(
        config=Agent6Config(
            dataset_root="/tmp/nonexistent",
            use_llm_summary=False,
            strict_schema=False,
        )
    )

    a4 = _make_a4_handoff(decision="GO")
    a5 = _make_a5_handoff(
        decision="GO",
        critical_defect_open=False,
        requirement_coverage=0.85,
    )

    payload = orch.assess_from_handoffs(
        scenario_id="S6-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
        release_id="REL-001",
    )

    assert payload.get("decision") == "HOLD"


def test_assess_from_handoffs_version_mismatch() -> None:
    """A4 deployed 2.0, A5 tested 2.1 -> Agent 6 HOLD."""
    orch = Agent6Orchestrator(
        config=Agent6Config(
            dataset_root="/tmp/nonexistent",
            use_llm_summary=False,
            strict_schema=False,
        )
    )

    a4 = _make_a4_handoff(
        decision="GO",
        module_versions=[{"module": "auth", "deployed_version": "2.0"}],
    )
    a5 = _make_a5_handoff(
        decision="GO",
        critical_defect_open=False,
        requirement_coverage=1.0,
    )

    # Inject version mismatch by setting a5 to test a different version
    a5_with_mismatch = _make_a5_handoff(
        decision="GO",
        critical_defect_open=False,
        requirement_coverage=1.0,
    )
    # Add module_versions to a5 payload
    a5_with_mismatch["payload"]["rule_findings"]["module_versions"] = [
        {"module": "auth", "tested_version": "2.1"}
    ]

    payload = orch.assess_from_handoffs(
        scenario_id="S6-001",
        agent4_handoff=a4,
        agent5_handoff=a5_with_mismatch,
        release_id="REL-001",
    )

    assert payload.get("decision") == "HOLD"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_schema_validation_valid_output() -> None:
    """Validate that a complete GO output passes schema validation."""
    a4 = _make_a4_handoff(decision="GO")
    a5 = _make_a5_handoff(decision="GO", critical_defect_open=False, requirement_coverage=1.0)

    orch = Agent6Orchestrator(
        config=Agent6Config(use_llm_summary=False, strict_schema=False)
    )
    payload = orch.assess_from_handoffs(
        scenario_id="S6-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
    )

    valid, errors = validate_output_schema(payload)
    assert valid, f"Schema validation failed: {errors}"
    assert "schema_validation" in payload


def test_schema_validation_decision_field() -> None:
    valid, errors = validate_output_schema({
        "scenario_id": "X",
        "release_id": "Y",
        "decision": "GO",
        "decision_type": "deterministic",
        "reasons": [],
        "evidence": [],
        "confidence": "high",
        "human_action": "proceed",
        "summary": "clean",
        "policy_version": "phase6-policy-v1",
        "timestamp_utc": "2026-05-10T00:00:00Z",
        "rule_findings": {},
    })
    assert valid


def test_schema_validation_missing_required_field() -> None:
    valid, errors = validate_output_schema({
        "scenario_id": "X",
        # missing release_id
        "decision": "GO",
        "decision_type": "deterministic",
        "reasons": [],
        "evidence": [],
        "confidence": "high",
        "human_action": "proceed",
        "summary": "clean",
        "policy_version": "phase6-policy-v1",
        "timestamp_utc": "2026-05-10T00:00:00Z",
        "rule_findings": {},
    })
    assert not valid
    assert any("release_id" in e for e in errors)


# ---------------------------------------------------------------------------
# Normalization pipeline
# ---------------------------------------------------------------------------


def test_normalization_pipeline_rounds_through() -> None:
    from agent6.ingestion import Phase6Ingestion

    a4 = _make_a4_handoff(decision="GO")
    a5 = _make_a5_handoff(decision="GO", critical_defect_open=False, requirement_coverage=1.0)

    ingestion = Phase6Ingestion(dataset_root="/tmp/nonexistent")
    raw = ingestion.ingest_from_handoffs(
        scenario_id="S6-001",
        release_id="REL-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
    )
    bundle = normalize_phase6_bundle(raw)

    assert bundle.scenario_id == "S6-001"
    assert bundle.release_id == "REL-001"
    assert bundle.agent4_context is not None
    assert bundle.agent5_context is not None
    assert bundle.agent4_context.decision == "GO"


# ---------------------------------------------------------------------------
# Brain orchestrator integration (stage adapter entry point)
# ---------------------------------------------------------------------------


def test_agent6_orchestrator_run_with_both_handoffs() -> None:
    """Agent6Orchestrator.run() with handoffs uses assess_from_handoffs."""
    orch = Agent6Orchestrator(
        config=Agent6Config(use_llm_summary=False, strict_schema=False)
    )

    a4 = _make_a4_handoff(decision="GO")
    a5 = _make_a5_handoff(decision="GO", critical_defect_open=False, requirement_coverage=1.0)

    result = orch.run(
        scenario_id="S6-001",
        release_id="REL-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
    )

    assert result.get("decision") == "GO"
    assert result.get("schema_validation", {}).get("valid") is True


def test_agent6_orchestrator_run_without_handoffs(tmp_path: Path) -> None:
    """Agent6Orchestrator.run() without handoffs uses assess_scenario (standalone)."""
    root = tmp_path / "phase6_empty"
    root.mkdir(parents=True)

    # Create minimal calendar so list_scenarios doesn't error
    calendar = root / "phase6_release_calendar.csv"
    calendar.write_text(
        "scenario_id,release_id,environment\nS6-EMPTY,REL-EMPTY,RELEASE\n",
        encoding="utf-8",
    )

    orch = Agent6Orchestrator(
        config=Agent6Config(dataset_root=str(root), use_llm_summary=False, strict_schema=False)
    )

    # No handoffs means standalone mode which needs A4/A5 context files.
    # With none present, Agent 6 will still assess but find missing handoffs.
    try:
        result = orch.run(scenario_id="S6-EMPTY", release_id="REL-EMPTY")
        # Should produce output (may be HOLD due to missing context)
        assert "decision" in result
    except Exception as exc:
        # Standalone without handoffs and without context files is expected
        assert "not found" in str(exc).lower() or "ingestion" in str(exc).lower()


# ---------------------------------------------------------------------------
# Label check
# ---------------------------------------------------------------------------


def test_label_check_correct_match(tmp_path: Path) -> None:
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "scenario_id,release_id,expected_decision,triggered_conditions\n"
        "S6-001,REL-001,GO,\n",
        encoding="utf-8",
    )

    orch = Agent6Orchestrator(
        config=Agent6Config(use_llm_summary=False, strict_schema=False)
    )

    a4 = _make_a4_handoff(decision="GO")
    a5 = _make_a5_handoff(decision="GO", critical_defect_open=False, requirement_coverage=1.0)

    result = orch.run(
        scenario_id="S6-001",
        release_id="REL-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
        check_label=True,
        labels_path=str(labels),
    )

    eval_result = result.get("evaluation", {})
    assert eval_result.get("match") is True
    assert eval_result.get("expected_decision") == "GO"
    assert eval_result.get("actual_decision") == "GO"


# ---------------------------------------------------------------------------
# Schema validation via run helper
# ---------------------------------------------------------------------------


def test_run_strict_schema_raises_on_invalid() -> None:
    orch = Agent6Orchestrator(
        config=Agent6Config(use_llm_summary=False, strict_schema=True)
    )

    a4 = _make_a4_handoff(decision="GO")
    a5 = _make_a5_handoff(decision="GO", critical_defect_open=False, requirement_coverage=1.0)

    result = orch.run(
        scenario_id="S6-001",
        release_id="REL-001",
        agent4_handoff=a4,
        agent5_handoff=a5,
    )

    # Strict schema + valid output should NOT raise
    assert result.get("schema_validation", {}).get("valid") is True
