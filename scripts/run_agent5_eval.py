#!/usr/bin/env python3
"""
Benchmark runner for Agent 5 across Phase 5 v1/v2 datasets.

Examples:
  python scripts/run_agent5_eval.py
  python scripts/run_agent5_eval.py --datasets synthetic_data/phase5/v1 synthetic_data/phase5/v2 --pretty
  python scripts/run_agent5_eval.py --output evaluations/agent5_benchmark_report.json --write-per-dataset
  python scripts/run_agent5_eval.py --strict

Behavior:
- Runs Agent 5 on each dataset root.
- Produces per-dataset evaluation metrics (accuracy, false_go, false_hold, etc).
- Optionally writes:
  1) a consolidated JSON report
  2) per-dataset predictions and evaluation JSON files
- Exits non-zero in strict mode if any dataset fails acceptance thresholds.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Ensure project root is importable when script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent5.agent import Agent5Config, Agent5LangChainOrchestrator


@dataclass(frozen=True)
class AcceptanceThresholds:
    min_accuracy: float = 0.90
    max_false_go_rate: float = 0.02
    max_false_hold_rate: float = 0.20
    min_schema_validity_rate: float = 1.00


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Agent 5 benchmark evaluation on Phase 5 datasets."
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["synthetic_data/phase5/v1", "synthetic_data/phase5/v2"],
        help=(
            "Dataset roots to evaluate "
            "(default: synthetic_data/phase5/v1 synthetic_data/phase5/v2)"
        ),
    )
    parser.add_argument(
        "--output",
        default="evaluations/agent5_benchmark_report.json",
        help="Consolidated JSON report output path",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print console and JSON output",
    )
    parser.add_argument(
        "--write-per-dataset",
        action="store_true",
        help="Write per-dataset predictions/evaluation JSON files under evaluations/",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail (non-zero exit) if acceptance thresholds are not met",
    )
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=0.90,
        help="Strict mode threshold: minimum acceptable accuracy (default: 0.90)",
    )
    parser.add_argument(
        "--max-false-go-rate",
        type=float,
        default=0.02,
        help="Strict mode threshold: maximum acceptable false GO rate (default: 0.02)",
    )
    parser.add_argument(
        "--max-false-hold-rate",
        type=float,
        default=0.20,
        help="Strict mode threshold: maximum acceptable false HOLD rate (default: 0.20)",
    )
    parser.add_argument(
        "--min-schema-validity-rate",
        type=float,
        default=1.00,
        help="Strict mode threshold: minimum schema validity rate (default: 1.00)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Use deterministic summary path only",
    )
    return parser.parse_args()


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_dataset_name(dataset_root: str) -> str:
    p = Path(dataset_root)
    name = p.name.strip() or "dataset"
    return name.replace(" ", "_")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _schema_validity_rate(predictions: Sequence[Dict[str, Any]]) -> float:
    if not predictions:
        return 0.0
    valid = 0
    total = 0
    for row in predictions:
        if not isinstance(row, dict):
            continue
        total += 1
        if bool(row.get("schema_validation", {}).get("valid", False)):
            valid += 1
    if total == 0:
        return 0.0
    return valid / total


def _evaluate_one_dataset(
    dataset_root: str,
    use_llm_summary: bool,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "dataset_root": dataset_root,
        "dataset_name": _normalize_dataset_name(dataset_root),
        "status": "unknown",
        "error": None,
        "metrics": {},
        "predictions": [],
        "rows": [],
        "dataset_validation": {},
    }

    root_path = Path(dataset_root)
    if not root_path.exists():
        result["status"] = "skipped"
        result["error"] = f"Dataset path does not exist: {dataset_root}"
        return result

    labels_path = root_path / "phase5_decision_labels.csv"
    if not labels_path.exists():
        result["status"] = "skipped"
        result["error"] = f"Labels file missing: {labels_path}"
        return result

    try:
        agent = Agent5LangChainOrchestrator(
            config=Agent5Config(
                dataset_root=dataset_root,
                use_llm_summary=use_llm_summary,
                strict_schema=False,
            ),
            llm_generate=None,
        )

        validation_report = agent.validate_dataset()
        result["dataset_validation"] = validation_report

        if not validation_report.get("exists", False):
            result["status"] = "failed"
            result["error"] = (
                f"Dataset root not found during validation: {dataset_root}"
            )
            return result

        missing_required = validation_report.get("missing_required", [])
        if missing_required:
            result["status"] = "failed"
            result["error"] = "Dataset missing required files: " + ", ".join(
                missing_required
            )
            return result

        predictions = list(agent.assess_all_scenarios())
        evaluation = agent.evaluate_against_labels(
            predictions=predictions,
            labels_csv_path=str(labels_path),
        )

        schema_rate = _schema_validity_rate(predictions)

        result["status"] = "ok"
        result["predictions"] = predictions
        result["rows"] = evaluation.get("rows", [])
        result["metrics"] = {
            "total_scenarios": evaluation.get("total_scenarios", 0),
            "evaluated_scenarios": evaluation.get("evaluated_scenarios", 0),
            "missing_predictions": evaluation.get("missing_predictions", 0),
            "matched": evaluation.get("matched", 0),
            "accuracy": evaluation.get("accuracy", 0.0),
            "false_go": evaluation.get("false_go", 0),
            "false_hold": evaluation.get("false_hold", 0),
            "false_go_rate": evaluation.get("false_go_rate", 0.0),
            "false_hold_rate": evaluation.get("false_hold_rate", 0.0),
            "schema_validity_rate": round(schema_rate, 4),
        }
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)

    return result


def _acceptance_check(
    dataset_result: Dict[str, Any],
    thresholds: AcceptanceThresholds,
) -> Dict[str, Any]:
    status = dataset_result.get("status")
    if status != "ok":
        return {
            "passed": False,
            "reasons": [f"Dataset status is {status!r}"],
        }

    metrics = dataset_result.get("metrics", {})
    accuracy = _safe_float(metrics.get("accuracy"))
    false_go_rate = _safe_float(metrics.get("false_go_rate"))
    false_hold_rate = _safe_float(metrics.get("false_hold_rate"))
    schema_validity_rate = _safe_float(metrics.get("schema_validity_rate"))

    reasons: List[str] = []

    if accuracy < thresholds.min_accuracy:
        reasons.append(
            f"accuracy {accuracy:.4f} < min_accuracy {thresholds.min_accuracy:.4f}"
        )
    if false_go_rate > thresholds.max_false_go_rate:
        reasons.append(
            f"false_go_rate {false_go_rate:.4f} > max_false_go_rate {thresholds.max_false_go_rate:.4f}"
        )
    if false_hold_rate > thresholds.max_false_hold_rate:
        reasons.append(
            f"false_hold_rate {false_hold_rate:.4f} > max_false_hold_rate {thresholds.max_false_hold_rate:.4f}"
        )
    if schema_validity_rate < thresholds.min_schema_validity_rate:
        reasons.append(
            f"schema_validity_rate {schema_validity_rate:.4f} < min_schema_validity_rate {thresholds.min_schema_validity_rate:.4f}"
        )

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
    }


def _build_global_summary(
    per_dataset: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    ok = [d for d in per_dataset if d.get("status") == "ok"]
    skipped = [d for d in per_dataset if d.get("status") == "skipped"]
    failed = [d for d in per_dataset if d.get("status") == "failed"]

    evaluated_total = 0
    matched_total = 0
    false_go_total = 0
    false_hold_total = 0
    schema_validity_weighted_sum = 0.0

    for d in ok:
        m = d.get("metrics", {})
        evaluated = _safe_int(m.get("evaluated_scenarios", 0))
        matched = _safe_int(m.get("matched", 0))
        false_go = _safe_int(m.get("false_go", 0))
        false_hold = _safe_int(m.get("false_hold", 0))
        schema_rate = _safe_float(m.get("schema_validity_rate", 0.0))

        evaluated_total += evaluated
        matched_total += matched
        false_go_total += false_go
        false_hold_total += false_hold
        schema_validity_weighted_sum += schema_rate * max(evaluated, 1)

    aggregate_accuracy = (matched_total / evaluated_total) if evaluated_total else 0.0
    aggregate_false_go_rate = (
        false_go_total / evaluated_total if evaluated_total else 0.0
    )
    aggregate_false_hold_rate = (
        false_hold_total / evaluated_total if evaluated_total else 0.0
    )

    if evaluated_total:
        aggregate_schema_validity = schema_validity_weighted_sum / evaluated_total
    else:
        aggregate_schema_validity = 0.0

    return {
        "datasets_total": len(per_dataset),
        "datasets_ok": len(ok),
        "datasets_skipped": len(skipped),
        "datasets_failed": len(failed),
        "aggregate": {
            "evaluated_scenarios": evaluated_total,
            "matched": matched_total,
            "accuracy": round(aggregate_accuracy, 4),
            "false_go": false_go_total,
            "false_hold": false_hold_total,
            "false_go_rate": round(aggregate_false_go_rate, 4),
            "false_hold_rate": round(aggregate_false_hold_rate, 4),
            "schema_validity_rate": round(aggregate_schema_validity, 4),
        },
    }


def _write_json(path: Path, payload: Dict[str, Any], pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2 if pretty else None)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()

    thresholds = AcceptanceThresholds(
        min_accuracy=args.min_accuracy,
        max_false_go_rate=args.max_false_go_rate,
        max_false_hold_rate=args.max_false_hold_rate,
        min_schema_validity_rate=args.min_schema_validity_rate,
    )

    per_dataset: List[Dict[str, Any]] = []
    strict_failures: List[Dict[str, Any]] = []

    for dataset_root in args.datasets:
        ds_result = _evaluate_one_dataset(
            dataset_root=dataset_root,
            use_llm_summary=not args.no_llm,
        )

        acceptance = _acceptance_check(ds_result, thresholds)
        ds_result["acceptance"] = acceptance
        per_dataset.append(ds_result)

        if args.strict and not acceptance.get("passed", False):
            strict_failures.append(
                {
                    "dataset_root": dataset_root,
                    "reasons": acceptance.get("reasons", []),
                    "status": ds_result.get("status"),
                }
            )

        if args.write_per_dataset:
            dataset_name = _normalize_dataset_name(dataset_root)
            safe_name = dataset_name.replace("/", "_")
            pred_path = Path("evaluations") / f"agent5_{safe_name}_predictions.json"
            eval_path = Path("evaluations") / f"agent5_{safe_name}_evaluation.json"

            _write_json(
                pred_path,
                {
                    "dataset_root": dataset_root,
                    "predictions": ds_result.get("predictions", []),
                },
                args.pretty,
            )
            _write_json(
                eval_path,
                {
                    "dataset_root": dataset_root,
                    "status": ds_result.get("status"),
                    "error": ds_result.get("error"),
                    "metrics": ds_result.get("metrics", {}),
                    "acceptance": ds_result.get("acceptance", {}),
                    "rows": ds_result.get("rows", []),
                },
                args.pretty,
            )

    report: Dict[str, Any] = {
        "agent": "agent5",
        "runner": "scripts/run_agent5_eval.py",
        "generated_at_utc": _timestamp(),
        "thresholds": asdict(thresholds),
        "summary": _build_global_summary(per_dataset),
        "datasets": per_dataset,
        "strict_mode": {
            "enabled": bool(args.strict),
            "failed": len(strict_failures) > 0,
            "failures": strict_failures,
        },
    }

    output_path = Path(args.output)
    _write_json(output_path, report, args.pretty)

    print(json.dumps(report, indent=2 if args.pretty else None))

    if args.strict and strict_failures:
        sys.exit(2)


if __name__ == "__main__":
    main()
