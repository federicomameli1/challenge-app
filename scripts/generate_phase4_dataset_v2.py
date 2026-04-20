#!/usr/bin/env python3
"""
Phase 4 synthetic dataset generator (v2) with realism controls.

v2 goals:
- Preserve Agent 4 compatibility while increasing documentary realism.
- Introduce controlled ambiguity, terminology drift, and partial inconsistency.
- Keep deterministic benchmark labels for GO/HOLD evaluation.

Generated structure (default: synthetic_data/v2):
- requirements_master.csv
- modules_versions.csv
- phase4_modules_versions.csv
- release_calendar.csv
- phase4_decision_labels.csv
- phase4_v2_scenario_catalog.csv
- scenario_manifest.json
- dev_deploy_logs/*.log
- service_health_reports/*.json
- dev_blockers_emails/*.txt

Usage:
    python scripts/generate_phase4_dataset_v2.py
    python scripts/generate_phase4_dataset_v2.py --output-dir synthetic_data/v2 --force
    python scripts/generate_phase4_dataset_v2.py --alias-intensity 0.75 --contradiction-rate 0.35 --missing-field-rate 0.10
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

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

CANONICAL_MODULES = [
    "ingestion-gateway",
    "event-router",
    "monitoring-core",
    "analytics-api",
    "alarm-engine",
    "ui-backend",
]

CRITICAL_SERVICES = {"monitoring-core", "alarm-engine"}

BASE_REQUIREMENTS = [
    {
        "requirement_id": "REQ-4A01",
        "description": "Collect telemetry packets from edge nodes every 30 seconds",
        "priority": "HIGH",
        "module": "ingestion-gateway",
        "mandatory_for_phase4": "true",
        "domain_area": "ingestion",
        "verification_hint": "Check packet continuity in DEV runtime",
    },
    {
        "requirement_id": "REQ-4A02",
        "description": "Route normalized telemetry into monitoring pipeline",
        "priority": "HIGH",
        "module": "event-router",
        "mandatory_for_phase4": "true",
        "domain_area": "routing",
        "verification_hint": "Validate queue depth and pipeline handoff",
    },
    {
        "requirement_id": "REQ-4A03",
        "description": "Compute health KPIs and publish alert stream",
        "priority": "HIGH",
        "module": "monitoring-core",
        "mandatory_for_phase4": "true",
        "domain_area": "health-monitoring",
        "verification_hint": "Validate KPI freshness and event emission",
    },
    {
        "requirement_id": "REQ-4A04",
        "description": "Expose analytics summary endpoint for test dashboard",
        "priority": "MEDIUM",
        "module": "analytics-api",
        "mandatory_for_phase4": "true",
        "domain_area": "api",
        "verification_hint": "Probe /analytics/summary for expected schema",
    },
    {
        "requirement_id": "REQ-4A05",
        "description": "Trigger warning and critical alarms on threshold breaches",
        "priority": "HIGH",
        "module": "alarm-engine",
        "mandatory_for_phase4": "true",
        "domain_area": "alarms",
        "verification_hint": "Inject threshold breach and verify notifications",
    },
    {
        "requirement_id": "REQ-4A06",
        "description": "Provide build metadata endpoint with release provenance",
        "priority": "MEDIUM",
        "module": "ui-backend",
        "mandatory_for_phase4": "false",
        "domain_area": "metadata",
        "verification_hint": "Check build id and release tag traceability",
    },
]

BASE_PLANNED_VERSIONS = {
    "ingestion-gateway": "1.5.0",
    "event-router": "2.4.2",
    "monitoring-core": "3.2.0",
    "analytics-api": "2.0.1",
    "alarm-engine": "2.8.0",
    "ui-backend": "1.3.0",
}

MODULE_ALIASES: Dict[str, List[str]] = {
    "ingestion-gateway": [
        "ingestion-gateway",
        "Ingestion Gateway",
        "ingestion_gateway",
    ],
    "event-router": ["event-router", "event_router", "Event Router"],
    "monitoring-core": [
        "monitoring-core",
        "Monitoring Core",
        "monitoring_core",
        "module-b",
    ],
    "analytics-api": ["analytics-api", "analytics_api", "Analytics API"],
    "alarm-engine": ["alarm-engine", "alarm_engine", "Alarm Engine"],
    "ui-backend": ["ui-backend", "ui_backend", "UI Backend"],
}

# ---------------------------------------------------------------------------
# Scenario model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    release_id: str
    taxonomy: str
    expected_decision: str  # GO | HOLD
    primary_rules: Tuple[str, ...]
    ambiguity_level: str  # low | medium | high
    rationale: str

    # hard gate flags
    unhealthy_service: bool = False
    critical_log_error: bool = False
    open_blocker_email: bool = False
    mandatory_version_mismatch: bool = False
    unmet_conditional: bool = False

    # non-blocking and realism flags
    non_blocking_warning: bool = False
    recoverable_error: bool = False
    inconsistent_health_narrative: bool = False
    multi_message_email: bool = True


SCENARIOS: List[ScenarioSpec] = [
    ScenarioSpec(
        scenario_id="S4V2-001",
        release_id="REL-2026.05.01",
        taxonomy="baseline_clean_go",
        expected_decision="GO",
        primary_rules=(),
        ambiguity_level="low",
        rationale="All hard gates pass with clean evidence.",
    ),
    ScenarioSpec(
        scenario_id="S4V2-002",
        release_id="REL-2026.05.02",
        taxonomy="healthy_with_transient_warning_go",
        expected_decision="GO",
        primary_rules=(),
        ambiguity_level="medium",
        rationale="Transient warning present but recovered and non-blocking.",
        non_blocking_warning=True,
        recoverable_error=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-003",
        release_id="REL-2026.05.03",
        taxonomy="critical_service_unhealthy_hold",
        expected_decision="HOLD",
        primary_rules=("critical_service_unhealthy",),
        ambiguity_level="low",
        rationale="Critical service unhealthy in DEV.",
        unhealthy_service=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-004",
        release_id="REL-2026.05.04",
        taxonomy="unresolved_critical_log_hold",
        expected_decision="HOLD",
        primary_rules=("unresolved_error_or_critical_log",),
        ambiguity_level="low",
        rationale="Unresolved CRITICAL runtime issue in deploy logs.",
        critical_log_error=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-005",
        release_id="REL-2026.05.05",
        taxonomy="open_blocker_email_hold",
        expected_decision="HOLD",
        primary_rules=("open_blocker_email",),
        ambiguity_level="medium",
        rationale="Open blocker remains unresolved in email thread.",
        open_blocker_email=True,
        non_blocking_warning=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-006",
        release_id="REL-2026.05.06",
        taxonomy="mandatory_version_mismatch_hold",
        expected_decision="HOLD",
        primary_rules=("mandatory_version_mismatch",),
        ambiguity_level="low",
        rationale="Mandatory module version mismatch detected.",
        mandatory_version_mismatch=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-007",
        release_id="REL-2026.05.07",
        taxonomy="conditional_unmet_hold",
        expected_decision="HOLD",
        primary_rules=("unmet_conditional_requirement",),
        ambiguity_level="medium",
        rationale="Conditional retest requirement remains unmet.",
        unmet_conditional=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-008",
        release_id="REL-2026.05.08",
        taxonomy="dual_blocker_email_and_version_hold",
        expected_decision="HOLD",
        primary_rules=("open_blocker_email", "mandatory_version_mismatch"),
        ambiguity_level="medium",
        rationale="Open blocker and mandatory version mismatch both present.",
        open_blocker_email=True,
        mandatory_version_mismatch=True,
        non_blocking_warning=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-009",
        release_id="REL-2026.05.09",
        taxonomy="health_plus_log_hold",
        expected_decision="HOLD",
        primary_rules=(
            "critical_service_unhealthy",
            "unresolved_error_or_critical_log",
        ),
        ambiguity_level="high",
        rationale="Critical service unhealthy and unresolved log errors.",
        unhealthy_service=True,
        critical_log_error=True,
        inconsistent_health_narrative=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-010",
        release_id="REL-2026.05.10",
        taxonomy="conditional_plus_warning_hold",
        expected_decision="HOLD",
        primary_rules=("unmet_conditional_requirement",),
        ambiguity_level="high",
        rationale="Conditional unmet despite mostly healthy technical signals.",
        unmet_conditional=True,
        non_blocking_warning=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-011",
        release_id="REL-2026.05.11",
        taxonomy="recoverable_error_go",
        expected_decision="GO",
        primary_rules=(),
        ambiguity_level="medium",
        rationale="Error occurred but explicit recovery and successful completion observed.",
        recoverable_error=True,
        non_blocking_warning=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-012",
        release_id="REL-2026.05.12",
        taxonomy="email_noise_go",
        expected_decision="GO",
        primary_rules=(),
        ambiguity_level="high",
        rationale="No blocker status; email thread noisy but non-blocking.",
        non_blocking_warning=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-013",
        release_id="REL-2026.05.13",
        taxonomy="open_blocker_with_inconsistent_health_hold",
        expected_decision="HOLD",
        primary_rules=("open_blocker_email",),
        ambiguity_level="high",
        rationale="Open blocker is decisive even with partially inconsistent health narrative.",
        open_blocker_email=True,
        inconsistent_health_narrative=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-014",
        release_id="REL-2026.05.14",
        taxonomy="version_mismatch_with_recovery_logs_hold",
        expected_decision="HOLD",
        primary_rules=("mandatory_version_mismatch",),
        ambiguity_level="medium",
        rationale="Runtime appears healthy, but mandatory version mismatch blocks promotion.",
        mandatory_version_mismatch=True,
        recoverable_error=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-015",
        release_id="REL-2026.05.15",
        taxonomy="three_gate_hold",
        expected_decision="HOLD",
        primary_rules=(
            "unresolved_error_or_critical_log",
            "open_blocker_email",
            "mandatory_version_mismatch",
        ),
        ambiguity_level="high",
        rationale="Multiple independent hard blockers in the same candidate.",
        critical_log_error=True,
        open_blocker_email=True,
        mandatory_version_mismatch=True,
        non_blocking_warning=True,
    ),
    ScenarioSpec(
        scenario_id="S4V2-016",
        release_id="REL-2026.05.16",
        taxonomy="clean_go_alias_heavy",
        expected_decision="GO",
        primary_rules=(),
        ambiguity_level="medium",
        rationale="GO case with heavy module alias drift across artifacts.",
        non_blocking_warning=True,
    ),
]

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def clamp_01(value: float) -> float:
    return max(0.0, min(1.0, value))


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def choose_module_alias(module: str, alias_intensity: float, rng: random.Random) -> str:
    aliases = MODULE_ALIASES[module]
    if rng.random() < alias_intensity:
        return rng.choice(aliases)
    return module


def iso_time(base: datetime, minutes_offset: int) -> str:
    return (base + timedelta(minutes=minutes_offset)).replace(microsecond=0).isoformat()


def bump_patch(version: str, delta: int = 1) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + delta}"


def lower_patch(version: str, delta: int = 1) -> str:
    major, minor, patch = version.split(".")
    patch_i = int(patch)

    if patch_i - delta >= 0:
        return f"{major}.{minor}.{patch_i - delta}"

    minor_i = int(minor)
    if minor_i > 0:
        return f"{major}.{minor_i - 1}.99"

    return f"{major}.{minor}.{patch_i + max(1, delta)}"


def maybe_blank(value: str, missing_field_rate: float, rng: random.Random) -> str:
    # Used only for optional descriptive fields.
    if rng.random() < missing_field_rate:
        return ""
    return value


def scenario_rule_flags(spec: ScenarioSpec) -> List[str]:
    flags = []
    if spec.unhealthy_service:
        flags.append("critical_service_unhealthy")
    if spec.critical_log_error:
        flags.append("unresolved_error_or_critical_log")
    if spec.open_blocker_email:
        flags.append("open_blocker_email")
    if spec.mandatory_version_mismatch:
        flags.append("mandatory_version_mismatch")
    if spec.unmet_conditional:
        flags.append("unmet_conditional_requirement")
    return flags


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


def build_release_calendar_rows(
    scenarios: List[ScenarioSpec], start_date: datetime
) -> List[Dict[str, str]]:
    rows = []
    for i, s in enumerate(scenarios):
        dev_start = (start_date + timedelta(days=i)).date().isoformat()
        dev_end = (start_date + timedelta(days=i + 1)).date().isoformat()
        test_target = (start_date + timedelta(days=i + 2)).date().isoformat()
        rows.append(
            {
                "release_id": s.release_id,
                "scenario_id": s.scenario_id,
                "environment": "DEV",
                "dev_window_start": dev_start,
                "dev_window_end": dev_end,
                "target_test_promotion": test_target,
                "release_stream": "phase4-v2",
            }
        )
    return rows


def build_requirements_rows(
    alias_intensity: float,
    missing_field_rate: float,
    rng: random.Random,
) -> List[Dict[str, str]]:
    rows = []
    for req in BASE_REQUIREMENTS:
        module_alias = choose_module_alias(req["module"], alias_intensity, rng)
        rows.append(
            {
                "requirement_id": req["requirement_id"],
                "description": req["description"],
                "priority": req["priority"],
                "module": module_alias,
                "mandatory_for_phase4": req["mandatory_for_phase4"],
                "domain_area": maybe_blank(req["domain_area"], missing_field_rate, rng),
                "verification_hint": maybe_blank(
                    req["verification_hint"], missing_field_rate, rng
                ),
            }
        )
    return rows


def build_version_rows_for_scenario(
    spec: ScenarioSpec,
    alias_intensity: float,
    contradiction_rate: float,
    rng: random.Random,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mismatch_module = "monitoring-core"

    for module in CANONICAL_MODULES:
        planned = BASE_PLANNED_VERSIONS[module]
        deployed = planned

        if spec.mandatory_version_mismatch and module == mismatch_module:
            deployed = lower_patch(planned, delta=1)
        elif (
            spec.expected_decision == "GO"
            and module == "ui-backend"
            and rng.random() < 0.4
        ):
            # harmless non-mandatory drift
            deployed = bump_patch(planned, delta=1)

        module_name = choose_module_alias(module, alias_intensity, rng)

        # controlled inconsistency: sometimes keep version_match column stale
        if rng.random() < contradiction_rate and module == mismatch_module:
            # stale declaration is realistic but policy still checks planned!=deployed
            version_match = "true" if planned != deployed else "false"
        else:
            version_match = "true" if planned == deployed else "false"

        rows.append(
            {
                "scenario_id": spec.scenario_id,
                "release_id": spec.release_id,
                "environment": "DEV",
                "module": module_name,
                "planned_version": planned,
                "deployed_version": deployed,
                "mandatory_for_phase4": str(module != "ui-backend").lower(),
                "version_match": version_match,
                "source_system": "pipeline-export-v2",
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Artifact builders
# ---------------------------------------------------------------------------


def build_deploy_log(
    spec: ScenarioSpec,
    alias_intensity: float,
    contradiction_rate: float,
    ambiguity_bias: float,
    rng: random.Random,
    base_time: datetime,
) -> str:
    lines: List[str] = []
    lines.append(
        f"{iso_time(base_time, 0)} INFO  [orchestrator] Start deployment candidate={spec.release_id} scenario={spec.scenario_id}"
    )
    lines.append(f"{iso_time(base_time, 1)} INFO  [orchestrator] Environment=DEV")
    lines.append(f"{iso_time(base_time, 2)} INFO  [registry] Pull images count=6")

    offset = 3
    for module in CANONICAL_MODULES:
        comp = choose_module_alias(module, alias_intensity, rng)
        lines.append(f"{iso_time(base_time, offset)} INFO  [{comp}] container started")
        offset += 1

    if spec.non_blocking_warning:
        comp = choose_module_alias("analytics-api", alias_intensity, rng)
        lines.append(
            f"{iso_time(base_time, offset)} WARN  [{comp}] transient downstream timeout, retrying"
        )
        offset += 1

    if spec.recoverable_error and not spec.critical_log_error:
        comp = choose_module_alias("event-router", alias_intensity, rng)
        lines.append(
            f"{iso_time(base_time, offset)} ERROR [{comp}] temporary handshake failure"
        )
        offset += 1
        lines.append(
            f"{iso_time(base_time, offset)} INFO  [{comp}] recovered after retry"
        )
        offset += 1

    if spec.critical_log_error:
        comp = choose_module_alias("monitoring-core", alias_intensity, rng)
        lines.append(
            f"{iso_time(base_time, offset)} ERROR [{comp}] rule-set checksum mismatch"
        )
        offset += 1
        lines.append(
            f"{iso_time(base_time, offset)} CRITICAL [{comp}] runtime bootstrap failed"
        )
        offset += 1
        lines.append(
            f"{iso_time(base_time, offset)} ERROR [orchestrator] deployment marked unstable"
        )
        offset += 1
    else:
        if rng.random() < contradiction_rate * 0.5:
            lines.append(
                f"{iso_time(base_time, offset)} INFO  [orchestrator] partial rollback not required"
            )
            offset += 1
        lines.append(
            f"{iso_time(base_time, offset)} INFO  [orchestrator] deployment completed successfully"
        )
        offset += 1

    if rng.random() < ambiguity_bias:
        lines.append(
            "NOTE: observed behavior within tolerance window; monitor next validation cycle."
        )

    return "\n".join(lines) + "\n"


def build_service_health_report(
    spec: ScenarioSpec,
    alias_intensity: float,
    contradiction_rate: float,
    missing_field_rate: float,
    rng: random.Random,
    base_time: datetime,
) -> Dict[str, object]:
    services = []
    unhealthy_target = "monitoring-core"

    for module in CANONICAL_MODULES:
        service_name = choose_module_alias(module, alias_intensity, rng)
        status = "healthy"
        reason = "ok"

        if spec.unhealthy_service and module == unhealthy_target:
            status = "failed" if rng.random() < 0.5 else "unhealthy"
            reason = "readiness probe timeout while fetching runtime rules"

        # non-critical degradation for realism
        if (
            not spec.unhealthy_service
            and module == "analytics-api"
            and spec.non_blocking_warning
            and rng.random() < 0.5
        ):
            status = "degraded"
            reason = "startup retry observed, recovered"

        services.append(
            {
                "service": service_name,
                "status": status,
                "critical": module in CRITICAL_SERVICES,
                "reason": maybe_blank(reason, missing_field_rate, rng),
            }
        )

    critical_unhealthy = any(
        svc["critical"] and str(svc["status"]).lower() not in {"healthy", "ok", "up"}
        for svc in services
    )

    overall = "healthy"
    if critical_unhealthy:
        overall = "degraded"

    # controlled contradiction: health narrative mismatch
    if spec.inconsistent_health_narrative and rng.random() < max(
        0.2, contradiction_rate
    ):
        overall = "healthy"

    report = {
        "scenario_id": spec.scenario_id,
        "release_id": spec.release_id,
        "environment": "DEV",
        "generated_at": maybe_blank(
            iso_time(base_time, 20), missing_field_rate * 0.4, rng
        ),
        "overall_status": overall,
        "services": services,
        "report_version": "2.0",
        "collector": "health-aggregator-v2",
    }
    return report


def build_email_thread(
    spec: ScenarioSpec,
    contradiction_rate: float,
    ambiguity_bias: float,
    rng: random.Random,
    base_time: datetime,
) -> str:
    t0 = iso_time(base_time, 8)
    t1 = iso_time(base_time, 24)
    t2 = iso_time(base_time, 48)

    lines: List[str] = []
    lines.append(f"Subject: [{spec.release_id}] DEV readiness discussion")
    lines.append(f"Time: {t0}")
    lines.append("From: qa.lead@company.example")
    lines.append("To: release.manager@company.example")
    lines.append("")

    if spec.open_blocker_email:
        lines.append("Blocker remains OPEN.")
        lines.append(
            "Blocking symptom: alarm notifications do not propagate under failover."
        )
        lines.append("Action: hold DEV->TEST promotion until fix evidence is attached.")
        lines.append("Status: OPEN BLOCKER")
    elif spec.unmet_conditional:
        lines.append("Conditional clearance only.")
        lines.append(
            "Retest REQUIRED before DEV->TEST promotion due to updated threshold policy."
        )
        lines.append("Current state: evidence missing for required retest execution.")
        lines.append("Status: CONDITIONAL_UNMET")
    else:
        lines.append("No open blockers identified in DEV validation checkpoint.")
        if spec.non_blocking_warning:
            lines.append(
                "Observed transient timeout but behavior recovered within allowed window."
            )
            if rng.random() < ambiguity_bias:
                lines.append(
                    "Recommendation: optional follow-up retest in next cycle (non-blocking)."
                )
        lines.append("Status: NONE")

    # message 2
    lines.append("")
    lines.append(f"Time: {t1}")
    lines.append("From: dev.lead@company.example")
    lines.append("To: qa.lead@company.example")
    lines.append("")

    if spec.critical_log_error:
        lines.append(
            "Deployment instability reproduced with runtime bootstrap failure."
        )
        lines.append("Fix not validated yet. Block remains active.")
    elif spec.open_blocker_email:
        lines.append("Patch is in progress; validated fix not available.")
    elif spec.unmet_conditional:
        lines.append("Retest package prepared, execution pending environment slot.")
    else:
        lines.append("All deployment checks completed on current candidate.")
        lines.append("No production-impacting blockers detected.")

    # optional contradiction message (kept safe for single-gate scenarios)
    contradiction_allowed = not (
        spec.expected_decision == "HOLD"
        and (
            (spec.open_blocker_email and len(spec.primary_rules) == 1)
            or (spec.unmet_conditional and len(spec.primary_rules) == 1)
        )
    )
    if contradiction_allowed and rng.random() < contradiction_rate:
        lines.append("")
        lines.append(f"Time: {t2}")
        lines.append("From: release.coordinator@company.example")
        lines.append("To: qa.lead@company.example")
        lines.append("")
        lines.append(
            "Thread includes mixed updates from parallel validation activities."
        )
        lines.append("Some remarks may refer to older candidate snapshots.")
        if spec.expected_decision == "GO":
            lines.append("Status: RESOLVED")
        else:
            lines.append("Status: OPEN")

    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Labels / catalog
# ---------------------------------------------------------------------------


def build_label_rows(scenarios: List[ScenarioSpec]) -> List[Dict[str, str]]:
    rows = []
    for s in scenarios:
        rows.append(
            {
                "scenario_id": s.scenario_id,
                "release_id": s.release_id,
                "environment": "DEV",
                "expected_decision": s.expected_decision,
                "scenario_type": "MIX"
                if s.ambiguity_level != "low"
                else ("CLEAR_GO" if s.expected_decision == "GO" else "CLEAR_HOLD"),
                "ambiguity_level": s.ambiguity_level,
                "taxonomy": s.taxonomy,
                "primary_triggered_rules": "|".join(s.primary_rules),
                "triggered_conditions": "|".join(scenario_rule_flags(s)),
                "rationale": s.rationale,
            }
        )
    return rows


def build_catalog_rows(scenarios: List[ScenarioSpec]) -> List[Dict[str, str]]:
    rows = []
    for s in scenarios:
        rows.append(
            {
                "scenario_id": s.scenario_id,
                "release_id": s.release_id,
                "taxonomy": s.taxonomy,
                "ambiguity_level": s.ambiguity_level,
                "expected_decision": s.expected_decision,
                "primary_rules": "|".join(s.primary_rules),
                "unhealthy_service": str(s.unhealthy_service).lower(),
                "critical_log_error": str(s.critical_log_error).lower(),
                "open_blocker_email": str(s.open_blocker_email).lower(),
                "mandatory_version_mismatch": str(s.mandatory_version_mismatch).lower(),
                "unmet_conditional": str(s.unmet_conditional).lower(),
                "non_blocking_warning": str(s.non_blocking_warning).lower(),
                "recoverable_error": str(s.recoverable_error).lower(),
                "inconsistent_health_narrative": str(
                    s.inconsistent_health_narrative
                ).lower(),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Generation pipeline
# ---------------------------------------------------------------------------


def generate_dataset(
    output_dir: Path,
    seed: int,
    force: bool,
    alias_intensity: float,
    contradiction_rate: float,
    missing_field_rate: float,
    ambiguity_bias: float,
    scenario_limit: int | None,
) -> None:
    alias_intensity = clamp_01(alias_intensity)
    contradiction_rate = clamp_01(contradiction_rate)
    missing_field_rate = clamp_01(missing_field_rate)
    ambiguity_bias = clamp_01(ambiguity_bias)

    scenarios = SCENARIOS[: scenario_limit or len(SCENARIOS)]
    if not scenarios:
        raise ValueError(
            "No scenarios selected. Increase --scenario-limit or use default."
        )

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

    requirements_rows = build_requirements_rows(
        alias_intensity, missing_field_rate, rng
    )
    calendar_rows = build_release_calendar_rows(scenarios, start_date)

    version_rows: List[Dict[str, str]] = []
    for idx, s in enumerate(scenarios):
        base_time = generation_time + timedelta(hours=idx * 4)

        version_rows.extend(
            build_version_rows_for_scenario(
                s,
                alias_intensity=alias_intensity,
                contradiction_rate=contradiction_rate,
                rng=rng,
            )
        )

        deploy_log = build_deploy_log(
            s,
            alias_intensity=alias_intensity,
            contradiction_rate=contradiction_rate,
            ambiguity_bias=ambiguity_bias,
            rng=rng,
            base_time=base_time,
        )
        (deploy_dir / f"{s.scenario_id}.log").write_text(deploy_log, encoding="utf-8")

        health_report = build_service_health_report(
            s,
            alias_intensity=alias_intensity,
            contradiction_rate=contradiction_rate,
            missing_field_rate=missing_field_rate,
            rng=rng,
            base_time=base_time,
        )
        (health_dir / f"{s.scenario_id}.json").write_text(
            json.dumps(health_report, indent=2), encoding="utf-8"
        )

        email_thread = build_email_thread(
            s,
            contradiction_rate=contradiction_rate,
            ambiguity_bias=ambiguity_bias,
            rng=rng,
            base_time=base_time,
        )
        (email_dir / f"{s.scenario_id}.txt").write_text(email_thread, encoding="utf-8")

    # Write shared files
    write_csv(
        output_dir / "requirements_master.csv",
        fieldnames=[
            "requirement_id",
            "description",
            "priority",
            "module",
            "mandatory_for_phase4",
            "domain_area",
            "verification_hint",
        ],
        rows=requirements_rows,
    )

    write_csv(
        output_dir / "release_calendar.csv",
        fieldnames=[
            "release_id",
            "scenario_id",
            "environment",
            "dev_window_start",
            "dev_window_end",
            "target_test_promotion",
            "release_stream",
        ],
        rows=calendar_rows,
    )

    version_fields = [
        "scenario_id",
        "release_id",
        "environment",
        "module",
        "planned_version",
        "deployed_version",
        "mandatory_for_phase4",
        "version_match",
        "source_system",
    ]
    write_csv(
        output_dir / "modules_versions.csv",
        fieldnames=version_fields,
        rows=version_rows,
    )
    write_csv(
        output_dir / "phase4_modules_versions.csv",
        fieldnames=version_fields,
        rows=version_rows,
    )

    labels = build_label_rows(scenarios)
    write_csv(
        output_dir / "phase4_decision_labels.csv",
        fieldnames=[
            "scenario_id",
            "release_id",
            "environment",
            "expected_decision",
            "scenario_type",
            "ambiguity_level",
            "taxonomy",
            "primary_triggered_rules",
            "triggered_conditions",
            "rationale",
        ],
        rows=labels,
    )

    catalog = build_catalog_rows(scenarios)
    write_csv(
        output_dir / "phase4_v2_scenario_catalog.csv",
        fieldnames=[
            "scenario_id",
            "release_id",
            "taxonomy",
            "ambiguity_level",
            "expected_decision",
            "primary_rules",
            "unhealthy_service",
            "critical_log_error",
            "open_blocker_email",
            "mandatory_version_mismatch",
            "unmet_conditional",
            "non_blocking_warning",
            "recoverable_error",
            "inconsistent_health_narrative",
        ],
        rows=catalog,
    )

    manifest = {
        "dataset": "phase4_v2",
        "generated_at": generation_time.isoformat(),
        "seed": seed,
        "scenario_count": len(scenarios),
        "controls": {
            "alias_intensity": alias_intensity,
            "contradiction_rate": contradiction_rate,
            "missing_field_rate": missing_field_rate,
            "ambiguity_bias": ambiguity_bias,
        },
        "decision_distribution": {
            "GO": sum(1 for s in scenarios if s.expected_decision == "GO"),
            "HOLD": sum(1 for s in scenarios if s.expected_decision == "HOLD"),
        },
        "policy_reference": {
            "hold_conditions": [
                "critical_service_unhealthy",
                "unresolved_error_or_critical_log",
                "open_blocker_email",
                "mandatory_version_mismatch",
                "unmet_conditional_requirement",
            ],
            "go_rule": "GO only when no hold condition is detected",
        },
        "files": {
            "requirements": "requirements_master.csv",
            "release_calendar": "release_calendar.csv",
            "versions": "modules_versions.csv",
            "phase4_versions": "phase4_modules_versions.csv",
            "labels": "phase4_decision_labels.csv",
            "scenario_catalog": "phase4_v2_scenario_catalog.csv",
            "deploy_logs": "dev_deploy_logs/",
            "health_reports": "service_health_reports/",
            "emails": "dev_blockers_emails/",
        },
    }
    (output_dir / "scenario_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Phase 4 v2 dataset with realism controls."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("synthetic_data/v2"),
        help="Output directory for generated dataset (default: synthetic_data/v2)",
    )
    parser.add_argument(
        "--seed", type=int, default=4242, help="Deterministic RNG seed (default: 4242)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into non-empty output directory",
    )
    parser.add_argument(
        "--alias-intensity",
        type=float,
        default=0.65,
        help="0..1 probability of aliasing module names across artifacts (default: 0.65)",
    )
    parser.add_argument(
        "--contradiction-rate",
        type=float,
        default=0.25,
        help="0..1 probability of injecting non-fatal documentary inconsistencies (default: 0.25)",
    )
    parser.add_argument(
        "--missing-field-rate",
        type=float,
        default=0.08,
        help="0..1 probability of blanking optional descriptive fields (default: 0.08)",
    )
    parser.add_argument(
        "--ambiguity-bias",
        type=float,
        default=0.35,
        help="0..1 probability of adding ambiguous narrative language (default: 0.35)",
    )
    parser.add_argument(
        "--scenario-limit",
        type=int,
        default=None,
        help="Optional limit for number of scenarios generated (default: all)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_dataset(
        output_dir=args.output_dir,
        seed=args.seed,
        force=args.force,
        alias_intensity=args.alias_intensity,
        contradiction_rate=args.contradiction_rate,
        missing_field_rate=args.missing_field_rate,
        ambiguity_bias=args.ambiguity_bias,
        scenario_limit=args.scenario_limit,
    )
    print(f"Phase 4 v2 dataset generated at: {args.output_dir}")


if __name__ == "__main__":
    main()
