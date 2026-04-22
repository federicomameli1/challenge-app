#!/usr/bin/env python3
"""
CLI entrypoint to run Agent 4 for one Phase 4 scenario.

Usage examples:
  python scripts/run_agent4.py --scenario-id S4-001
  python scripts/run_agent4.py --scenario-id S4-008 --dataset-root synthetic_data/v1 --check-label
  python scripts/run_agent4.py --scenario-id S4-010 --output evaluations/S4-010_output.json --pretty
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Ensure project root is importable when script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent4.explanation import ExplanationContext, build_explanation_with_optional_llm
from agent4.ingestion import IngestionError, Phase4Ingestion
from agent4.models import validate_output_schema
from agent4.normalization import normalize_evidence_bundle
from agent4.policy import Phase4PolicyEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Agent 4 readiness assessment for one scenario."
    )
    parser.add_argument(
        "--scenario-id",
        required=True,
        help="Scenario identifier, e.g. S4-001",
    )
    parser.add_argument(
        "--dataset-root",
        default="synthetic_data/v1",
        help="Dataset root directory (default: synthetic_data/v1)",
    )
    parser.add_argument(
        "--release-id",
        default=None,
        help="Optional release_id consistency filter",
    )
    parser.add_argument(
        "--check-label",
        action="store_true",
        help="Compare output decision against phase4_decision_labels.csv",
    )
    parser.add_argument(
        "--fail-on-label-mismatch",
        action="store_true",
        help="Exit non-zero if --check-label is enabled and decision mismatches expected label",
    )
    parser.add_argument(
        "--strict-schema",
        action="store_true",
        help="Exit non-zero if output does not match Agent 4 output schema",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path to save JSON payload",
    )
    return parser.parse_args()


def _source_path(bundle: Any, key: str, fallback: str) -> str:
    ref = bundle.source_references.get(key)
    if ref is None:
        return fallback
    return ref.path


def _load_expected_label(
    dataset_root: Path, scenario_id: str
) -> Tuple[Optional[str], Optional[str]]:
    labels_path = dataset_root / "phase4_decision_labels.csv"
    if not labels_path.exists():
        return None, f"Labels file not found: {labels_path}"

    with labels_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("scenario_id") or "").strip() == scenario_id:
                expected = (row.get("expected_decision") or "").strip().upper()
                if expected in {"GO", "HOLD"}:
                    return expected, None
                return (
                    None,
                    f"Invalid expected_decision for {scenario_id}: {expected!r}",
                )

    return None, f"Scenario {scenario_id} not found in labels file."


def run_agent4(args: argparse.Namespace) -> Dict[str, Any]:
    ingestion = Phase4Ingestion(dataset_root=args.dataset_root)

    # Optional pre-flight diagnostics.
    dataset_report = ingestion.validate_dataset()
    if not dataset_report.get("exists", False):
        raise RuntimeError(
            f"Dataset root does not exist: {args.dataset_root}. "
            f"Run generator first: python scripts/generate_phase4_dataset.py"
        )
    missing_required = dataset_report.get("missing_required", [])
    if missing_required:
        raise RuntimeError(
            f"Dataset missing required files: {', '.join(missing_required)}"
        )

    raw = ingestion.ingest(
        scenario_id=args.scenario_id,
        release_id=args.release_id,
    )

    normalized = normalize_evidence_bundle(
        requirements_rows=raw.requirements,
        version_rows=raw.module_versions,
        deploy_log_text=raw.deploy_log,
        health_report=raw.service_health_report,
        email_thread_text=raw.blocker_email_thread,
        requirements_source=_source_path(
            raw, "requirements", "requirements_master.csv"
        ),
        versions_source=_source_path(
            raw, "module_versions", "phase4_modules_versions.csv"
        ),
        deploy_log_source=_source_path(
            raw, "deploy_log", f"dev_deploy_logs/{raw.scenario_id}.log"
        ),
        health_source=_source_path(
            raw,
            "service_health_report",
            f"service_health_reports/{raw.scenario_id}.json",
        ),
        email_source=_source_path(
            raw, "blocker_email_thread", f"dev_blockers_emails/{raw.scenario_id}.txt"
        ),
    )

    policy_engine = Phase4PolicyEngine()
    findings = policy_engine.evaluate(
        normalized,
        environment=raw.environment,
    )

    non_blocking_warning = any(
        event.severity == "WARN" for event in normalized.deploy_logs
    )

    context = ExplanationContext(
        scenario_id=raw.scenario_id,
        release_id=raw.release_id,
        environment=raw.environment,
        findings=findings,
        non_blocking_warning=non_blocking_warning,
        evidence_conflict=False,
        evidence_incomplete=False,
    )

    # Deterministic explanation path (no external LLM call required).
    output = build_explanation_with_optional_llm(
        context=context,
        llm_generate=None,
    )

    payload = output.to_dict()
    payload["meta"] = {
        "agent": "agent4",
        "dataset_root": str(Path(args.dataset_root)),
        "scenario_id": raw.scenario_id,
        "release_id": raw.release_id,
    }

    valid, schema_errors = validate_output_schema(payload)
    payload["schema_validation"] = {
        "valid": valid,
        "errors": schema_errors,
    }

    if args.check_label:
        expected, err = _load_expected_label(Path(args.dataset_root), raw.scenario_id)
        if err is not None:
            payload["evaluation"] = {
                "label_check_performed": False,
                "error": err,
            }
        else:
            actual = payload.get("decision")
            match = actual == expected
            payload["evaluation"] = {
                "label_check_performed": True,
                "expected_decision": expected,
                "actual_decision": actual,
                "match": match,
            }

    return payload


def main() -> None:
    args = parse_args()

    try:
        payload = run_agent4(args)
    except IngestionError as exc:
        print(
            json.dumps(
                {
                    "error": "ingestion_error",
                    "message": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": "agent4_runtime_error",
                    "message": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    json_text = json.dumps(payload, indent=2 if args.pretty else None)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json_text + ("\n" if not json_text.endswith("\n") else ""), encoding="utf-8"
        )

    print(json_text)

    if args.strict_schema and not payload.get("schema_validation", {}).get(
        "valid", False
    ):
        sys.exit(1)

    if args.check_label and args.fail_on_label_mismatch:
        evaluation = payload.get("evaluation", {})
        if evaluation.get("label_check_performed") and not evaluation.get(
            "match", False
        ):
            sys.exit(2)


if __name__ == "__main__":
    main()
