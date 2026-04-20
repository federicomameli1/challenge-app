#!/usr/bin/env python3
"""
Phase 5 v1 synthetic dataset generator.

Generates a deterministic, policy-aligned dataset for Agent 5 development and
evaluation under `synthetic_data/phase5/v1` by default.

Output files:
- requirements_master.csv
- test_cases_master.csv
- traceability_matrix.csv
- test_execution_results.csv
- defect_register.csv
- phase5_decision_labels.csv
- phase5_release_calendar.csv
- phase5_manifest.json
- test_analysis_emails/<scenario_id>.txt
- agent4_context/<scenario_id>.json
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
    expected_bias: str  # "GO" or "HOLD"
    default_ambiguity: str  # low|medium|high


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Phase 5 v1 dataset."
    )
    parser.add_argument(
        "--output-dir",
        default="synthetic_data/phase5/v1",
        help="Output dataset directory (default: synthetic_data/phase5/v1)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=48,
        help="Total number of scenarios to generate (default: 48)",
    )
    parser.add_argument(
        "--ambiguity-rate",
        type=float,
        default=0.20,
        help="Rate for medium/high narrative ambiguity injection [0..1] (default: 0.20)",
    )
    parser.add_argument(
        "--missing-field-rate",
        type=float,
        default=0.05,
        help="Rate for optional-field omissions [0..1] (default: 0.05)",
    )
    parser.add_argument(
        "--conflict-rate",
        type=float,
        default=0.05,
        help="Rate for narrative/documentary conflict injection [0..1] (default: 0.05)",
    )
    parser.add_argument(
        "--continuity-cases-rate",
        type=float,
        default=0.12,
        help="Approximate share of scenarios with Agent4 continuity context [0..1] (default: 0.12)",
    )
    parser.add_argument(
        "--go-hold-ratio",
        type=float,
        default=0.40,
        help="Target GO ratio in random fill scenarios [0..1] (default: 0.40)",
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


def choose_ambiguity(rng: random.Random, base: str, ambiguity_rate: float) -> str:
    if rng.random() > ambiguity_rate:
        return base
    roll = rng.random()
    if roll < 0.55:
        return "medium"
    return "high"


def scenario_id_from_index(idx: int) -> str:
    return "P5-{0:03d}".format(idx)


def release_id_from_index(idx: int) -> str:
    # Group by batches for realism.
    batch = 1 + ((idx - 1) // 12)
    patch = 0 + ((idx - 1) % 4)
    return "P5-REL-{0}.{1}.{2}".format(1, batch, patch)


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
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-004",
            "description": "Optional reporting UI smoke check.",
            "priority": "LOW",
            "module": "reporting-ui",
            "mandatory_for_phase5": "false",
            "domain": "ui",
            "traceability_tag": "OPTIONAL",
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
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-002",
            "title": "Payment idempotency checks",
            "mapped_requirement_ids": "REQ-P5-002",
            "criticality": "HIGH",
            "test_owner": "qa.payment",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-003",
            "title": "Order reconciliation consistency",
            "mapped_requirement_ids": "REQ-P5-003",
            "criticality": "MEDIUM",
            "test_owner": "qa.order",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-004",
            "title": "Reporting UI smoke",
            "mapped_requirement_ids": "REQ-P5-004",
            "criticality": "LOW",
            "test_owner": "qa.ui",
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
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-002",
            "test_case_id": "TC-P5-002",
            "mapping_source": "traceability_workbook",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-003",
            "test_case_id": "TC-P5-003",
            "mapping_source": "traceability_workbook",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "requirement_id": "REQ-P5-004",
            "test_case_id": "TC-P5-004",
            "mapping_source": "traceability_workbook",
        },
    ]


def build_base_executions(sid: str, rid: str) -> List[Dict[str, str]]:
    return [
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-001",
            "status": "PASS",
            "executed": "true",
            "retest_required": "false",
            "retest_completed": "false",
            "executor": "qa.auth",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-002",
            "status": "PASS",
            "executed": "true",
            "retest_required": "false",
            "retest_completed": "false",
            "executor": "qa.payment",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-003",
            "status": "PASS",
            "executed": "true",
            "retest_required": "false",
            "retest_completed": "false",
            "executor": "qa.order",
        },
        {
            "scenario_id": sid,
            "release_id": rid,
            "test_case_id": "TC-P5-004",
            "status": "PASS",
            "executed": "true",
            "retest_required": "false",
            "retest_completed": "false",
            "executor": "qa.ui",
        },
    ]


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
        }
    ]


def build_default_agent4_context() -> Optional[Dict[str, object]]:
    return None


def set_execution_status(
    executions: List[Dict[str, str]], tc_id: str, status: str
) -> None:
    for row in executions:
        if row.get("test_case_id") == tc_id:
            row["status"] = status
            row["executed"] = "true" if status.upper() != "NOT_RUN" else "false"
            return


def remove_trace_for_requirement(
    traceability: List[Dict[str, str]], requirement_id: str
) -> None:
    traceability[:] = [
        r for r in traceability if r.get("requirement_id") != requirement_id
    ]


def remove_execution_for_testcase(
    executions: List[Dict[str, str]], test_case_id: str
) -> None:
    executions[:] = [r for r in executions if r.get("test_case_id") != test_case_id]


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
        mapped = str(tc.get("mapped_requirement_ids", "")).strip()
        if not tc_id or not mapped:
            continue
        for req in [
            p.strip()
            for p in mapped.replace("|", ",").replace(";", ",").split(",")
            if p.strip()
        ]:
            req_to_tc.setdefault(req, set()).add(tc_id)

    exec_by_tc: Dict[str, List[Dict[str, str]]] = {}
    for ex in executions:
        tc_id = str(ex.get("test_case_id", "")).strip()
        if not tc_id:
            continue
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
            status = str(ex.get("status", "")).strip().upper()
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
        status = str(ex.get("status", "")).strip().upper()
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

        unresolved_list = []
        if isinstance(unresolved, list):
            unresolved_list = [str(x).strip() for x in unresolved if str(x).strip()]
        elif isinstance(unresolved, str):
            unresolved_list = [
                p.strip() for p in unresolved.replace("|", ",").split(",") if p.strip()
            ]

        triggered_list = []
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

    incompleteness = False
    if (
        not requirements
        or not test_cases
        or not traceability
        or not executions
        or not defects
    ):
        incompleteness = True
    if mandatory_uncovered:
        incompleteness = True

    return {
        "mandatory_requirement_uncovered": mandatory_uncovered,
        "mandatory_requirement_failed_or_blocked": mandatory_failed_or_blocked,
        "critical_defect_open": critical_defect_open,
        "test_evidence_incomplete": incompleteness,
        "conditional_retest_unmet": conditional_retest_unmet,
        "agent4_unresolved_hard_blocker_unclosed": agent4_unresolved_hard_blocker_unclosed,
    }


def build_rationale(triggered: Sequence[str], scenario_type: str) -> str:
    if not triggered:
        return "No hard Phase 5 gate triggered; mandatory scope is covered and clear for progression."
    return "HOLD due to triggered hard gates ({0}) in scenario class {1}.".format(
        ", ".join(triggered), scenario_type
    )


def apply_scenario_type_mutations(
    scenario_type: str,
    requirements: List[Dict[str, str]],
    test_cases: List[Dict[str, str]],
    traceability: List[Dict[str, str]],
    executions: List[Dict[str, str]],
    defects: List[Dict[str, str]],
    rng: random.Random,
    continuity_case: bool,
) -> Optional[Dict[str, object]]:
    agent4_context = build_default_agent4_context()

    if scenario_type == "CLEAR_GO":
        pass

    elif scenario_type == "MIXED_SIGNAL_GO":
        # Non-mandatory noise only.
        set_execution_status(executions, "TC-P5-004", "BLOCKED")
        for ex in executions:
            if ex.get("test_case_id") == "TC-P5-004":
                ex["retest_required"] = "false"
                ex["retest_completed"] = "false"
                break
        defects.append(
            {
                "scenario_id": defects[0]["scenario_id"],
                "release_id": defects[0]["release_id"],
                "defect_id": "DF-P5-NONBLOCK-{0}".format(
                    defects[0]["scenario_id"].split("-")[-1]
                ),
                "title": "Known UI spacing issue",
                "severity": "LOW",
                "status": "OPEN",
                "owner": "dev.ui",
            }
        )

    elif scenario_type == "HOLD_UNCOVERED_MANDATORY":
        remove_trace_for_requirement(traceability, "REQ-P5-002")
        remove_execution_for_testcase(executions, "TC-P5-002")

    elif scenario_type == "HOLD_FAILED_MANDATORY":
        set_execution_status(executions, "TC-P5-001", "FAIL")

    elif scenario_type == "HOLD_BLOCKED_MANDATORY":
        set_execution_status(executions, "TC-P5-002", "BLOCKED")

    elif scenario_type == "HOLD_OPEN_CRITICAL_DEFECT":
        defects.append(
            {
                "scenario_id": defects[0]["scenario_id"],
                "release_id": defects[0]["release_id"],
                "defect_id": "DF-P5-CRIT-{0}".format(
                    defects[0]["scenario_id"].split("-")[-1]
                ),
                "title": "Critical deadlock in payment commit path",
                "severity": "CRITICAL",
                "status": "OPEN",
                "owner": "dev.payment",
            }
        )

    elif scenario_type == "HOLD_UNMET_RETEST":
        set_execution_status(executions, "TC-P5-003", "CONDITIONAL_UNMET")
        for ex in executions:
            if ex.get("test_case_id") == "TC-P5-003":
                ex["retest_required"] = "true"
                ex["retest_completed"] = "false"
                break

    elif scenario_type == "HOLD_AGENT4_CONTINUITY":
        agent4_context = {
            "agent4_decision": "HOLD",
            "agent4_triggered_rules": ["mandatory_version_mismatch"],
            "unresolved_conditions": ["backend_version_alignment_unclosed"],
            "closure_confirmed": False,
            "confidence": "medium",
            "summary": "Agent4 unresolved hard blocker remained open at phase boundary.",
        }

    elif scenario_type == "MIXED_SIGNAL_HOLD_MULTI":
        set_execution_status(executions, "TC-P5-001", "FAIL")
        defects.append(
            {
                "scenario_id": defects[0]["scenario_id"],
                "release_id": defects[0]["release_id"],
                "defect_id": "DF-P5-HIGH-{0}".format(
                    defects[0]["scenario_id"].split("-")[-1]
                ),
                "title": "High severity timeout in auth-token propagation",
                "severity": "HIGH",
                "status": "OPEN",
                "owner": "dev.auth",
            }
        )

    elif scenario_type == "HOLD_EVIDENCE_INCOMPLETE":
        # Keep minimal structure but remove required mandatory scope traceability.
        traceability[:] = [
            row for row in traceability if row.get("requirement_id") == "REQ-P5-004"
        ]

    else:
        # Fallback to CLEAR_GO semantics.
        pass

    # Optional continuity overlays by global continuity rate.
    if continuity_case and scenario_type not in {"HOLD_AGENT4_CONTINUITY"}:
        if rng.random() < 0.5:
            agent4_context = {
                "agent4_decision": "HOLD",
                "agent4_triggered_rules": ["open_blocker_email"],
                "unresolved_conditions": ["pending_blocker_closure_note"],
                "closure_confirmed": True,
                "confidence": "medium",
                "summary": "Agent4 hold condition explicitly closed by Phase5 evidence.",
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


def maybe_drop_optional_fields(
    rng: random.Random,
    missing_field_rate: float,
    requirements: List[Dict[str, str]],
    test_cases: List[Dict[str, str]],
    executions: List[Dict[str, str]],
) -> None:
    # Drop optional fields only; do not remove required contract fields.
    for row in requirements:
        if rng.random() < missing_field_rate:
            row["domain"] = ""
        if rng.random() < missing_field_rate:
            row["traceability_tag"] = ""

    for row in test_cases:
        if rng.random() < missing_field_rate:
            row["test_owner"] = ""

    for row in executions:
        if rng.random() < missing_field_rate:
            row["executor"] = ""


def build_email_text(
    sid: str,
    rid: str,
    scenario_type: str,
    expected_decision: str,
    ambiguity_level: str,
    triggered_conditions: Sequence[str],
    conflict_injected: bool,
) -> str:
    lines: List[str] = []
    lines.append("Subject: [Phase5] Test analysis summary for {0}".format(rid))
    lines.append("Scenario: {0}".format(sid))
    lines.append("Date: {0}".format(utc_now_iso()))
    lines.append("")
    lines.append("Summary")
    lines.append("- Scenario class: {0}".format(scenario_type))
    lines.append("- Ambiguity level: {0}".format(ambiguity_level))
    lines.append("")

    if expected_decision == "GO":
        lines.append(
            "Current evidence indicates mandatory scope is covered and no hard blockers remain."
        )
    else:
        lines.append(
            "Current evidence indicates one or more hard gates remain unresolved."
        )
        lines.append(
            "- Triggered hard conditions: {0}".format(", ".join(triggered_conditions))
        )

    if ambiguity_level in {"medium", "high"}:
        lines.append("")
        lines.append("Narrative note:")
        lines.append(
            "Some teams report 'locally resolved' observations pending formal closure updates."
        )

    if conflict_injected:
        lines.append("")
        lines.append("Potential conflict:")
        lines.append(
            "An informal thread suggests progress, but official closure artifacts are not fully aligned."
        )

    lines.append("")
    lines.append("End of message.")
    return "\n".join(lines) + "\n"


def choose_blueprints(
    rng: random.Random,
    scenario_count: int,
    go_hold_ratio: float,
) -> List[ScenarioBlueprint]:
    must_have = [
        ScenarioBlueprint("CLEAR_GO", "GO", "low"),
        ScenarioBlueprint("HOLD_UNCOVERED_MANDATORY", "HOLD", "low"),
        ScenarioBlueprint("HOLD_FAILED_MANDATORY", "HOLD", "low"),
        ScenarioBlueprint("HOLD_BLOCKED_MANDATORY", "HOLD", "low"),
        ScenarioBlueprint("HOLD_OPEN_CRITICAL_DEFECT", "HOLD", "low"),
        ScenarioBlueprint("HOLD_UNMET_RETEST", "HOLD", "low"),
        ScenarioBlueprint("HOLD_AGENT4_CONTINUITY", "HOLD", "medium"),
        ScenarioBlueprint("MIXED_SIGNAL_GO", "GO", "medium"),
        ScenarioBlueprint("MIXED_SIGNAL_HOLD_MULTI", "HOLD", "medium"),
    ]

    if scenario_count <= len(must_have):
        return must_have[:scenario_count]

    out = list(must_have)

    go_types = [
        ScenarioBlueprint("CLEAR_GO", "GO", "low"),
        ScenarioBlueprint("MIXED_SIGNAL_GO", "GO", "medium"),
    ]
    hold_types = [
        ScenarioBlueprint("HOLD_UNCOVERED_MANDATORY", "HOLD", "low"),
        ScenarioBlueprint("HOLD_FAILED_MANDATORY", "HOLD", "low"),
        ScenarioBlueprint("HOLD_BLOCKED_MANDATORY", "HOLD", "low"),
        ScenarioBlueprint("HOLD_OPEN_CRITICAL_DEFECT", "HOLD", "low"),
        ScenarioBlueprint("HOLD_UNMET_RETEST", "HOLD", "low"),
        ScenarioBlueprint("HOLD_AGENT4_CONTINUITY", "HOLD", "medium"),
        ScenarioBlueprint("MIXED_SIGNAL_HOLD_MULTI", "HOLD", "medium"),
        ScenarioBlueprint("HOLD_EVIDENCE_INCOMPLETE", "HOLD", "medium"),
    ]

    while len(out) < scenario_count:
        if rng.random() < go_hold_ratio:
            out.append(rng.choice(go_types))
        else:
            out.append(rng.choice(hold_types))

    return out


def main() -> None:
    args = parse_args()

    seed = int(args.seed)
    scenario_count = max(1, int(args.scenario_count))
    ambiguity_rate = clamp01(float(args.ambiguity_rate))
    missing_field_rate = clamp01(float(args.missing_field_rate))
    conflict_rate = clamp01(float(args.conflict_rate))
    continuity_rate = clamp01(float(args.continuity_cases_rate))
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

    continuity_case_count = 0
    hold_count = 0
    go_count = 0
    gate_coverage: Dict[str, int] = {k: 0 for k in HARD_GATE_CODES}

    for idx, bp in enumerate(blueprints, start=1):
        sid = scenario_id_from_index(idx)
        rid = release_id_from_index(idx)
        env = "TEST"

        requirements = build_base_requirements(sid, rid)
        test_cases = build_base_test_cases(sid, rid)
        traceability = build_base_traceability(sid, rid)
        executions = build_base_executions(sid, rid)
        defects = build_base_defects(sid, rid)

        continuity_case = rng.random() < continuity_rate
        if continuity_case:
            continuity_case_count += 1

        agent4_context = apply_scenario_type_mutations(
            scenario_type=bp.scenario_type,
            requirements=requirements,
            test_cases=test_cases,
            traceability=traceability,
            executions=executions,
            defects=defects,
            rng=rng,
            continuity_case=continuity_case,
        )

        maybe_drop_optional_fields(
            rng=rng,
            missing_field_rate=missing_field_rate,
            requirements=requirements,
            test_cases=test_cases,
            executions=executions,
        )

        flags = compute_expected_flags(
            requirements=requirements,
            test_cases=test_cases,
            traceability=traceability,
            executions=executions,
            defects=defects,
            agent4_context=agent4_context,
        )

        triggered = [code for code, value in flags.items() if value]
        triggered.sort()

        expected_decision = "HOLD" if triggered else "GO"
        if expected_decision == "HOLD":
            hold_count += 1
        else:
            go_count += 1

        for code in triggered:
            gate_coverage[code] = gate_coverage.get(code, 0) + 1

        ambiguity_level = choose_ambiguity(rng, bp.default_ambiguity, ambiguity_rate)
        conflict_injected = rng.random() < conflict_rate
        rationale = build_rationale(triggered, bp.scenario_type)

        labels_rows.append(
            {
                "scenario_id": sid,
                "release_id": rid,
                "expected_decision": expected_decision,
                "scenario_type": bp.scenario_type,
                "rationale": rationale,
                "triggered_conditions": "|".join(triggered),
                "ambiguity_level": ambiguity_level,
                "requires_agent4_closure": "true"
                if "agent4_unresolved_hard_blocker_unclosed" in triggered
                else "false",
            }
        )

        calendar_rows.append(
            {
                "release_id": rid,
                "scenario_id": sid,
                "environment": env,
                "phase5_window_start": "2026-05-01T09:00:00+00:00",
                "phase5_window_end": "2026-05-02T18:00:00+00:00",
                "target_phase5_gate": "phase5_test_analysis",
            }
        )

        email_text = build_email_text(
            sid=sid,
            rid=rid,
            scenario_type=bp.scenario_type,
            expected_decision=expected_decision,
            ambiguity_level=ambiguity_level,
            triggered_conditions=triggered,
            conflict_injected=conflict_injected,
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

    # Write core files.
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

    manifest = {
        "dataset_name": "phase5_v1",
        "generated_at_utc": utc_now_iso(),
        "generator": "scripts/generate_phase5_dataset_v1.py",
        "seed": seed,
        "scenario_count": scenario_count,
        "parameters": {
            "ambiguity_rate": ambiguity_rate,
            "missing_field_rate": missing_field_rate,
            "conflict_rate": conflict_rate,
            "continuity_cases_rate": continuity_rate,
            "go_hold_ratio": go_hold_ratio,
        },
        "summary": {
            "go_count": go_count,
            "hold_count": hold_count,
            "continuity_cases": continuity_case_count,
        },
        "coverage": {
            "hard_gate_trigger_counts": gate_coverage,
            "all_hard_gates_present": all(v > 0 for v in gate_coverage.values()),
        },
        "files": [
            "requirements_master.csv",
            "test_cases_master.csv",
            "traceability_matrix.csv",
            "test_execution_results.csv",
            "defect_register.csv",
            "phase5_decision_labels.csv",
            "phase5_release_calendar.csv",
            "phase5_manifest.json",
            "test_analysis_emails/*.txt",
            "agent4_context/*.json",
        ],
    }

    (root / "phase5_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(root),
                "scenario_count": scenario_count,
                "go_count": go_count,
                "hold_count": hold_count,
                "all_hard_gates_present": manifest["coverage"][
                    "all_hard_gates_present"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
