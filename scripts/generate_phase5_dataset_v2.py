#!/usr/bin/env python3
"""
Phase 5 v2 synthetic dataset generator with realism controls.

This generator creates a realism-oriented, policy-consistent dataset for Agent 5
under `synthetic_data/phase5/v2` by default.

Output files:
- requirements_master.csv
- test_cases_master.csv
- traceability_matrix.csv
- test_execution_results.csv
- defect_register.csv
- phase5_decision_labels.csv
- phase5_release_calendar.csv
- scenario_taxonomy.csv
- phase5_manifest.json
- test_analysis_emails/<scenario_id>.txt
- agent4_context/<scenario_id>.json (optional per scenario)

Design constraints:
- deterministic reproducibility by seed
- hard-gate label consistency
- controlled ambiguity/conflict injection
- coverage across all hard HOLD gate classes
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

HARD_GATE_CODES = {
    "mandatory_requirement_uncovered",
    "mandatory_requirement_failed_or_blocked",
    "critical_defect_open",
    "test_evidence_incomplete",
    "conditional_retest_unmet",
    "agent4_unresolved_hard_blocker_unclosed",
}


@dataclass(frozen=True)
class ScenarioBlueprint:
    scenario_type: str
    primary_class: str
    expected_bias: str  # "GO" or "HOLD"
    default_ambiguity: str  # low|medium|high


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Phase 5 v2 dataset with realism controls."
    )
    parser.add_argument(
        "--output-dir",
        default="synthetic_data/phase5/v2",
        help="Output dataset directory (default: synthetic_data/phase5/v2)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1042,
        help="Random seed for reproducibility (default: 1042)",
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=72,
        help="Total number of scenarios to generate (default: 72)",
    )
    parser.add_argument(
        "--ambiguity-rate",
        type=float,
        default=0.35,
        help="Base rate for medium/high ambiguity injection [0..1] (default: 0.35)",
    )
    parser.add_argument(
        "--high-ambiguity-rate",
        type=float,
        default=0.18,
        help="Rate for high-ambiguity override [0..1] (default: 0.18)",
    )
    parser.add_argument(
        "--missing-field-rate",
        type=float,
        default=0.10,
        help="Rate for optional-field omissions [0..1] (default: 0.10)",
    )
    parser.add_argument(
        "--conflict-rate",
        type=float,
        default=0.15,
        help="Rate for documentary conflict injection [0..1] (default: 0.15)",
    )
    parser.add_argument(
        "--continuity-cases-rate",
        type=float,
        default=0.20,
        help="Approximate share of scenarios with Agent4 continuity context [0..1] (default: 0.20)",
    )
    parser.add_argument(
        "--alias-intensity",
        type=float,
        default=0.25,
        help="Rate for terminology/alias drift in optional fields [0..1] (default: 0.25)",
    )
    parser.add_argument(
        "--go-hold-ratio",
        type=float,
        default=0.38,
        help="Target GO share in random fill scenarios [0..1] (default: 0.38)",
    )
    return parser.parse_args()


def clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def write_csv(
    path: Path, rows: Sequence[Dict[str, str]], fieldnames: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def scenario_id_from_index(idx: int) -> str:
    return "P5V2-{0:03d}".format(idx)


def release_id_from_index(idx: int) -> str:
    batch = 1 + ((idx - 1) // 12)
    patch = (idx - 1) % 6
    return "P5-REL-{0}.{1}.{2}".format(2, batch, patch)


def choose_ambiguity(
    rng: random.Random,
    base: str,
    ambiguity_rate: float,
    high_ambiguity_rate: float,
) -> str:
    if rng.random() < high_ambiguity_rate:
        return "high"
    if rng.random() < ambiguity_rate:
        return "medium" if rng.random() < 0.65 else "high"
    return base


def split_multi(value: str) -> List[str]:
    text = (value or "").strip().replace("|", ",").replace(";", ",")
    if not text:
        return []
    return [p.strip() for p in text.split(",") if p.strip()]


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def normalize_status(status: str) -> str:
    s = (status or "").strip().upper()
    if s in {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "CONDITIONAL_UNMET"}:
        return s
    return "UNKNOWN"


def build_base_requirements(sid: str, rid: str) -> List[Dict[str, str]]:
    return [
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-001",
            "description": "Mandatory user authentication regression check.",
            "priority": "HIGH",
            "module": "auth-service",
            "mandatory_for_phase5": "true",
            "domain": "security",
            "traceability_tag": "MUST",
            "module_alias_raw": "Authentication Core",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-002",
            "description": "Mandatory payment transaction idempotency validation.",
            "priority": "HIGH",
            "module": "payment-core",
            "mandatory_for_phase5": "true",
            "domain": "transaction",
            "traceability_tag": "MUST",
            "module_alias_raw": "Txn Engine",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-003",
            "description": "Mandatory order reconciliation pipeline validation.",
            "priority": "MEDIUM",
            "module": "order-pipeline",
            "mandatory_for_phase5": "true",
            "domain": "fulfillment",
            "traceability_tag": "MUST",
            "module_alias_raw": "Reconciliation Flow",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-004",
            "description": "Mandatory audit-log persistence verification.",
            "priority": "MEDIUM",
            "module": "audit-store",
            "mandatory_for_phase5": "true",
            "domain": "compliance",
            "traceability_tag": "MUST",
            "module_alias_raw": "Audit Ledger",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-005",
            "description": "Optional reporting UI smoke check.",
            "priority": "LOW",
            "module": "reporting-ui",
            "mandatory_for_phase5": "false",
            "domain": "ui",
            "traceability_tag": "OPTIONAL",
            "module_alias_raw": "BI Frontend",
        },
    ]


def build_base_test_cases(sid: str, rid: str) -> List[Dict[str, str]]:
    return [
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-001",
            "title": "Auth flow regression",
            "mapped_requirement_ids": "REQ-P5-001",
            "criticality": "HIGH",
            "test_owner": "qa.auth",
            "test_family_alias": "Identity Regression Pack",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-002",
            "title": "Payment idempotency checks",
            "mapped_requirement_ids": "REQ-P5-002",
            "criticality": "HIGH",
            "test_owner": "qa.payment",
            "test_family_alias": "Txn Resilience Pack",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-003",
            "title": "Order reconciliation consistency",
            "mapped_requirement_ids": "REQ-P5-003",
            "criticality": "MEDIUM",
            "test_owner": "qa.order",
            "test_family_alias": "Order Integrity Pack",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-004",
            "title": "Audit log persistence",
            "mapped_requirement_ids": "REQ-P5-004",
            "criticality": "MEDIUM",
            "test_owner": "qa.compliance",
            "test_family_alias": "Compliance Persistence Pack",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-005",
            "title": "Reporting UI smoke",
            "mapped_requirement_ids": "REQ-P5-005",
            "criticality": "LOW",
            "test_owner": "qa.ui",
            "test_family_alias": "UI Sanity Pack",
        },
    ]


def build_base_traceability(sid: str, rid: str) -> List[Dict[str, str]]:
    return [
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-001",
            "test_case_id": "TC-P5-001",
            "mapping_source": "traceability_workbook",
            "mapping_confidence": "high",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-002",
            "test_case_id": "TC-P5-002",
            "mapping_source": "traceability_workbook",
            "mapping_confidence": "high",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-003",
            "test_case_id": "TC-P5-003",
            "mapping_source": "traceability_workbook",
            "mapping_confidence": "high",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-004",
            "test_case_id": "TC-P5-004",
            "mapping_source": "traceability_workbook",
            "mapping_confidence": "high",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-005",
            "test_case_id": "TC-P5-005",
            "mapping_source": "traceability_workbook",
            "mapping_confidence": "medium",
        },
    ]


def build_base_executions(sid: str, rid: str) -> List[Dict[str, str]]:
    rows = []
    for tc_id, owner in [
        ("TC-P5-001", "qa.auth"),
        ("TC-P5-002", "qa.payment"),
        ("TC-P5-003", "qa.order"),
        ("TC-P5-004", "qa.compliance"),
        ("TC-P5-005", "qa.ui"),
    ]:
        rows.append(
            {
                "scenario_id": sid,
                "release_id": rid,
                "test_case_id": tc_id,
                "status": "PASS",
                "executed": "true",
                "retest_required": "false",
                "retest_completed": "false",
                "executor": owner,
                "execution_ts": "2026-06-01T10:00:00+00:00",
                "report_version": "v2.0",
                "narrative_note": "",
            }
        )
    return rows


def build_base_defects(sid: str, rid: str) -> List[Dict[str, str]]:
    return [
        {
            "scenario_id": sid,
            "release_id": rid,
            "defect_id": "DF-P5-{0}".format(sid.split("-")[-1]),
            "title": "Minor tooltip formatting issue",
            "severity": "LOW",
            "status": "CLOSED",
            "owner": "dev.ui",
            "source_system": "jira",
            "closure_note": "fixed in UI patch",
        }
    ]


def set_execution_status(
    executions: List[Dict[str, str]],
    tc_id: str,
    status: str,
    *,
    retest_required: Optional[bool] = None,
    retest_completed: Optional[bool] = None,
    note: str = "",
) -> None:
    for row in executions:
        if row.get("test_case_id") != tc_id:
            continue
        normalized = normalize_status(status)
        row["status"] = normalized
        row["executed"] = bool_text(normalized != "NOT_RUN")
        if retest_required is not None:
            row["retest_required"] = bool_text(retest_required)
        if retest_completed is not None:
            row["retest_completed"] = bool_text(retest_completed)
        if note:
            row["narrative_note"] = note
        return


def remove_trace_for_requirement(
    traceability: List[Dict[str, str]],
    requirement_id: str,
) -> None:
    traceability[:] = [
        r for r in traceability if r.get("requirement_id") != requirement_id
    ]


def remove_execution_for_testcase(
    executions: List[Dict[str, str]],
    test_case_id: str,
) -> None:
    executions[:] = [r for r in executions if r.get("test_case_id") != test_case_id]


def add_open_defect(
    defects: List[Dict[str, str]],
    sid: str,
    rid: str,
    defect_id_suffix: str,
    severity: str,
    title: str,
    owner: str,
) -> None:
    defects.append(
        {
            "scenario_id": sid,
            "release_id": rid,
            "defect_id": "DF-P5-{0}-{1}".format(defect_id_suffix, sid.split("-")[-1]),
            "title": title,
            "severity": severity,
            "status": "OPEN",
            "owner": owner,
            "source_system": "jira",
            "closure_note": "",
        }
    )


def maybe_apply_alias_drift(
    rng: random.Random,
    alias_intensity: float,
    requirements: List[Dict[str, str]],
    test_cases: List[Dict[str, str]],
    traceability: List[Dict[str, str]],
) -> List[str]:
    modifiers: List[str] = []

    if rng.random() >= alias_intensity:
        return modifiers

    modifiers.append("alias_drift")

    req_alias_map = {
        "REQ-P5-001": "R-AUTH-01",
        "REQ-P5-002": "R-TXN-02",
        "REQ-P5-003": "R-ORD-03",
        "REQ-P5-004": "R-AUD-04",
        "REQ-P5-005": "R-UI-05",
    }

    # Apply drift to optional descriptive fields only (keep canonical keys intact).
    for req in requirements:
        rid = req.get("requirement_id", "")
        alias = req_alias_map.get(rid, "")
        if alias:
            req["traceability_tag"] = (
                alias if rng.random() < 0.6 else req["traceability_tag"]
            )

    for tc in test_cases:
        mapped = split_multi(tc.get("mapped_requirement_ids", ""))
        if not mapped:
            continue
        if rng.random() < 0.5:
            alias_mapped = [req_alias_map.get(x, x) for x in mapped]
            tc["test_family_alias"] = "alias_map:" + ",".join(alias_mapped)

    # Add optional alias marker to trace rows.
    for tr in traceability:
        if rng.random() < 0.5:
            req = tr.get("requirement_id", "")
            tr["mapping_confidence"] = (
                "medium"
                if req in req_alias_map
                else tr.get("mapping_confidence", "high")
            )

    return modifiers


def maybe_drop_optional_fields(
    rng: random.Random,
    missing_field_rate: float,
    requirements: List[Dict[str, str]],
    test_cases: List[Dict[str, str]],
    traceability: List[Dict[str, str]],
    executions: List[Dict[str, str]],
    defects: List[Dict[str, str]],
) -> List[str]:
    modifiers: List[str] = []
    any_drop = False

    for row in requirements:
        if rng.random() < missing_field_rate:
            row["domain"] = ""
            any_drop = True
        if rng.random() < missing_field_rate:
            row["module_alias_raw"] = ""
            any_drop = True

    for row in test_cases:
        if rng.random() < missing_field_rate:
            row["test_owner"] = ""
            any_drop = True
        if rng.random() < missing_field_rate:
            row["test_family_alias"] = ""
            any_drop = True

    for row in traceability:
        if rng.random() < missing_field_rate:
            row["mapping_confidence"] = ""
            any_drop = True

    for row in executions:
        if rng.random() < missing_field_rate:
            row["executor"] = ""
            any_drop = True
        if rng.random() < missing_field_rate:
            row["narrative_note"] = ""
            any_drop = True

    for row in defects:
        if rng.random() < missing_field_rate:
            row["closure_note"] = ""
            any_drop = True

    if any_drop:
        modifiers.append("partial_missing_fields")
    return modifiers


def maybe_inject_timestamp_skew(
    rng: random.Random,
    ambiguity_level: str,
    executions: List[Dict[str, str]],
) -> List[str]:
    modifiers: List[str] = []
    if ambiguity_level not in {"medium", "high"}:
        return modifiers
    if rng.random() > 0.35:
        return modifiers

    modifiers.append("timestamp_skew")
    for row in executions:
        if row.get("test_case_id") == "TC-P5-005":
            row["execution_ts"] = "2026-05-29T17:30:00+00:00"
            row["report_version"] = "v1.8-stale"
            row["narrative_note"] = (
                row.get("narrative_note", "") + " stale-report-reference"
            ).strip()
            break
    return modifiers


def maybe_inject_thread_fragmentation(
    rng: random.Random,
    ambiguity_level: str,
) -> List[str]:
    if ambiguity_level == "high" and rng.random() < 0.45:
        return ["thread_fragmentation"]
    if ambiguity_level == "medium" and rng.random() < 0.15:
        return ["thread_fragmentation"]
    return []


def maybe_inject_narrative_softness(
    rng: random.Random,
    ambiguity_level: str,
) -> List[str]:
    if ambiguity_level in {"medium", "high"} and rng.random() < 0.50:
        return ["narrative_softness"]
    return []


def apply_scenario_mutations(
    bp: ScenarioBlueprint,
    sid: str,
    rid: str,
    rng: random.Random,
    continuity_case: bool,
    requirements: List[Dict[str, str]],
    test_cases: List[Dict[str, str]],
    traceability: List[Dict[str, str]],
    executions: List[Dict[str, str]],
    defects: List[Dict[str, str]],
) -> Optional[Dict[str, object]]:
    """
    Apply deterministic scenario-class mutations.
    Returns optional agent4 context.
    """
    agent4_context: Optional[Dict[str, object]] = None

    st = bp.scenario_type
    if st == "CLEAR_GO":
        # baseline already GO
        pass

    elif st == "MIXED_SIGNAL_GO":
        # only non-mandatory noise
        set_execution_status(
            executions,
            "TC-P5-005",
            "BLOCKED",
            retest_required=False,
            retest_completed=False,
            note="non-blocking UI environment instability",
        )
        add_open_defect(
            defects,
            sid=sid,
            rid=rid,
            defect_id_suffix="LOWUI",
            severity="LOW",
            title="Known low-priority UI spacing issue",
            owner="dev.ui",
        )

    elif st == "HOLD_UNCOVERED_MANDATORY":
        remove_trace_for_requirement(traceability, "REQ-P5-002")
        remove_execution_for_testcase(executions, "TC-P5-002")

    elif st == "HOLD_FAILED_MANDATORY":
        set_execution_status(
            executions,
            "TC-P5-001",
            "FAIL",
            retest_required=False,
            retest_completed=False,
            note="auth regression still failing",
        )

    elif st == "HOLD_BLOCKED_MANDATORY":
        set_execution_status(
            executions,
            "TC-P5-003",
            "BLOCKED",
            retest_required=False,
            retest_completed=False,
            note="environment dependency unavailable",
        )

    elif st == "HOLD_OPEN_CRITICAL_DEFECT":
        add_open_defect(
            defects,
            sid=sid,
            rid=rid,
            defect_id_suffix="CRIT",
            severity="CRITICAL",
            title="Critical deadlock in payment commit path",
            owner="dev.payment",
        )

    elif st == "HOLD_UNMET_RETEST":
        set_execution_status(
            executions,
            "TC-P5-004",
            "CONDITIONAL_UNMET",
            retest_required=True,
            retest_completed=False,
            note="compliance retest pending formal rerun",
        )

    elif st == "HOLD_AGENT4_CONTINUITY":
        agent4_context = {
            "agent4_decision": "HOLD",
            "agent4_triggered_rules": ["mandatory_version_mismatch"],
            "unresolved_conditions": ["backend_version_alignment_unclosed"],
            "closure_confirmed": False,
            "confidence": "medium",
            "summary": "Agent4 unresolved blocker was not explicitly closed at phase boundary.",
        }

    elif st == "HOLD_EVIDENCE_INCOMPLETE":
        # force incompleteness while keeping other structured files present
        traceability[:] = [
            r for r in traceability if r.get("requirement_id") == "REQ-P5-005"
        ]

    elif st == "MIXED_SIGNAL_HOLD_MULTI":
        set_execution_status(
            executions,
            "TC-P5-001",
            "FAIL",
            retest_required=False,
            retest_completed=False,
            note="intermittent auth failure persisted",
        )
        add_open_defect(
            defects,
            sid=sid,
            rid=rid,
            defect_id_suffix="HIGH",
            severity="HIGH",
            title="High severity timeout in auth-token propagation",
            owner="dev.auth",
        )

    # Optional continuity overlays for scenarios that are not explicit continuity-hold.
    if continuity_case and st != "HOLD_AGENT4_CONTINUITY":
        if rng.random() < 0.55:
            agent4_context = {
                "agent4_decision": "HOLD",
                "agent4_triggered_rules": ["open_blocker_email"],
                "unresolved_conditions": ["pending_blocker_closure_note"],
                "closure_confirmed": True,
                "confidence": "medium",
                "summary": "Agent4 blocker was explicitly closed in Phase5 evidence.",
            }
        else:
            agent4_context = {
                "agent4_decision": "GO",
                "agent4_triggered_rules": [],
                "unresolved_conditions": [],
                "closure_confirmed": True,
                "confidence": "high",
                "summary": "Agent4 transition was clean.",
            }

    return agent4_context


def compute_expected_flags(
    requirements: Sequence[Dict[str, str]],
    test_cases: Sequence[Dict[str, str]],
    traceability: Sequence[Dict[str, str]],
    executions: Sequence[Dict[str, str]],
    defects: Sequence[Dict[str, str]],
    agent4_context: Optional[Dict[str, object]],
) -> Dict[str, bool]:
    mandatory_reqs = [
        r
        for r in requirements
        if str(r.get("mandatory_for_phase5", "")).strip().lower() == "true"
    ]

    req_to_tc: Dict[str, set] = {}
    for row in traceability:
        req = str(row.get("requirement_id", "")).strip()
        tc = str(row.get("test_case_id", "")).strip()
        if req and tc:
            req_to_tc.setdefault(req, set()).add(tc)

    for tc in test_cases:
        tc_id = str(tc.get("test_case_id", "")).strip()
        mapped = split_multi(str(tc.get("mapped_requirement_ids", "")))
        if not tc_id:
            continue
        for req in mapped:
            req_to_tc.setdefault(req, set()).add(tc_id)

    exec_by_tc: Dict[str, List[Dict[str, str]]] = {}
    for ex in executions:
        tc_id = str(ex.get("test_case_id", "")).strip()
        if tc_id:
            exec_by_tc.setdefault(tc_id, []).append(ex)

    mandatory_uncovered = False
    mandatory_failed_or_blocked = False

    for req in mandatory_reqs:
        req_id = str(req.get("requirement_id", "")).strip()
        mapped_tcs = req_to_tc.get(req_id, set())
        if not mapped_tcs:
            mandatory_uncovered = True
            continue

        mapped_execs: List[Dict[str, str]] = []
        for tc_id in mapped_tcs:
            mapped_execs.extend(exec_by_tc.get(tc_id, []))

        executed_any = False
        for ex in mapped_execs:
            status = normalize_status(str(ex.get("status", "")))
            executed_raw = str(ex.get("executed", "")).strip().lower()
            executed = executed_raw in {"1", "true", "yes", "y", "on"} or status in {
                "PASS",
                "FAIL",
                "BLOCKED",
                "CONDITIONAL_UNMET",
            }
            if executed:
                executed_any = True
            if status in {"FAIL", "BLOCKED"}:
                mandatory_failed_or_blocked = True

        if not executed_any:
            mandatory_uncovered = True

    critical_defect_open = False
    for d in defects:
        sev = str(d.get("severity", "")).strip().upper()
        st = str(d.get("status", "")).strip().upper()
        if sev in {"CRITICAL", "HIGH"} and st in {
            "OPEN",
            "NEW",
            "REOPENED",
            "IN PROGRESS",
        }:
            critical_defect_open = True
            break

    conditional_retest_unmet = False
    for ex in executions:
        status = normalize_status(str(ex.get("status", "")))
        rr = str(ex.get("retest_required", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        rc = str(ex.get("retest_completed", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        if status == "CONDITIONAL_UNMET" or (rr and not rc):
            conditional_retest_unmet = True
            break

    agent4_unresolved_hard_blocker_unclosed = False
    if isinstance(agent4_context, dict):
        decision = (
            str(
                agent4_context.get(
                    "agent4_decision", agent4_context.get("decision", "")
                )
            )
            .strip()
            .upper()
        )
        unresolved = agent4_context.get("unresolved_conditions", [])
        triggered = agent4_context.get(
            "agent4_triggered_rules", agent4_context.get("triggered_rules", [])
        )
        closure_confirmed = bool(agent4_context.get("closure_confirmed", False))

        unresolved_list: List[str] = []
        if isinstance(unresolved, list):
            unresolved_list = [str(x).strip() for x in unresolved if str(x).strip()]
        elif isinstance(unresolved, str):
            unresolved_list = [
                p.strip() for p in unresolved.replace("|", ",").split(",") if p.strip()
            ]

        triggered_list: List[str] = []
        if isinstance(triggered, list):
            triggered_list = [str(x).strip() for x in triggered if str(x).strip()]
        elif isinstance(triggered, str):
            triggered_list = [
                p.strip() for p in triggered.replace("|", ",").split(",") if p.strip()
            ]

        if decision == "HOLD":
            if unresolved_list and not closure_confirmed:
                agent4_unresolved_hard_blocker_unclosed = True
            elif not unresolved_list and triggered_list and not closure_confirmed:
                agent4_unresolved_hard_blocker_unclosed = True

    evidence_incomplete = False
    if (
        not requirements
        or not test_cases
        or not traceability
        or not executions
        or not defects
    ):
        evidence_incomplete = True
    if mandatory_uncovered:
        evidence_incomplete = True

    return {
        "mandatory_requirement_uncovered": mandatory_uncovered,
        "mandatory_requirement_failed_or_blocked": mandatory_failed_or_blocked,
        "critical_defect_open": critical_defect_open,
        "test_evidence_incomplete": evidence_incomplete,
        "conditional_retest_unmet": conditional_retest_unmet,
        "agent4_unresolved_hard_blocker_unclosed": agent4_unresolved_hard_blocker_unclosed,
    }


def choose_blueprints(
    rng: random.Random,
    scenario_count: int,
    go_hold_ratio: float,
) -> List[ScenarioBlueprint]:
    must_have = [
        ScenarioBlueprint("CLEAR_GO", "CLEAN_GO", "GO", "low"),
        ScenarioBlueprint(
            "HOLD_UNCOVERED_MANDATORY",
            "CLEAR_HOLD_SINGLE_GATE",
            "HOLD",
            "low",
        ),
        ScenarioBlueprint(
            "HOLD_FAILED_MANDATORY",
            "CLEAR_HOLD_SINGLE_GATE",
            "HOLD",
            "low",
        ),
        ScenarioBlueprint(
            "HOLD_BLOCKED_MANDATORY",
            "CLEAR_HOLD_SINGLE_GATE",
            "HOLD",
            "low",
        ),
        ScenarioBlueprint(
            "HOLD_OPEN_CRITICAL_DEFECT",
            "CLEAR_HOLD_SINGLE_GATE",
            "HOLD",
            "low",
        ),
        ScenarioBlueprint(
            "HOLD_UNMET_RETEST",
            "CONDITIONAL_GOVERNANCE_HOLD",
            "HOLD",
            "medium",
        ),
        ScenarioBlueprint(
            "HOLD_AGENT4_CONTINUITY",
            "CONFLICTED_EVIDENCE_HOLD",
            "HOLD",
            "medium",
        ),
        ScenarioBlueprint("MIXED_SIGNAL_GO", "MIXED_NON_BLOCKING_GO", "GO", "medium"),
        ScenarioBlueprint(
            "MIXED_SIGNAL_HOLD_MULTI",
            "CLEAR_HOLD_MULTI_GATE",
            "HOLD",
            "medium",
        ),
        ScenarioBlueprint(
            "HOLD_EVIDENCE_INCOMPLETE",
            "TRACEABILITY_GAP_HOLD",
            "HOLD",
            "medium",
        ),
    ]

    if scenario_count <= len(must_have):
        return must_have[:scenario_count]

    out = list(must_have)

    go_types = [
        ScenarioBlueprint("CLEAR_GO", "CLEAN_GO", "GO", "low"),
        ScenarioBlueprint("MIXED_SIGNAL_GO", "MIXED_NON_BLOCKING_GO", "GO", "medium"),
    ]
    hold_types = [
        ScenarioBlueprint(
            "HOLD_UNCOVERED_MANDATORY",
            "CLEAR_HOLD_SINGLE_GATE",
            "HOLD",
            "low",
        ),
        ScenarioBlueprint(
            "HOLD_FAILED_MANDATORY",
            "CLEAR_HOLD_SINGLE_GATE",
            "HOLD",
            "low",
        ),
        ScenarioBlueprint(
            "HOLD_BLOCKED_MANDATORY",
            "CLEAR_HOLD_SINGLE_GATE",
            "HOLD",
            "low",
        ),
        ScenarioBlueprint(
            "HOLD_OPEN_CRITICAL_DEFECT",
            "CLEAR_HOLD_SINGLE_GATE",
            "HOLD",
            "low",
        ),
        ScenarioBlueprint(
            "HOLD_UNMET_RETEST",
            "CONDITIONAL_GOVERNANCE_HOLD",
            "HOLD",
            "medium",
        ),
        ScenarioBlueprint(
            "HOLD_AGENT4_CONTINUITY",
            "CONFLICTED_EVIDENCE_HOLD",
            "HOLD",
            "medium",
        ),
        ScenarioBlueprint(
            "MIXED_SIGNAL_HOLD_MULTI",
            "MIXED_BLOCKING_HOLD",
            "HOLD",
            "medium",
        ),
        ScenarioBlueprint(
            "HOLD_EVIDENCE_INCOMPLETE",
            "TRACEABILITY_GAP_HOLD",
            "HOLD",
            "medium",
        ),
    ]

    while len(out) < scenario_count:
        if rng.random() < go_hold_ratio:
            out.append(rng.choice(go_types))
        else:
            out.append(rng.choice(hold_types))

    return out


def build_rationale(triggered: Sequence[str], primary_class: str) -> str:
    if not triggered:
        return "No hard Phase 5 gate triggered; mandatory scope and closure evidence are sufficient."
    return "HOLD due to hard-gate triggers ({0}) under class {1}.".format(
        ", ".join(triggered),
        primary_class,
    )


def build_email_text(
    sid: str,
    rid: str,
    scenario_type: str,
    expected_decision: str,
    ambiguity_level: str,
    triggered: Sequence[str],
    conflict_injected: bool,
    modifiers: Sequence[str],
) -> str:
    lines: List[str] = []
    lines.append("Subject: [Phase5] Test analysis thread for {0}".format(rid))
    lines.append("Scenario: {0}".format(sid))
    lines.append("Date: {0}".format(utc_now_iso()))
    lines.append("")
    lines.append("Context")
    lines.append("- scenario_type: {0}".format(scenario_type))
    lines.append("- ambiguity_level: {0}".format(ambiguity_level))
    if modifiers:
        lines.append("- modifiers: {0}".format("|".join(modifiers)))
    lines.append("")

    if expected_decision == "GO":
        lines.append(
            "Current evidence suggests mandatory checks are complete and non-blocking."
        )
        lines.append("No critical/high unresolved issues remain in formal registers.")
    else:
        lines.append(
            "Current evidence indicates one or more hard gates remain unresolved."
        )
        lines.append("- triggered_conditions: {0}".format(", ".join(triggered)))

    if "narrative_softness" in modifiers:
        lines.append("")
        lines.append(
            "Narrative note: issue appears resolved locally, pending formal workflow updates."
        )

    if "thread_fragmentation" in modifiers:
        lines.append("")
        lines.append("Thread fragment A: validation looked clean in one subsystem.")
        lines.append(
            "Thread fragment B: closure artifact was still pending synchronization."
        )

    if ambiguity_level in {"medium", "high"}:
        lines.append("")
        lines.append(
            "Additional remark: terminology differed across teams (pass-with-remarks vs acceptable-risk)."
        )

    if conflict_injected:
        lines.append("")
        lines.append("Potential conflict:")
        lines.append(
            "An informal note claims closure, while official artifacts remain partially out of sync."
        )

    lines.append("")
    lines.append("End of message.")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()

    seed = int(args.seed)
    scenario_count = max(1, int(args.scenario_count))
    ambiguity_rate = clamp01(float(args.ambiguity_rate))
    high_ambiguity_rate = clamp01(float(args.high_ambiguity_rate))
    missing_field_rate = clamp01(float(args.missing_field_rate))
    conflict_rate = clamp01(float(args.conflict_rate))
    continuity_rate = clamp01(float(args.continuity_cases_rate))
    alias_intensity = clamp01(float(args.alias_intensity))
    go_hold_ratio = clamp01(float(args.go_hold_ratio))

    rng = random.Random(seed)

    root = Path(args.output_dir)
    emails_dir = root / "test_analysis_emails"
    a4_ctx_dir = root / "agent4_context"
    root.mkdir(parents=True, exist_ok=True)
    emails_dir.mkdir(parents=True, exist_ok=True)
    a4_ctx_dir.mkdir(parents=True, exist_ok=True)

    blueprints = choose_blueprints(rng, scenario_count, go_hold_ratio)

    requirements_rows: List[Dict[str, str]] = []
    test_cases_rows: List[Dict[str, str]] = []
    traceability_rows: List[Dict[str, str]] = []
    execution_rows: List[Dict[str, str]] = []
    defect_rows: List[Dict[str, str]] = []
    labels_rows: List[Dict[str, str]] = []
    calendar_rows: List[Dict[str, str]] = []
    taxonomy_rows: List[Dict[str, str]] = []

    continuity_case_count = 0
    go_count = 0
    hold_count = 0
    gate_coverage: Dict[str, int] = {k: 0 for k in HARD_GATE_CODES}
    class_coverage: Dict[str, int] = {}

    for idx, bp in enumerate(blueprints, start=1):
        sid = scenario_id_from_index(idx)
        rid = release_id_from_index(idx)
        env = "TEST"

        requirements = build_base_requirements(sid, rid)
        test_cases = build_base_test_cases(sid, rid)
        traceability = build_base_traceability(sid, rid)
        executions = build_base_executions(sid, rid)
        defects = build_base_defects(sid, rid)

        ambiguity_level = choose_ambiguity(
            rng,
            bp.default_ambiguity,
            ambiguity_rate=ambiguity_rate,
            high_ambiguity_rate=high_ambiguity_rate,
        )

        continuity_case = rng.random() < continuity_rate
        if continuity_case:
            continuity_case_count += 1

        agent4_context = apply_scenario_mutations(
            bp=bp,
            sid=sid,
            rid=rid,
            rng=rng,
            continuity_case=continuity_case,
            requirements=requirements,
            test_cases=test_cases,
            traceability=traceability,
            executions=executions,
            defects=defects,
        )

        secondary_modifiers: List[str] = []
        secondary_modifiers.extend(
            maybe_apply_alias_drift(
                rng=rng,
                alias_intensity=alias_intensity,
                requirements=requirements,
                test_cases=test_cases,
                traceability=traceability,
            )
        )
        secondary_modifiers.extend(
            maybe_drop_optional_fields(
                rng=rng,
                missing_field_rate=missing_field_rate,
                requirements=requirements,
                test_cases=test_cases,
                traceability=traceability,
                executions=executions,
                defects=defects,
            )
        )
        secondary_modifiers.extend(
            maybe_inject_timestamp_skew(
                rng=rng,
                ambiguity_level=ambiguity_level,
                executions=executions,
            )
        )
        secondary_modifiers.extend(
            maybe_inject_thread_fragmentation(rng, ambiguity_level)
        )
        secondary_modifiers.extend(
            maybe_inject_narrative_softness(rng, ambiguity_level)
        )

        # De-duplicate modifier list while preserving order.
        seen_mod = set()
        dedup_modifiers: List[str] = []
        for m in secondary_modifiers:
            if m in seen_mod:
                continue
            seen_mod.add(m)
            dedup_modifiers.append(m)
        secondary_modifiers = dedup_modifiers

        flags = compute_expected_flags(
            requirements=requirements,
            test_cases=test_cases,
            traceability=traceability,
            executions=executions,
            defects=defects,
            agent4_context=agent4_context,
        )
        triggered = sorted([k for k, v in flags.items() if v])

        expected_decision = "HOLD" if triggered else "GO"
        if expected_decision == "GO":
            go_count += 1
        else:
            hold_count += 1

        for code in triggered:
            gate_coverage[code] = gate_coverage.get(code, 0) + 1

        class_coverage[bp.primary_class] = class_coverage.get(bp.primary_class, 0) + 1

        conflict_injected = rng.random() < conflict_rate
        if conflict_injected:
            if "narrative_softness" not in secondary_modifiers:
                secondary_modifiers.append("narrative_softness")

        rationale = build_rationale(triggered, bp.primary_class)

        labels_rows.append(
            {
                "scenario_id": sid,
                "release_id": rid,
                "expected_decision": expected_decision,
                "scenario_type": bp.scenario_type,
                "rationale": rationale,
                "triggered_conditions": "|".join(triggered),
                "ambiguity_level": ambiguity_level,
                "requires_agent4_closure": bool_text(
                    "agent4_unresolved_hard_blocker_unclosed" in triggered
                ),
            }
        )

        taxonomy_rows.append(
            {
                "scenario_id": sid,
                "release_id": rid,
                "primary_class": bp.primary_class,
                "secondary_modifiers": "|".join(secondary_modifiers),
                "ambiguity_level": ambiguity_level,
                "expected_decision": expected_decision,
            }
        )

        calendar_rows.append(
            {
                "release_id": rid,
                "scenario_id": sid,
                "environment": env,
                "phase5_window_start": "2026-06-01T09:00:00+00:00",
                "phase5_window_end": "2026-06-02T18:00:00+00:00",
                "target_phase5_gate": "phase5_test_analysis",
            }
        )

        email_text = build_email_text(
            sid=sid,
            rid=rid,
            scenario_type=bp.scenario_type,
            expected_decision=expected_decision,
            ambiguity_level=ambiguity_level,
            triggered=triggered,
            conflict_injected=conflict_injected,
            modifiers=secondary_modifiers,
        )
        (emails_dir / "{0}.txt".format(sid)).write_text(email_text, encoding="utf-8")

        if agent4_context is not None:
            (a4_ctx_dir / "{0}.json".format(sid)).write_text(
                json.dumps(agent4_context, indent=2) + "\n",
                encoding="utf-8",
            )

        requirements_rows.extend(requirements)
        test_cases_rows.extend(test_cases)
        traceability_rows.extend(traceability)
        execution_rows.extend(executions)
        defect_rows.extend(defects)

    # ------------------------------------------------------------------
    # Write files
    # ------------------------------------------------------------------
    write_csv(
        root / "requirements_master.csv",
        requirements_rows,
        [
            "scenario_id",
            "release_id",
            "requirement_id",
            "description",
            "priority",
            "module",
            "mandatory_for_phase5",
            "domain",
            "traceability_tag",
            "module_alias_raw",
        ],
    )

    write_csv(
        root / "test_cases_master.csv",
        test_cases_rows,
        [
            "scenario_id",
            "release_id",
            "test_case_id",
            "title",
            "mapped_requirement_ids",
            "criticality",
            "test_owner",
            "test_family_alias",
        ],
    )

    write_csv(
        root / "traceability_matrix.csv",
        traceability_rows,
        [
            "scenario_id",
            "release_id",
            "requirement_id",
            "test_case_id",
            "mapping_source",
            "mapping_confidence",
        ],
    )

    write_csv(
        root / "test_execution_results.csv",
        execution_rows,
        [
            "scenario_id",
            "release_id",
            "test_case_id",
            "status",
            "executed",
            "retest_required",
            "retest_completed",
            "executor",
            "execution_ts",
            "report_version",
            "narrative_note",
        ],
    )

    write_csv(
        root / "defect_register.csv",
        defect_rows,
        [
            "scenario_id",
            "release_id",
            "defect_id",
            "title",
            "severity",
            "status",
            "owner",
            "source_system",
            "closure_note",
        ],
    )

    write_csv(
        root / "phase5_decision_labels.csv",
        labels_rows,
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
    )

    write_csv(
        root / "phase5_release_calendar.csv",
        calendar_rows,
        [
            "release_id",
            "scenario_id",
            "environment",
            "phase5_window_start",
            "phase5_window_end",
            "target_phase5_gate",
        ],
    )

    write_csv(
        root / "scenario_taxonomy.csv",
        taxonomy_rows,
        [
            "scenario_id",
            "release_id",
            "primary_class",
            "secondary_modifiers",
            "ambiguity_level",
            "expected_decision",
        ],
    )

    # ------------------------------------------------------------------
    # Acceptance snapshot
    # ------------------------------------------------------------------
    all_gates_present = all(gate_coverage.get(k, 0) > 0 for k in HARD_GATE_CODES)
    label_policy_consistency = True
    for row in labels_rows:
        triggered = split_multi(row.get("triggered_conditions", "").replace("|", ","))
        expected = row.get("expected_decision", "")
        if triggered and expected != "HOLD":
            label_policy_consistency = False
            break
        if not triggered and expected != "GO":
            label_policy_consistency = False
            break

    manifest = {
        "dataset_name": "phase5_v2",
        "generated_at_utc": utc_now_iso(),
        "generator": "scripts/generate_phase5_dataset_v2.py",
        "seed": seed,
        "scenario_count": scenario_count,
        "parameters": {
            "ambiguity_rate": ambiguity_rate,
            "high_ambiguity_rate": high_ambiguity_rate,
            "missing_field_rate": missing_field_rate,
            "conflict_rate": conflict_rate,
            "continuity_cases_rate": continuity_rate,
            "alias_intensity": alias_intensity,
            "go_hold_ratio": go_hold_ratio,
        },
        "summary": {
            "go_count": go_count,
            "hold_count": hold_count,
            "continuity_cases": continuity_case_count,
            "class_coverage": class_coverage,
        },
        "coverage": {
            "hard_gate_trigger_counts": gate_coverage,
            "all_hard_gates_present": all_gates_present,
        },
        "acceptance_checks": {
            "label_policy_consistency": label_policy_consistency,
            "go_hold_present": go_count > 0 and hold_count > 0,
            "required_files_written": True,
        },
        "files": [
            "requirements_master.csv",
            "test_cases_master.csv",
            "traceability_matrix.csv",
            "test_execution_results.csv",
            "defect_register.csv",
            "phase5_decision_labels.csv",
            "phase5_release_calendar.csv",
            "scenario_taxonomy.csv",
            "phase5_manifest.json",
            "test_analysis_emails/*.txt",
            "agent4_context/*.json",
        ],
    }

    (root / "phase5_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(root),
                "scenario_count": scenario_count,
                "go_count": go_count,
                "hold_count": hold_count,
                "all_hard_gates_present": all_gates_present,
                "label_policy_consistency": label_policy_consistency,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
