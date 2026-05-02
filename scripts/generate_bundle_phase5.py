"""
Generate Phase 5 CSV datasets inside each APCS bundle folder.

Creates a phase5/ subfolder in every APCS bundle with:
  - phase5_release_calendar.csv
  - requirements_master.csv
  - test_cases_master.csv
  - traceability_matrix.csv
  - test_execution_results.csv
  - defect_register.csv
  - phase5_manifest.json
  - agent4_context/<scenario_id>.json  (only for A4-continuity bundles)

Usage:
    python scripts/generate_bundle_phase5.py
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLES_ROOT = REPO_ROOT / "datasets" / "apcs_bundles"

WINDOW_START = "2026-06-01T09:00:00+00:00"
WINDOW_END = "2026-06-02T18:00:00+00:00"
EXEC_TS = "2026-06-01T10:00:00+00:00"


class HoldReason(str, Enum):
    NONE = "none"
    CRITICAL_DEFECT_OPEN = "critical_defect_open"
    MANDATORY_REQ_FAILED = "mandatory_requirement_failed_or_blocked"
    TEST_EVIDENCE_INCOMPLETE = "test_evidence_incomplete"
    AGENT4_CONTINUITY = "agent4_unresolved_hard_blocker_unclosed"
    COMPOUND = "compound"  # critical_defect + mandatory_req_failed


@dataclass
class BundleSpec:
    category: str
    folder: str
    scenario_id: str
    release_id: str
    hold_reason: HoldReason
    agent4_decision: str = "HOLD"


BUNDLES: List[BundleSpec] = [
    # --- baseline ---
    BundleSpec(
        category="baseline",
        folder="SET_GO_STABLE_v1.1.2",
        scenario_id="P5-BASE-GO-001",
        release_id="BASE-REL-1.1.2",
        hold_reason=HoldReason.NONE,
    ),
    BundleSpec(
        category="baseline",
        folder="SET_HOLD_A4_CONTINUITY_v1.1.2",
        scenario_id="P5-BASE-HOLD-A4-001",
        release_id="BASE-REL-1.1.2-A4",
        hold_reason=HoldReason.AGENT4_CONTINUITY,
        agent4_decision="HOLD",
    ),
    BundleSpec(
        category="baseline",
        folder="SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2",
        scenario_id="P5-BASE-HOLD-RT-001",
        release_id="BASE-REL-1.1.2-RT",
        hold_reason=HoldReason.CRITICAL_DEFECT_OPEN,
    ),
    BundleSpec(
        category="baseline",
        folder="SET_RANDOM_APCS_v1.0",
        scenario_id="P5-BASE-RAND-001",
        release_id="BASE-REL-1.0.0",
        hold_reason=HoldReason.NONE,
    ),
    # --- adversarial ---
    BundleSpec(
        category="adversarial",
        folder="SET_ADV_GO_FALSE_ALARM_v1.3.0",
        scenario_id="P5-ADV-GO-FA-001",
        release_id="ADV-REL-1.3.0-FA",
        hold_reason=HoldReason.NONE,
    ),
    BundleSpec(
        category="adversarial",
        folder="SET_ADV_HOLD_FAKE_CLOSURE_v1.3.0",
        scenario_id="P5-ADV-HOLD-FC-001",
        release_id="ADV-REL-1.3.0-FC",
        hold_reason=HoldReason.MANDATORY_REQ_FAILED,
    ),
    BundleSpec(
        category="adversarial",
        folder="SET_ADV_HOLD_SILENT_DRIFT_v1.3.0",
        scenario_id="P5-ADV-HOLD-SD-001",
        release_id="ADV-REL-1.3.0-SD",
        hold_reason=HoldReason.TEST_EVIDENCE_INCOMPLETE,
    ),
    BundleSpec(
        category="adversarial",
        folder="SET_ADV_HOLD_UNRESOLVED_CONFLICT_v1.3.0",
        scenario_id="P5-ADV-HOLD-UC-001",
        release_id="ADV-REL-1.3.0-UC",
        hold_reason=HoldReason.CRITICAL_DEFECT_OPEN,
    ),
    # --- premium ---
    BundleSpec(
        category="premium",
        folder="SET_GO_PREMIUM_v1.2.0",
        scenario_id="P5-PREM-GO-001",
        release_id="PREM-REL-1.2.0",
        hold_reason=HoldReason.NONE,
    ),
    BundleSpec(
        category="premium",
        folder="SET_HOLD_COMPOUND_BLOCKERS_v1.2.0",
        scenario_id="P5-PREM-HOLD-CB-001",
        release_id="PREM-REL-1.2.0-CB",
        hold_reason=HoldReason.COMPOUND,
    ),
    BundleSpec(
        category="premium",
        folder="SET_HOLD_VERSION_DRIFT_v1.2.0",
        scenario_id="P5-PREM-HOLD-VD-001",
        release_id="PREM-REL-1.2.0-VD",
        hold_reason=HoldReason.TEST_EVIDENCE_INCOMPLETE,
    ),
]


def write_csv(path: Path, headers: List[str], rows: List[List[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def generate_phase5(spec: BundleSpec) -> None:
    bundle_root = BUNDLES_ROOT / spec.category / spec.folder
    if not bundle_root.exists():
        print(f"  SKIP (folder not found): {bundle_root}")
        return

    out = bundle_root / "phase5"
    out.mkdir(exist_ok=True)

    sid = spec.scenario_id
    rid = spec.release_id
    hr = spec.hold_reason

    # ------------------------------------------------------------------ #
    # phase5_release_calendar.csv
    # ------------------------------------------------------------------ #
    write_csv(
        out / "phase5_release_calendar.csv",
        ["release_id", "scenario_id", "environment", "phase5_window_start", "phase5_window_end", "target_phase5_gate"],
        [[rid, sid, "TEST", WINDOW_START, WINDOW_END, "phase5_test_analysis"]],
    )

    # ------------------------------------------------------------------ #
    # requirements_master.csv
    # ------------------------------------------------------------------ #
    write_csv(
        out / "requirements_master.csv",
        ["scenario_id", "release_id", "requirement_id", "description", "priority", "module", "mandatory_for_phase5", "domain", "traceability_tag", "module_alias_raw"],
        [
            [sid, rid, "REQ-001", "Mandatory authentication regression check.", "HIGH", "auth-service", "true", "security", "MUST", "Authentication Core"],
            [sid, rid, "REQ-002", "Mandatory transaction idempotency validation.", "HIGH", "payment-core", "true", "transaction", "MUST", "Txn Engine"],
            [sid, rid, "REQ-003", "Mandatory audit-log persistence verification.", "MEDIUM", "audit-store", "true", "compliance", "MUST", "Audit Ledger"],
        ],
    )

    # ------------------------------------------------------------------ #
    # test_cases_master.csv
    # ------------------------------------------------------------------ #
    write_csv(
        out / "test_cases_master.csv",
        ["scenario_id", "release_id", "test_case_id", "title", "mapped_requirement_ids", "criticality", "test_owner", "test_family_alias"],
        [
            [sid, rid, "TC-001", "Auth flow regression", "REQ-001", "HIGH", "qa.auth", "Identity Regression Pack"],
            [sid, rid, "TC-002", "Transaction idempotency checks", "REQ-002", "HIGH", "qa.payment", "Txn Resilience Pack"],
            [sid, rid, "TC-003", "Audit log persistence", "REQ-003", "MEDIUM", "qa.compliance", "Compliance Persistence Pack"],
        ],
    )

    # ------------------------------------------------------------------ #
    # traceability_matrix.csv
    # ------------------------------------------------------------------ #
    write_csv(
        out / "traceability_matrix.csv",
        ["scenario_id", "release_id", "requirement_id", "test_case_id", "mapping_source", "mapping_confidence"],
        [
            [sid, rid, "REQ-001", "TC-001", "traceability_workbook", "high"],
            [sid, rid, "REQ-002", "TC-002", "traceability_workbook", "high"],
            [sid, rid, "REQ-003", "TC-003", "traceability_workbook", "high"],
        ],
    )

    # ------------------------------------------------------------------ #
    # test_execution_results.csv
    # ------------------------------------------------------------------ #
    exec_headers = [
        "scenario_id", "release_id", "test_case_id", "status",
        "executed", "retest_required", "retest_completed",
        "executor", "execution_ts", "report_version", "narrative_note",
    ]

    if hr == HoldReason.MANDATORY_REQ_FAILED or hr == HoldReason.COMPOUND:
        exec_rows = [
            [sid, rid, "TC-001", "FAIL", "true", "false", "false", "qa.auth", EXEC_TS, "v1.0", "auth regression still failing after patch"],
            [sid, rid, "TC-002", "PASS", "true", "false", "false", "qa.payment", EXEC_TS, "v1.0", ""],
            [sid, rid, "TC-003", "PASS", "true", "false", "false", "qa.compliance", EXEC_TS, "v1.0", ""],
        ]
    elif hr == HoldReason.TEST_EVIDENCE_INCOMPLETE:
        exec_rows = [
            [sid, rid, "TC-001", "BLOCKED", "false", "false", "false", "", "", "", "test not executed - environment instability prevented run"],
            [sid, rid, "TC-002", "PASS", "true", "false", "false", "qa.payment", EXEC_TS, "v1.0", ""],
            [sid, rid, "TC-003", "PASS", "true", "false", "false", "qa.compliance", EXEC_TS, "v1.0", ""],
        ]
    else:
        # GO, CRITICAL_DEFECT_OPEN, AGENT4_CONTINUITY — tests all pass
        exec_rows = [
            [sid, rid, "TC-001", "PASS", "true", "false", "false", "qa.auth", EXEC_TS, "v1.0", ""],
            [sid, rid, "TC-002", "PASS", "true", "false", "false", "qa.payment", EXEC_TS, "v1.0", ""],
            [sid, rid, "TC-003", "PASS", "true", "false", "false", "qa.compliance", EXEC_TS, "v1.0", ""],
        ]

    write_csv(out / "test_execution_results.csv", exec_headers, exec_rows)

    # ------------------------------------------------------------------ #
    # defect_register.csv
    # ------------------------------------------------------------------ #
    defect_headers = [
        "scenario_id", "release_id", "defect_id", "title", "severity",
        "status", "owner", "source_system", "closure_note",
    ]

    if hr in (HoldReason.CRITICAL_DEFECT_OPEN, HoldReason.COMPOUND):
        defect_rows = [
            [sid, rid, "DF-001", "Minor UI formatting issue", "LOW", "CLOSED", "dev.ui", "jira", "fixed in UI patch"],
            [sid, rid, "DF-CRIT-001", "Critical data integrity issue in payment commit path", "CRITICAL", "OPEN", "dev.payment", "jira", ""],
        ]
    else:
        defect_rows = [
            [sid, rid, "DF-001", "Minor UI formatting issue", "LOW", "CLOSED", "dev.ui", "jira", "fixed in UI patch"],
        ]

    write_csv(out / "defect_register.csv", defect_headers, defect_rows)

    # ------------------------------------------------------------------ #
    # agent4_context/<scenario_id>.json  (only for A4-continuity bundles)
    # ------------------------------------------------------------------ #
    if hr == HoldReason.AGENT4_CONTINUITY:
        ctx_dir = out / "agent4_context"
        ctx_dir.mkdir(exist_ok=True)
        ctx = {
            "agent4_decision": spec.agent4_decision,
            "agent4_triggered_rules": ["critical_service_unhealthy"],
            "unresolved_conditions": ["service_health_not_confirmed_in_phase5"],
            "closure_confirmed": False,
            "confidence": "high",
            "summary": (
                "Agent 4 detected a critical service health issue that remains unresolved. "
                "Phase 5 evidence does not contain an explicit closure note for this blocker."
            ),
        }
        ctx_file = ctx_dir / f"{sid}.json"
        ctx_file.write_text(json.dumps(ctx, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"    + agent4_context/{sid}.json")

    # ------------------------------------------------------------------ #
    # phase5_manifest.json
    # ------------------------------------------------------------------ #
    is_go = hr == HoldReason.NONE
    manifest = {
        "dataset_name": f"phase5_{spec.folder}",
        "generated_at_utc": "2026-05-01T10:00:00+00:00",
        "generator": "scripts/generate_bundle_phase5.py",
        "scenario_count": 1,
        "bundle_source": spec.folder,
        "summary": {
            "go_count": 1 if is_go else 0,
            "hold_count": 0 if is_go else 1,
            "hold_reason": hr.value if not is_go else None,
        },
        "files": [
            "phase5_release_calendar.csv",
            "requirements_master.csv",
            "test_cases_master.csv",
            "traceability_matrix.csv",
            "test_execution_results.csv",
            "defect_register.csv",
        ],
    }
    (out / "phase5_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    decision = "GO" if is_go else f"HOLD ({hr.value})"
    print(f"  OK  {spec.folder}/phase5/  [{decision}]")


def main() -> None:
    print(f"Generating Phase 5 datasets in {BUNDLES_ROOT}\n")
    for spec in BUNDLES:
        generate_phase5(spec)
    print("\nDone.")


if __name__ == "__main__":
    main()
