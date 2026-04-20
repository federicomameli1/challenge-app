#!/usr/bin/env python3
"""
Benchmark runner for Agent 4 across v1/v2 datasets.

Examples:
  python scripts/run_agent4_eval.py
  python scripts/run_agent4_eval.py --datasets synthetic_data/v1 synthetic_data/v2 --pretty
  python scripts/run_agent4_eval.py --output evaluations/agent4_benchmark_report.json --write-per-dataset
  python scripts/run_agent4_eval.py --strict

Behavior:
- Runs Agent 4 on each dataset root.
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
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Ensure project root is importable when script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent4.agent import Agent4Config, Agent4Orchestrator


@dataclass(frozen=True)
class AcceptanceThresholds:
    min_accuracy: float = 0.90
    max_false_go_rate: float = 0.05
    max_false_hold_rate: float = 0.20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Agent 4 benchmark evaluation on v1/v2 datasets."
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["synthetic_data/v1", "synthetic_data/v2"],
        help="Dataset roots to evaluate (default: synthetic_data/v1 synthetic_data/v2)",
    )
    parser.add_argument(
        "--output",
        default="evaluations/agent4_benchmark_report.json",
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
        default=0.05,
        help="Strict mode threshold: maximum acceptable false GO rate (default: 0.05)",
    )
    parser.add_argument(
        "--max-false-hold-rate",
        type=float,
        default=0.20,
        help="Strict mode threshold: maximum acceptable false HOLD rate (default: 0.20)",
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
    }

    root_path = Path(dataset_root)
    if not root_path.exists():
        result["status"] = "skipped"
        result["error"] = f"Dataset path does not exist: {dataset_root}"
        return result

    labels_path = root_path / "phase4_decision_labels.csv"
    if not labels_path.exists():
        result["status"] = "skipped"
        result["error"] = f"Labels file missing: {labels_path}"
        return result

    try:
        agent = Agent4Orchestrator(
            config=Agent4Config(
                dataset_root=dataset_root,
                use_llm_summary=use_llm_summary,
            ),
            llm_generate=None,
        )

        predictions = agent.assess_all_scenarios()
        evaluation = agent.evaluate_against_labels(predictions=predictions)

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

    for d in ok:
        m = d.get("metrics", {})
        evaluated_total += int(m.get("evaluated_scenarios", 0) or 0)
        matched_total += int(m.get("matched", 0) or 0)
        false_go_total += int(m.get("false_go", 0) or 0)
        false_hold_total += int(m.get("false_hold", 0) or 0)

    aggregate_accuracy = (matched_total / evaluated_total) if evaluated_total else 0.0
    aggregate_false_go_rate = (
        false_go_total / evaluated_total if evaluated_total else 0.0
    )
    aggregate_false_hold_rate = (
        false_hold_total / evaluated_total if evaluated_total else 0.0
    )

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

        if not acceptance["passed"]:
            strict_failures.append(
                {
                    "dataset_root": dataset_root,
                    "status": ds_result.get("status"),
                    "reasons": acceptance.get("reasons", []),
                }
            )

    summary = _build_global_summary(per_dataset)

    consolidated_report: Dict[str, Any] = {
        "agent": "agent4",
        "report_generated_at_utc": _timestamp(),
        "thresholds": asdict(thresholds),
        "summary": summary,
        "datasets": [],
    }

    # Keep consolidated report compact by default (without full predictions).
    for d in per_dataset:
        consolidated_report["datasets"].append(
            {
                "dataset_root": d.get("dataset_root"),
                "dataset_name": d.get("dataset_name"),
                "status": d.get("status"),
                "error": d.get("error"),
                "metrics": d.get("metrics", {}),
                "acceptance": d.get("acceptance", {}),
            }
        )

    output_path = Path(args.output)
    _write_json(output_path, consolidated_report, pretty=args.pretty)

    if args.write_per_dataset:
        eval_root = PROJECT_ROOT / "evaluations"
        eval_root.mkdir(parents=True, exist_ok=True)

        for d in per_dataset:
            dataset_name = d.get("dataset_name", "dataset")
            payload = {
                "agent": "agent4",
                "dataset_root": d.get("dataset_root"),
                "dataset_name": dataset_name,
                "status": d.get("status"),
                "error": d.get("error"),
                "metrics": d.get("metrics", {}),
                "acceptance": d.get("acceptance", {}),
                "rows": d.get("rows", []),
                "predictions": d.get("predictions", []),
                "generated_at_utc": _timestamp(),
            }
            _write_json(
                eval_root / f"agent4_eval_{dataset_name}.json",
                payload,
                pretty=args.pretty,
            )

    console_payload = {
        "output_report": str(output_path),
        "summary": consolidated_report["summary"],
        "datasets": consolidated_report["datasets"],
    }
    print(json.dumps(console_payload, indent=2 if args.pretty else None))

    if args.strict and strict_failures:
        print(
            json.dumps(
                {
                    "strict_mode": True,
                    "failed_datasets": strict_failures,
                },
                indent=2 if args.pretty else None,
            ),
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
