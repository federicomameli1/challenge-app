from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pytest

from agent5.agent import Agent5Config, Agent5LangChainOrchestrator
from agent5.explanation import ExplanationContext, build_deterministic_explanation
from agent5.ingestion import Phase5Ingestion
from agent5.lc_pipeline import LangChainAgent5Pipeline, LCPipelineConfig
from agent5.models import (
    Decision,
    DecisionType,
    ReasonItem,
    RuleCode,
    RuleFinding,
    RuleFindings,
    SourceRef,
    build_agent5_output,
    validate_output_schema,
)
from agent5.normalization import normalize_evidence_bundle
from agent5.policy import Phase5PolicyEngine


def _write_csv(
    path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _scenario_rows(scenario_id: str, release_id: str, kind: str) -> Dict[str, object]:
    req1 = f"{scenario_id}-REQ-1"
    req2 = f"{scenario_id}-REQ-2"
    req3 = f"{scenario_id}-REQ-3"

    tc1 = f"{scenario_id}-TC-1"
    tc2 = f"{scenario_id}-TC-2"
    tc3 = f"{scenario_id}-TC-3"

    requirements = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "requirement_id": req1,
            "description": "Mandatory auth regression",
            "priority": "HIGH",
            "module": "auth-service",
            "mandatory_for_phase5": "true",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "requirement_id": req2,
            "description": "Mandatory payment idempotency",
            "priority": "HIGH",
            "module": "payment-core",
            "mandatory_for_phase5": "true",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "requirement_id": req3,
            "description": "Optional UI smoke",
            "priority": "LOW",
            "module": "reporting-ui",
            "mandatory_for_phase5": "false",
        },
    ]

    test_cases = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": tc1,
            "title": "Auth flow",
            "mapped_requirement_ids": req1,
            "criticality": "HIGH",
            "test_owner": "qa.auth",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": tc2,
            "title": "Payment idempotency",
            "mapped_requirement_ids": req2,
            "criticality": "HIGH",
            "test_owner": "qa.payment",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": tc3,
            "title": "Reporting smoke",
            "mapped_requirement_ids": req3,
            "criticality": "LOW",
            "test_owner": "qa.ui",
        },
    ]

    traceability = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "requirement_id": req1,
            "test_case_id": tc1,
            "mapping_source": "traceability_workbook",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "requirement_id": req2,
            "test_case_id": tc2,
            "mapping_source": "traceability_workbook",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "requirement_id": req3,
            "test_case_id": tc3,
            "mapping_source": "traceability_workbook",
        },
    ]

    executions = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": tc1,
            "status": "PASS",
            "executed": "true",
            "retest_required": "false",
            "retest_completed": "false",
            "executor": "qa.auth",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": tc2,
            "status": "PASS",
            "executed": "true",
            "retest_required": "false",
            "retest_completed": "false",
            "executor": "qa.payment",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": tc3,
            "status": "PASS",
            "executed": "true",
            "retest_required": "false",
            "retest_completed": "false",
            "executor": "qa.ui",
        },
    ]

    defects = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "defect_id": f"{scenario_id}-DF-LOW-1",
            "title": "Minor UI issue",
            "severity": "LOW",
            "status": "CLOSED",
            "owner": "dev.ui",
        }
    ]

    expected_decision = "GO"
    triggered: List[str] = []
    agent4_context = None

    if kind == "hold_uncovered":
        traceability = [row for row in traceability if row["requirement_id"] != req2]
        executions = [row for row in executions if row["test_case_id"] != tc2]
        expected_decision = "HOLD"
        triggered = ["mandatory_requirement_uncovered", "test_evidence_incomplete"]

    elif kind == "hold_fail":
        for row in executions:
            if row["test_case_id"] == tc1:
                row["status"] = "FAIL"
        expected_decision = "HOLD"
        triggered = ["mandatory_requirement_failed_or_blocked"]

    elif kind == "hold_critical":
        defects.append(
            {
                "scenario_id": scenario_id,
                "release_id": release_id,
                "defect_id": f"{scenario_id}-DF-CRIT-1",
                "title": "Critical payment deadlock",
                "severity": "CRITICAL",
                "status": "OPEN",
                "owner": "dev.payment",
            }
        )
        expected_decision = "HOLD"
        triggered = ["critical_defect_open"]

    elif kind == "hold_conditional":
        for row in executions:
            if row["test_case_id"] == tc2:
                row["status"] = "CONDITIONAL_UNMET"
                row["retest_required"] = "true"
                row["retest_completed"] = "false"
        expected_decision = "HOLD"
        triggered = ["conditional_retest_unmet"]

    elif kind == "hold_continuity":
        agent4_context = {
            "agent4_decision": "HOLD",
            "agent4_triggered_rules": ["mandatory_version_mismatch"],
            "unresolved_conditions": ["backend_version_alignment_unclosed"],
            "closure_confirmed": False,
            "summary": "A4 unresolved hard blocker remains open.",
        }
        expected_decision = "HOLD"
        triggered = ["agent4_unresolved_hard_blocker_unclosed"]

    elif kind == "hold_incomplete":
        # Keep dataset ingestible (non-empty traceability/execution tables) while
        # making mandatory scope incomplete.
        traceability = [row for row in traceability if row["requirement_id"] == req3]
        executions = [row for row in executions if row["test_case_id"] == tc3]
        expected_decision = "HOLD"
        triggered = ["test_evidence_incomplete", "mandatory_requirement_uncovered"]

    return {
        "requirements": requirements,
        "test_cases": test_cases,
        "traceability": traceability,
        "executions": executions,
        "defects": defects,
        "agent4_context": agent4_context,
        "expected_decision": expected_decision,
        "triggered": triggered,
        "scenario_type": kind,
    }


def _build_dataset(
    tmp_path: Path,
    scenarios: Sequence[Tuple[str, str, str]],
    include_labels: bool = True,
) -> Path:
    root = tmp_path / "phase5_dataset"
    emails_dir = root / "test_analysis_emails"
    a4_dir = root / "agent4_context"
    emails_dir.mkdir(parents=True, exist_ok=True)
    a4_dir.mkdir(parents=True, exist_ok=True)

    requirements_rows: List[Dict[str, str]] = []
    test_cases_rows: List[Dict[str, str]] = []
    traceability_rows: List[Dict[str, str]] = []
    execution_rows: List[Dict[str, str]] = []
    defect_rows: List[Dict[str, str]] = []
    labels_rows: List[Dict[str, str]] = []
    calendar_rows: List[Dict[str, str]] = []

    for scenario_id, release_id, kind in scenarios:
        payload = _scenario_rows(scenario_id, release_id, kind)

        requirements_rows.extend(payload["requirements"])  # type: ignore[arg-type]
        test_cases_rows.extend(payload["test_cases"])  # type: ignore[arg-type]
        traceability_rows.extend(payload["traceability"])  # type: ignore[arg-type]
        execution_rows.extend(payload["executions"])  # type: ignore[arg-type]
        defect_rows.extend(payload["defects"])  # type: ignore[arg-type]

        calendar_rows.append(
            {
                "release_id": release_id,
                "scenario_id": scenario_id,
                "environment": "TEST",
                "phase5_window_start": "2026-05-01T09:00:00+00:00",
                "phase5_window_end": "2026-05-01T18:00:00+00:00",
                "target_phase5_gate": "phase5_test_analysis",
            }
        )

        labels_rows.append(
            {
                "scenario_id": scenario_id,
                "release_id": release_id,
                "expected_decision": payload["expected_decision"],  # type: ignore[index]
                "scenario_type": payload["scenario_type"],  # type: ignore[index]
                "rationale": f"Expected {payload['expected_decision']}",
                "triggered_conditions": "|".join(payload["triggered"]),  # type: ignore[index]
                "ambiguity_level": "low",
                "requires_agent4_closure": "true"
                if "agent4_unresolved_hard_blocker_unclosed" in payload["triggered"]  # type: ignore[operator]
                else "false",
            }
        )

        (emails_dir / f"{scenario_id}.txt").write_text(
            f"Subject: Phase5 summary for {release_id}\nNo blocking narrative.\n",
            encoding="utf-8",
        )

        if payload["agent4_context"] is not None:  # type: ignore[index]
            (a4_dir / f"{scenario_id}.json").write_text(
                json.dumps(payload["agent4_context"], indent=2) + "\n",  # type: ignore[index]
                encoding="utf-8",
            )

    _write_csv(
        root / "requirements_master.csv",
        [
            "scenario_id",
            "release_id",
            "requirement_id",
            "description",
            "priority",
            "module",
            "mandatory_for_phase5",
        ],
        requirements_rows,
    )
    _write_csv(
        root / "test_cases_master.csv",
        [
            "scenario_id",
            "release_id",
            "test_case_id",
            "title",
            "mapped_requirement_ids",
            "criticality",
            "test_owner",
        ],
        test_cases_rows,
    )
    _write_csv(
        root / "traceability_matrix.csv",
        [
            "scenario_id",
            "release_id",
            "requirement_id",
            "test_case_id",
            "mapping_source",
        ],
        traceability_rows,
    )
    _write_csv(
        root / "test_execution_results.csv",
        [
            "scenario_id",
            "release_id",
            "test_case_id",
            "status",
            "executed",
            "retest_required",
            "retest_completed",
            "executor",
        ],
        execution_rows,
    )
    _write_csv(
        root / "defect_register.csv",
        [
            "scenario_id",
            "release_id",
            "defect_id",
            "title",
            "severity",
            "status",
            "owner",
        ],
        defect_rows,
    )
    _write_csv(
        root / "phase5_release_calendar.csv",
        [
            "release_id",
            "scenario_id",
            "environment",
            "phase5_window_start",
            "phase5_window_end",
            "target_phase5_gate",
        ],
        calendar_rows,
    )

    if include_labels:
        _write_csv(
            root / "phase5_decision_labels.csv",
            [
                "scenario_id",
                "release_id",
                "expected_decision",
                "scenario_type",
                "rationale",
                "triggered_conditions",
                "ambiguity_level",
                "requires_agent4_closure",
            ],
            labels_rows,
        )

    return root


@pytest.fixture
def go_dataset(tmp_path: Path) -> Tuple[Path, str, str]:
    sid = "P5-T001"
    rid = "P5-REL-1.0.0"
    root = _build_dataset(tmp_path, [(sid, rid, "go")], include_labels=True)
    return root, sid, rid


@pytest.fixture
def hold_fail_dataset(tmp_path: Path) -> Tuple[Path, str, str]:
    sid = "P5-T002"
    rid = "P5-REL-1.0.1"
    root = _build_dataset(tmp_path, [(sid, rid, "hold_fail")], include_labels=True)
    return root, sid, rid


def _evaluate_findings(
    dataset_root: Path, scenario_id: str, release_id: str
) -> RuleFindings:
    ingestion = Phase5Ingestion(dataset_root=dataset_root)
    raw = ingestion.ingest(scenario_id=scenario_id, release_id=release_id)
    normalized = normalize_evidence_bundle(raw)
    return Phase5PolicyEngine().evaluate(normalized, environment=raw.environment)


# ---------------------------
# Schema + model tests
# ---------------------------


def test_validate_output_schema_accepts_valid_payload() -> None:
    findings = RuleFindings(findings=tuple())
    output = build_agent5_output(
        scenario_id="P5-T099",
        release_id="P5-REL-9.9.9",
        findings=findings,
        reasons=(
            ReasonItem(
                title="All hard release gates passed",
                detail="No hard gate triggered.",
                rule_code=None,
                evidence=tuple(),
            ),
        ),
        evidence=(
            SourceRef(file_path="synthetic_data/phase5/v1/requirements_master.csv"),
        ),
        summary="GO recommended because no gate triggered.",
        decision_type=DecisionType.DETERMINISTIC,
    )
    valid, errors = validate_output_schema(output.to_dict())
    assert valid is True
    assert errors == []


def test_validate_output_schema_rejects_missing_required_key() -> None:
    payload = {
        "scenario_id": "P5-T100",
        "release_id": "P5-REL-1.0.0",
        # decision missing
        "decision_type": "deterministic",
        "reasons": [],
        "evidence": [],
        "confidence": "high",
        "human_action": "ok",
        "summary": "ok",
        "policy_version": "phase5-policy-v1",
        "timestamp_utc": "2026-01-01T00:00:00+00:00",
        "rule_findings": {},
    }
    valid, errors = validate_output_schema(payload)
    assert valid is False
    assert any("Missing required top-level keys" in e for e in errors)


# ---------------------------
# Deterministic policy tests
# ---------------------------


def test_policy_go_when_all_green(go_dataset: Tuple[Path, str, str]) -> None:
    root, sid, rid = go_dataset
    findings = _evaluate_findings(root, sid, rid)
    assert findings.decision == Decision.GO
    assert findings.hold_required is False
    assert findings.triggered_rule_codes == []


def test_policy_hold_when_mandatory_uncovered(tmp_path: Path) -> None:
    sid = "P5-T010"
    rid = "P5-REL-1.1.0"
    root = _build_dataset(tmp_path, [(sid, rid, "hold_uncovered")], include_labels=True)
    findings = _evaluate_findings(root, sid, rid)
    assert findings.decision == Decision.HOLD
    assert findings.mandatory_requirement_uncovered is True


def test_policy_hold_when_mandatory_failed(
    hold_fail_dataset: Tuple[Path, str, str],
) -> None:
    root, sid, rid = hold_fail_dataset
    findings = _evaluate_findings(root, sid, rid)
    assert findings.decision == Decision.HOLD
    assert findings.mandatory_requirement_failed_or_blocked is True


def test_policy_hold_when_critical_defect_open(tmp_path: Path) -> None:
    sid = "P5-T011"
    rid = "P5-REL-1.1.1"
    root = _build_dataset(tmp_path, [(sid, rid, "hold_critical")], include_labels=True)
    findings = _evaluate_findings(root, sid, rid)
    assert findings.decision == Decision.HOLD
    assert findings.critical_defect_open is True


def test_policy_hold_when_conditional_retest_unmet(tmp_path: Path) -> None:
    sid = "P5-T012"
    rid = "P5-REL-1.1.2"
    root = _build_dataset(
        tmp_path, [(sid, rid, "hold_conditional")], include_labels=True
    )
    findings = _evaluate_findings(root, sid, rid)
    assert findings.decision == Decision.HOLD
    assert findings.conditional_retest_unmet is True


def test_policy_hold_when_agent4_unresolved_unclosed(tmp_path: Path) -> None:
    sid = "P5-T013"
    rid = "P5-REL-1.1.3"
    root = _build_dataset(
        tmp_path, [(sid, rid, "hold_continuity")], include_labels=True
    )
    findings = _evaluate_findings(root, sid, rid)
    assert findings.decision == Decision.HOLD
    assert findings.agent4_unresolved_hard_blocker_unclosed is True


def test_policy_hold_when_required_evidence_incomplete(tmp_path: Path) -> None:
    sid = "P5-T014"
    rid = "P5-REL-1.1.4"
    root = _build_dataset(
        tmp_path, [(sid, rid, "hold_incomplete")], include_labels=True
    )
    findings = _evaluate_findings(root, sid, rid)
    assert findings.decision == Decision.HOLD
    assert findings.test_evidence_incomplete is True


# ---------------------------
# Explanation tests
# ---------------------------


def test_explanation_deterministic_hold_contains_triggered_rules(
    hold_fail_dataset: Tuple[Path, str, str],
) -> None:
    root, sid, rid = hold_fail_dataset
    findings = _evaluate_findings(root, sid, rid)

    ctx = ExplanationContext(
        scenario_id=sid,
        release_id=rid,
        findings=findings,
        evidence_conflict=False,
        evidence_incomplete=False,
    )
    output = build_deterministic_explanation(ctx)
    payload = output.to_dict()

    assert payload["decision"] == "HOLD"
    assert "mandatory_requirement_failed_or_blocked" in payload["summary"]


# ---------------------------
# LangChain pipeline tests
# ---------------------------


def test_langchain_pipeline_single_scenario_matches_label(
    go_dataset: Tuple[Path, str, str],
) -> None:
    root, sid, _ = go_dataset
    pipeline = LangChainAgent5Pipeline(
        config=LCPipelineConfig(
            dataset_root=str(root),
            use_llm_summary=False,
            strict_schema=True,
        ),
        llm_generate=None,
    )

    payload = pipeline.assess_scenario(scenario_id=sid, release_id=None)
    assert payload["decision"] == "GO"
    assert payload["schema_validation"]["valid"] is True

    eval_report = pipeline.evaluate_against_labels(predictions=[payload])
    assert eval_report["accuracy"] == 1.0
    assert eval_report["false_go"] == 0
    assert eval_report["false_hold"] == 0


def test_langchain_pipeline_evaluate_all_two_scenarios(tmp_path: Path) -> None:
    s1 = ("P5-T020", "P5-REL-2.0.0", "go")
    s2 = ("P5-T021", "P5-REL-2.0.1", "hold_fail")
    root = _build_dataset(tmp_path, [s1, s2], include_labels=True)

    pipeline = LangChainAgent5Pipeline(
        config=LCPipelineConfig(
            dataset_root=str(root),
            use_llm_summary=False,
            strict_schema=True,
        ),
        llm_generate=None,
    )

    predictions = pipeline.assess_all_scenarios()
    assert len(predictions) == 2
    assert all(p["schema_validation"]["valid"] is True for p in predictions)

    report = pipeline.evaluate_against_labels(predictions=predictions)
    assert report["total_scenarios"] == 2
    assert report["accuracy"] == 1.0
    assert report["false_go"] == 0
    assert report["false_hold"] == 0


# ---------------------------
# Orchestrator/API tests
# ---------------------------


def test_orchestrator_run_with_label_check(go_dataset: Tuple[Path, str, str]) -> None:
    root, sid, _ = go_dataset
    orchestrator = Agent5LangChainOrchestrator(
        config=Agent5Config(
            dataset_root=str(root),
            use_llm_summary=False,
            strict_schema=True,
        ),
        llm_generate=None,
    )

    payload = orchestrator.run(
        scenario_id=sid,
        check_label=True,
        strict_schema=True,
    )
    assert payload["decision"] == "GO"
    assert payload["schema_validation"]["valid"] is True
    assert payload["evaluation"]["label_check_performed"] is True
    assert payload["evaluation"]["match"] is True


def test_orchestrator_assess_all_scenarios(tmp_path: Path) -> None:
    rows = [
        ("P5-T030", "P5-REL-3.0.0", "go"),
        ("P5-T031", "P5-REL-3.0.1", "hold_critical"),
        ("P5-T032", "P5-REL-3.0.2", "hold_conditional"),
    ]
    root = _build_dataset(tmp_path, rows, include_labels=True)

    orchestrator = Agent5LangChainOrchestrator(
        config=Agent5Config(
            dataset_root=str(root),
            use_llm_summary=False,
            strict_schema=True,
        ),
        llm_generate=None,
    )
    predictions = list(orchestrator.assess_all_scenarios())
    assert len(predictions) == 3

    eval_report = orchestrator.evaluate_against_labels(predictions=predictions)
    assert eval_report["accuracy"] == 1.0
    assert eval_report["evaluated_scenarios"] == 3


# ---------------------------
# Tier-2 style behavior checks
# ---------------------------


@pytest.mark.parametrize(
    "kind,expected_decision",
    [
        ("go", "GO"),
        ("hold_uncovered", "HOLD"),
        ("hold_fail", "HOLD"),
        ("hold_critical", "HOLD"),
        ("hold_conditional", "HOLD"),
        ("hold_continuity", "HOLD"),
    ],
)
def test_tier2_core_scenario_matrix(
    tmp_path: Path, kind: str, expected_decision: str
) -> None:
    sid = f"P5-TM-{kind}"
    rid = "P5-REL-4.0.0"
    root = _build_dataset(tmp_path, [(sid, rid, kind)], include_labels=True)

    pipeline = LangChainAgent5Pipeline(
        config=LCPipelineConfig(
            dataset_root=str(root),
            use_llm_summary=False,
            strict_schema=True,
        ),
        llm_generate=None,
    )
    payload = pipeline.assess_scenario(scenario_id=sid, release_id=rid)
    assert payload["decision"] == expected_decision
    assert payload["schema_validation"]["valid"] is True
    assert "rule_findings" in payload
    assert "triggered_rule_codes" in payload["rule_findings"]
