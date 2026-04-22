#!/usr/bin/env python3
"""
CLI entrypoint for LangChain-based Agent 5 runner.

This script uses the shared LangChain pipeline module (`agent5.lc_pipeline`)
so orchestration logic remains centralized and migration to LangGraph stays simple.

Usage examples:
  python scripts/run_agent5_langchain.py --scenario-id P5-001 --dataset-root synthetic_data/phase5/v1 --check-label --pretty
  python scripts/run_agent5_langchain.py --evaluate-all --dataset-root synthetic_data/phase5/v2 --check-label --pretty
  python scripts/run_agent5_langchain.py --evaluate-all --dataset-root synthetic_data/phase5/v1 --output evaluations/agent5_langchain_v1.json --pretty
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is importable when script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent5.lc_pipeline import Agent5LCError, LangChainAgent5Pipeline, LCPipelineConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Agent 5 via shared LangChain pipeline."
    )
    parser.add_argument(
        "--scenario-id",
        default=None,
        help="Scenario identifier, e.g. P5-001. Required unless --evaluate-all is used.",
    )
    parser.add_argument(
        "--dataset-root",
        default="synthetic_data/phase5/v1",
        help="Dataset root directory (default: synthetic_data/phase5/v1)",
    )
    parser.add_argument(
        "--release-id",
        default=None,
        help="Optional release_id consistency filter for single-scenario mode",
    )
    parser.add_argument(
        "--evaluate-all",
        action="store_true",
        help="Run pipeline for every scenario in release calendar and report aggregate metrics",
    )
    parser.add_argument(
        "--check-label",
        action="store_true",
        help="Compare decision against phase5_decision_labels.csv",
    )
    parser.add_argument(
        "--labels-path",
        default=None,
        help="Optional custom labels CSV path (default: <dataset-root>/phase5_decision_labels.csv)",
    )
    parser.add_argument(
        "--fail-on-label-mismatch",
        action="store_true",
        help="Exit non-zero when label mismatch occurs (single mode, or any mismatch in --evaluate-all mode)",
    )
    parser.add_argument(
        "--strict-schema",
        action="store_true",
        help="Exit non-zero if output schema validation fails",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM summary layer (deterministic summary only)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path to write JSON report",
    )
    return parser.parse_args()


def _labels_path(args: argparse.Namespace) -> Path:
    if args.labels_path:
        return Path(args.labels_path)
    return Path(args.dataset_root) / "phase5_decision_labels.csv"


def _load_expected_label(
    labels_csv: Path, scenario_id: str
) -> Tuple[Optional[str], Optional[str]]:
    if not labels_csv.exists():
        return None, f"Labels file not found: {labels_csv}"

    with labels_csv.open("r", encoding="utf-8", newline="") as f:
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


def _safe_schema_valid(payload: Dict[str, Any]) -> bool:
    return bool(payload.get("schema_validation", {}).get("valid", False))


def _build_pipeline(args: argparse.Namespace) -> LangChainAgent5Pipeline:
    config = LCPipelineConfig(
        dataset_root=args.dataset_root,
        use_llm_summary=not args.no_llm,
        strict_schema=False,  # CLI enforces strict behavior when requested.
    )
    return LangChainAgent5Pipeline(config=config, llm_generate=None)


def _validate_dataset(pipeline: LangChainAgent5Pipeline) -> Dict[str, Any]:
    report = pipeline.validate_dataset()
    if not report.get("exists", False):
        raise RuntimeError(
            f"Dataset root does not exist: {pipeline.config.dataset_root}. Generate dataset first."
        )
    missing_required = report.get("missing_required", [])
    if missing_required:
        raise RuntimeError(
            "Dataset missing required files: {0}".format(", ".join(missing_required))
        )
    return report


def _run_single(
    args: argparse.Namespace,
    pipeline: LangChainAgent5Pipeline,
) -> Dict[str, Any]:
    scenario_id = str(args.scenario_id).strip()
    payload = pipeline.assess_scenario(
        scenario_id=scenario_id,
        release_id=args.release_id,
    )

    if args.check_label:
        labels_path = _labels_path(args)
        expected, err = _load_expected_label(labels_path, scenario_id)
        if err is not None:
            payload["evaluation"] = {
                "label_check_performed": False,
                "error": err,
            }
        else:
            actual = str(payload.get("decision", "")).strip().upper()
            payload["evaluation"] = {
                "label_check_performed": True,
                "expected_decision": expected,
                "actual_decision": actual,
                "match": actual == expected,
            }

    return payload


def _run_all(
    args: argparse.Namespace,
    pipeline: LangChainAgent5Pipeline,
) -> Dict[str, Any]:
    predictions = pipeline.assess_all_scenarios()

    total = len(predictions)
    schema_valid_count = sum(1 for p in predictions if _safe_schema_valid(p))
    schema_validity_rate = (schema_valid_count / total) if total else 0.0

    report: Dict[str, Any] = {
        "agent": "agent5_langchain",
        "dataset_root": str(Path(args.dataset_root)),
        "mode": "evaluate_all",
        "summary": {
            "total_scenarios": total,
            "schema_validity_rate": round(schema_validity_rate, 4),
        },
        "predictions": predictions,
    }

    if args.check_label:
        labels_path = _labels_path(args)
        evaluation = pipeline.evaluate_against_labels(
            predictions=predictions,
            labels_csv_path=str(labels_path),
        )
        report["summary"].update(
            {
                "evaluated_scenarios": evaluation.get("evaluated_scenarios", 0),
                "matched": evaluation.get("matched", 0),
                "accuracy": evaluation.get("accuracy", 0.0),
                "false_go": evaluation.get("false_go", 0),
                "false_hold": evaluation.get("false_hold", 0),
                "false_go_rate": evaluation.get("false_go_rate", 0.0),
                "false_hold_rate": evaluation.get("false_hold_rate", 0.0),
                "missing_predictions": evaluation.get("missing_predictions", 0),
            }
        )
        report["rows"] = evaluation.get("rows", [])
        report["evaluation"] = evaluation

    return report


def _write_output(path: str, payload: Dict[str, Any], pretty: bool) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2 if pretty else None)
    if not text.endswith("\n"):
        text += "\n"
    out_path.write_text(text, encoding="utf-8")


def _has_any_label_mismatch(payload: Dict[str, Any], evaluate_all: bool) -> bool:
    if evaluate_all:
        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            return False
        return any(isinstance(r, dict) and r.get("match") is False for r in rows)

    evaluation = payload.get("evaluation", {})
    if not isinstance(evaluation, dict):
        return False
    return bool(
        evaluation.get("label_check_performed") and not evaluation.get("match", False)
    )


def _has_any_schema_error(payload: Dict[str, Any], evaluate_all: bool) -> bool:
    if evaluate_all:
        predictions = payload.get("predictions", [])
        if not isinstance(predictions, list):
            return True
        return any(
            not _safe_schema_valid(p) for p in predictions if isinstance(p, dict)
        )
    return not _safe_schema_valid(payload)


def main() -> None:
    args = parse_args()

    if not args.evaluate_all and not args.scenario_id:
        print(
            json.dumps(
                {
                    "error": "invalid_arguments",
                    "message": "Provide --scenario-id for single run or use --evaluate-all.",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        pipeline = _build_pipeline(args)
        _validate_dataset(pipeline)

        if args.evaluate_all:
            payload = _run_all(args, pipeline)
        else:
            payload = _run_single(args, pipeline)

    except Agent5LCError as exc:
        print(
            json.dumps(
                {"error": "agent5_langchain_error", "message": str(exc)},
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(
            json.dumps(
                {"error": "agent5_langchain_runtime_error", "message": str(exc)},
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    if args.output:
        _write_output(args.output, payload, args.pretty)

    print(json.dumps(payload, indent=2 if args.pretty else None))

    if args.strict_schema and _has_any_schema_error(payload, args.evaluate_all):
        sys.exit(1)

    if args.check_label and args.fail_on_label_mismatch:
        if _has_any_label_mismatch(payload, args.evaluate_all):
            sys.exit(2)


if __name__ == "__main__":
    main()
