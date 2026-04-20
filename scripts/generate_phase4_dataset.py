#!/usr/bin/env python3
"""
Phase 4 synthetic dataset generator (v1).

Generates a coherent benchmark dataset for Agent 4 (DEV -> TEST readiness).
The dataset includes:
- requirements_master.csv
- modules_versions.csv
- release_calendar.csv
- phase4_modules_versions.csv
- phase4_decision_labels.csv
- dev_deploy_logs/*.log
- service_health_reports/*.json
- dev_blockers_emails/*.txt
- scenario_manifest.json

Usage:
    python scripts/generate_phase4_dataset.py
    python scripts/generate_phase4_dataset.py --output-dir synthetic_data/v1 --force
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

# ---------------------------
# Domain definitions
# ---------------------------

MODULES = [
    "ingestion-gateway",
    "event-router",
    "monitoring-core",
    "analytics-api",
    "alarm-engine",
    "ui-backend",
]

CRITICAL_SERVICES = {"monitoring-core", "alarm-engine"}

REQUIREMENTS = [
    {
        "requirement_id": "REQ-401",
        "description": "Collect telemetry packets from edge nodes every 30s",
        "priority": "HIGH",
        "module": "ingestion-gateway",
        "mandatory_for_phase4": "true",
    },
    {
        "requirement_id": "REQ-402",
        "description": "Route normalized telemetry to monitoring pipeline",
        "priority": "HIGH",
        "module": "event-router",
        "mandatory_for_phase4": "true",
    },
    {
        "requirement_id": "REQ-403",
        "description": "Compute health KPIs and publish alarms",
        "priority": "HIGH",
        "module": "monitoring-core",
        "mandatory_for_phase4": "true",
    },
    {
        "requirement_id": "REQ-404",
        "description": "Expose analytics summary endpoint for test dashboard",
        "priority": "MEDIUM",
        "module": "analytics-api",
        "mandatory_for_phase4": "true",
    },
    {
        "requirement_id": "REQ-405",
        "description": "Trigger warning and critical alarms under threshold breaches",
        "priority": "HIGH",
        "module": "alarm-engine",
        "mandatory_for_phase4": "true",
    },
    {
        "requirement_id": "REQ-406",
        "description": "Provide release metadata and build provenance endpoint",
        "priority": "MEDIUM",
        "module": "ui-backend",
        "mandatory_for_phase4": "false",
    },
]

BASE_PLANNED_VERSIONS = {
    "ingestion-gateway": "1.4.0",
    "event-router": "2.3.1",
    "monitoring-core": "3.1.0",
    "analytics-api": "1.9.2",
    "alarm-engine": "2.7.0",
    "ui-backend": "1.2.4",
}


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    release_id: str
    scenario_type: str  # CLEAR_GO, CLEAR_HOLD, MIX
    expected_decision: str  # GO, HOLD
    rationale: str

    unhealthy_service: bool = False
    critical_log_error: bool = False
    open_blocker_email: bool = False
    mandatory_version_mismatch: bool = False
    unmet_conditional: bool = False
    non_blocking_warning: bool = False


SCENARIOS: List[Scenario] = [
    Scenario(
        scenario_id="S4-001",
        release_id="REL-2026.04.01",
        scenario_type="CLEAR_GO",
        expected_decision="GO",
        rationale="All hard gates passed, only informational logs present.",
    ),
    Scenario(
        scenario_id="S4-002",
        release_id="REL-2026.04.02",
        scenario_type="CLEAR_HOLD",
        expected_decision="HOLD",
        rationale="Critical service unhealthy in DEV.",
        unhealthy_service=True,
    ),
    Scenario(
        scenario_id="S4-003",
        release_id="REL-2026.04.03",
        scenario_type="CLEAR_HOLD",
        expected_decision="HOLD",
        rationale="Unresolved CRITICAL runtime issue in deploy logs.",
        critical_log_error=True,
    ),
    Scenario(
        scenario_id="S4-004",
        release_id="REL-2026.04.04",
        scenario_type="CLEAR_HOLD",
        expected_decision="HOLD",
        rationale="Open blocker remains unresolved in email thread.",
        open_blocker_email=True,
    ),
    Scenario(
        scenario_id="S4-005",
        release_id="REL-2026.04.05",
        scenario_type="CLEAR_HOLD",
        expected_decision="HOLD",
        rationale="Mandatory module version mismatch detected.",
        mandatory_version_mismatch=True,
    ),
    Scenario(
        scenario_id="S4-006",
        release_id="REL-2026.04.06",
        scenario_type="CLEAR_HOLD",
        expected_decision="HOLD",
        rationale="Conditional release requirement (retest) unmet.",
        unmet_conditional=True,
    ),
    Scenario(
        scenario_id="S4-007",
        release_id="REL-2026.04.07",
        scenario_type="MIX",
        expected_decision="GO",
        rationale="Non-blocking WARN logs and resolved thread, no hard blockers.",
        non_blocking_warning=True,
    ),
    Scenario(
        scenario_id="S4-008",
        release_id="REL-2026.04.08",
        scenario_type="MIX",
        expected_decision="HOLD",
        rationale="Both version mismatch and open blocker present.",
        mandatory_version_mismatch=True,
        open_blocker_email=True,
        non_blocking_warning=True,
    ),
    Scenario(
        scenario_id="S4-009",
        release_id="REL-2026.04.09",
        scenario_type="MIX",
        expected_decision="HOLD",
        rationale="Service unhealthy plus unresolved runtime CRITICAL error.",
        unhealthy_service=True,
        critical_log_error=True,
    ),
    Scenario(
        scenario_id="S4-010",
        release_id="REL-2026.04.10",
        scenario_type="MIX",
        expected_decision="HOLD",
        rationale="Conditional unmet despite otherwise healthy deployment.",
        unmet_conditional=True,
        non_blocking_warning=True,
    ),
]


# ---------------------------
# Utilities
# ---------------------------


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def iso_time(base: datetime, minutes_offset: int) -> str:
    return (base + timedelta(minutes=minutes_offset)).isoformat()


def bump_patch(version: str, delta: int = 1) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + delta}"


def lower_patch(version: str, delta: int = 1) -> str:
    major, minor, patch = version.split(".")
    patch_int = int(patch)

    # Primary path: lower patch while staying non-negative.
    if patch_int - delta >= 0:
        return f"{major}.{minor}.{patch_int - delta}"

    # Fallback path for patch==0 (or underflow): still force a mismatch.
    # Try lowering minor and set a high patch to keep semantic plausibility.
    minor_int = int(minor)
    if minor_int > 0:
        return f"{major}.{minor_int - 1}.99"

    # Last fallback when major/minor are both 0: bump patch to guarantee mismatch.
    return f"{major}.{minor}.{patch_int + max(delta, 1)}"


def scenario_conditions(s: Scenario) -> List[str]:
    flags = []
    if s.unhealthy_service:
        flags.append("critical_service_unhealthy")
    if s.critical_log_error:
        flags.append("unresolved_error_or_critical_log")
    if s.open_blocker_email:
        flags.append("open_blocker_email")
    if s.mandatory_version_mismatch:
        flags.append("mandatory_version_mismatch")
    if s.unmet_conditional:
        flags.append("unmet_conditional_requirement")
    if s.non_blocking_warning:
        flags.append("non_blocking_warning")
    return flags


# ---------------------------
# Content builders
# ---------------------------


def build_release_calendar_rows(start_date: datetime) -> List[Dict[str, str]]:
    rows = []
    for i, s in enumerate(SCENARIOS):
        dev_window_start = (start_date + timedelta(days=i)).date().isoformat()
        dev_window_end = (start_date + timedelta(days=i + 1)).date().isoformat()
        target_test_promotion = (start_date + timedelta(days=i + 2)).date().isoformat()
        rows.append(
            {
                "release_id": s.release_id,
                "scenario_id": s.scenario_id,
                "environment": "DEV",
                "dev_window_start": dev_window_start,
                "dev_window_end": dev_window_end,
                "target_test_promotion": target_test_promotion,
            }
        )
    return rows


def build_module_version_rows_for_scenario(s: Scenario) -> List[Dict[str, str]]:
    rows = []
    mismatch_module = "monitoring-core"
    for module in MODULES:
        planned = BASE_PLANNED_VERSIONS[module]
        deployed = planned

        if s.mandatory_version_mismatch and module == mismatch_module:
            deployed = lower_patch(planned, delta=1)
        elif s.expected_decision == "GO" and module == "ui-backend":
            # harmless patch forward drift on non-mandatory module can still be GO
            deployed = bump_patch(planned, delta=1)

        rows.append(
            {
                "scenario_id": s.scenario_id,
                "release_id": s.release_id,
                "environment": "DEV",
                "module": module,
                "planned_version": planned,
                "deployed_version": deployed,
                "mandatory_for_phase4": str(
                    module in CRITICAL_SERVICES or module != "ui-backend"
                ).lower(),
                "version_match": str(planned == deployed).lower(),
            }
        )
    return rows


def build_deploy_log(s: Scenario, rng: random.Random, base_time: datetime) -> str:
    lines = []
    current = base_time
    lines.append(
        f"{iso_time(current, 0)} INFO  [orchestrator] Starting deployment for {s.release_id} ({s.scenario_id})"
    )
    lines.append(f"{iso_time(current, 1)} INFO  [orchestrator] Environment=DEV")
    lines.append(
        f"{iso_time(current, 2)} INFO  [registry] Pulling images for 6 modules"
    )

    offset = 3
    for m in MODULES:
        lines.append(f"{iso_time(current, offset)} INFO  [{m}] Container started")
        offset += 1

    if s.non_blocking_warning:
        lines.append(
            f"{iso_time(current, offset)} WARN  [analytics-api] Retry on transient dependency timeout"
        )
        offset += 1

    if s.critical_log_error:
        lines.append(
            f"{iso_time(current, offset)} ERROR [monitoring-core] Failed to load runtime rule-set checksum"
        )
        offset += 1
        lines.append(
            f"{iso_time(current, offset)} CRITICAL [monitoring-core] Rule engine failed health bootstrap"
        )
        offset += 1
        lines.append(
            f"{iso_time(current, offset)} INFO  [orchestrator] Auto-retry scheduled"
        )
        offset += 1
        lines.append(
            f"{iso_time(current, offset)} ERROR [orchestrator] Deployment marked unstable after retries"
        )
        offset += 1
    else:
        # add some normal noise
        if rng.random() < 0.5:
            lines.append(
                f"{iso_time(current, offset)} INFO  [event-router] Queue depth within expected range"
            )
            offset += 1
        lines.append(
            f"{iso_time(current, offset)} INFO  [orchestrator] Deployment completed successfully"
        )
        offset += 1

    return "\n".join(lines) + "\n"


def build_service_health_report(s: Scenario, base_time: datetime) -> Dict[str, object]:
    services = []
    unhealthy_target = "monitoring-core"

    for module in MODULES:
        status = "healthy"
        reason = "ok"

        if s.unhealthy_service and module == unhealthy_target:
            status = "unhealthy"
            reason = "readiness probe failed (connection timeout to rule cache)"

        services.append(
            {
                "service": module,
                "status": status,
                "critical": module in CRITICAL_SERVICES,
                "reason": reason,
            }
        )

    overall = "healthy"
    if any(item["critical"] and item["status"] != "healthy" for item in services):
        overall = "degraded"

    return {
        "scenario_id": s.scenario_id,
        "release_id": s.release_id,
        "environment": "DEV",
        "generated_at": iso_time(base_time, 20),
        "overall_status": overall,
        "services": services,
    }


def build_email_thread(s: Scenario, base_time: datetime) -> str:
    t0 = iso_time(base_time, 5)
    t1 = iso_time(base_time, 25)
    t2 = iso_time(base_time, 45)

    if s.open_blocker_email:
        return (
            f"Subject: [{s.release_id}] Blocker - DEV readiness unresolved\n"
            f"Time: {t0}\n"
            f"From: qa.lead@company.example\n"
            f"To: release.manager@company.example\n\n"
            "Issue remains OPEN.\n"
            "Blocking symptom: alarm notifications not propagated under failover.\n"
            "Action requested: hold DEV->TEST promotion until fix + retest evidence.\n\n"
            f"Time: {t1}\n"
            f"From: dev.lead@company.example\n"
            f"To: qa.lead@company.example\n\n"
            "Patch under development. No validated fix available yet.\n"
            "Status: OPEN BLOCKER\n"
        )

    if s.unmet_conditional:
        return (
            f"Subject: [{s.release_id}] Conditional readiness note\n"
            f"Time: {t0}\n"
            f"From: compliance@company.example\n"
            f"To: release.manager@company.example\n\n"
            "Conditional clearance only.\n"
            "Retest is REQUIRED before DEV->TEST promotion due to updated alarm threshold policy.\n"
            "Current state: evidence missing for required retest run.\n\n"
            f"Time: {t1}\n"
            f"From: qa.lead@company.example\n"
            f"To: release.manager@company.example\n\n"
            "Status: CONDITIONAL UNMET\n"
        )

    if s.non_blocking_warning:
        return (
            f"Subject: [{s.release_id}] DEV deployment notes\n"
            f"Time: {t0}\n"
            f"From: dev.lead@company.example\n"
            f"To: qa.lead@company.example\n\n"
            "Observed transient API timeout during first startup; issue self-recovered.\n"
            "No blocker opened.\n\n"
            f"Time: {t1}\n"
            f"From: qa.lead@company.example\n"
            f"To: release.manager@company.example\n\n"
            "Verification complete. Previous warning classified as non-blocking.\n"
            "Status: RESOLVED\n"
        )

    return (
        f"Subject: [{s.release_id}] DEV readiness confirmation\n"
        f"Time: {t0}\n"
        f"From: qa.lead@company.example\n"
        f"To: release.manager@company.example\n\n"
        "No open blockers found in DEV validation.\n"
        "Status: NONE\n\n"
        f"Time: {t2}\n"
        f"From: release.manager@company.example\n"
        f"To: qa.lead@company.example\n\n"
        "Acknowledged.\n"
    )


def build_decision_label_rows() -> List[Dict[str, str]]:
    rows = []
    for s in SCENARIOS:
        rows.append(
            {
                "scenario_id": s.scenario_id,
                "release_id": s.release_id,
                "environment": "DEV",
                "scenario_type": s.scenario_type,
                "expected_decision": s.expected_decision,
                "rationale": s.rationale,
                "triggered_conditions": "|".join(scenario_conditions(s)),
            }
        )
    return rows


# ---------------------------
# Main generation
# ---------------------------


def generate_dataset(output_dir: Path, seed: int, force: bool) -> None:
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise FileExistsError(
            f"Output directory '{output_dir}' is not empty. Use --force to overwrite files."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    deploy_dir = output_dir / "dev_deploy_logs"
    health_dir = output_dir / "service_health_reports"
    email_dir = output_dir / "dev_blockers_emails"
    for d in (deploy_dir, health_dir, email_dir):
        d.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    generation_time = datetime.now(timezone.utc).replace(microsecond=0)
    start_date = generation_time

    # requirements_master.csv
    write_csv(
        output_dir / "requirements_master.csv",
        fieldnames=[
            "requirement_id",
            "description",
            "priority",
            "module",
            "mandatory_for_phase4",
        ],
        rows=REQUIREMENTS,
    )

    # release_calendar.csv
    release_calendar_rows = build_release_calendar_rows(start_date)
    write_csv(
        output_dir / "release_calendar.csv",
        fieldnames=[
            "release_id",
            "scenario_id",
            "environment",
            "dev_window_start",
            "dev_window_end",
            "target_test_promotion",
        ],
        rows=release_calendar_rows,
    )

    # versions (global + phase4)
    all_version_rows: List[Dict[str, str]] = []
    for s in SCENARIOS:
        all_version_rows.extend(build_module_version_rows_for_scenario(s))

    write_csv(
        output_dir / "modules_versions.csv",
        fieldnames=[
            "scenario_id",
            "release_id",
            "environment",
            "module",
            "planned_version",
            "deployed_version",
            "mandatory_for_phase4",
            "version_match",
        ],
        rows=all_version_rows,
    )
    write_csv(
        output_dir / "phase4_modules_versions.csv",
        fieldnames=[
            "scenario_id",
            "release_id",
            "environment",
            "module",
            "planned_version",
            "deployed_version",
            "mandatory_for_phase4",
            "version_match",
        ],
        rows=all_version_rows,
    )

    # scenario artifacts
    for idx, s in enumerate(SCENARIOS):
        base_time = generation_time + timedelta(hours=idx * 3)

        log_content = build_deploy_log(s, rng, base_time)
        (deploy_dir / f"{s.scenario_id}.log").write_text(log_content, encoding="utf-8")

        health_content = build_service_health_report(s, base_time)
        (health_dir / f"{s.scenario_id}.json").write_text(
            json.dumps(health_content, indent=2), encoding="utf-8"
        )

        email_content = build_email_thread(s, base_time)
        (email_dir / f"{s.scenario_id}.txt").write_text(email_content, encoding="utf-8")

    # labels
    label_rows = build_decision_label_rows()
    write_csv(
        output_dir / "phase4_decision_labels.csv",
        fieldnames=[
            "scenario_id",
            "release_id",
            "environment",
            "scenario_type",
            "expected_decision",
            "rationale",
            "triggered_conditions",
        ],
        rows=label_rows,
    )

    # manifest
    manifest = {
        "dataset": "phase4_v1",
        "generated_at": generation_time.isoformat(),
        "seed": seed,
        "scenario_count": len(SCENARIOS),
        "decision_distribution": {
            "GO": sum(1 for s in SCENARIOS if s.expected_decision == "GO"),
            "HOLD": sum(1 for s in SCENARIOS if s.expected_decision == "HOLD"),
        },
        "policy_reference": {
            "hold_conditions": [
                "critical_service_unhealthy",
                "unresolved_error_or_critical_log",
                "open_blocker_email",
                "mandatory_version_mismatch",
                "unmet_conditional_requirement",
            ],
            "go_rule": "GO only when no hold_condition is present",
        },
        "files": {
            "requirements": "requirements_master.csv",
            "release_calendar": "release_calendar.csv",
            "versions": "modules_versions.csv",
            "phase4_versions": "phase4_modules_versions.csv",
            "labels": "phase4_decision_labels.csv",
            "deploy_logs": "dev_deploy_logs/",
            "health_reports": "service_health_reports/",
            "emails": "dev_blockers_emails/",
        },
    }
    (output_dir / "scenario_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Phase 4 dataset (v1)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("synthetic_data/v1"),
        help="Output directory for generated dataset (default: synthetic_data/v1)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic seed for synthetic variations (default: 42)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into a non-empty output directory",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_dataset(output_dir=args.output_dir, seed=args.seed, force=args.force)
    print(f"Phase 4 v1 dataset generated at: {args.output_dir}")


if __name__ == "__main__":
    main()
