#!/usr/bin/env python3
"""
CLI compatibility wrapper to run Agent 5 (LangChain-first implementation).

This script intentionally mirrors the ergonomic behavior of `run_agent4.py`,
while delegating execution to the Agent 5 LangChain orchestrator.

Usage examples:
  python scripts/run_agent5.py --scenario-id P5-001
  python scripts/run_agent5.py --scenario-id P5-008 --dataset-root synthetic_data/phase5/v1 --check-label
  python scripts/run_agent5.py --scenario-id P5-010 --output evaluations/P5-010_output.json --pretty
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure project root is importable when script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent5.agent import Agent5Config, Agent5LangChainOrchestrator
from agent5.ingestion import IngestionError
from agent5.lc_pipeline import Agent5LCError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Agent 5 Phase 5 test-analysis assessment for one scenario."
    )
    parser.add_argument(
        "--scenario-id",
        required=True,
        help="Scenario identifier, e.g. P5-001",
    )
    parser.add_argument(
        "--dataset-root",
        default="synthetic_data/phase5/v1",
        help="Dataset root directory (default: synthetic_data/phase5/v1)",
    )
    parser.add_argument(
        "--release-id",
        default=None,
        help="Optional release_id consistency filter",
    )
    parser.add_argument(
        "--check-label",
        action="store_true",
        help="Compare output decision against phase5_decision_labels.csv",
    )
    parser.add_argument(
        "--labels-path",
        default=None,
        help=(
            "Optional custom labels CSV path "
            "(default: <dataset-root>/phase5_decision_labels.csv)"
        ),
    )
    parser.add_argument(
        "--fail-on-label-mismatch",
        action="store_true",
        help=(
            "Exit non-zero if --check-label is enabled and decision mismatches "
            "expected label"
        ),
    )
    parser.add_argument(
        "--strict-schema",
        action="store_true",
        help="Exit non-zero if output does not match Agent 5 output schema",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable optional LLM summary layer (deterministic summary only)",
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


def _build_orchestrator(args: argparse.Namespace) -> Agent5LangChainOrchestrator:
    config = Agent5Config(
        dataset_root=args.dataset_root,
        policy_version="phase5-policy-v1",
        use_llm_summary=not args.no_llm,
        strict_schema=False,  # CLI enforces strict behavior via --strict-schema.
        evidence_limit_per_reason=5,
        total_evidence_limit=20,
    )
    return Agent5LangChainOrchestrator(config=config, llm_generate=None)


def run_agent5(args: argparse.Namespace) -> Dict[str, Any]:
    orchestrator = _build_orchestrator(args)

    dataset_report = orchestrator.validate_dataset()
    if not dataset_report.get("exists", False):
        raise RuntimeError(
            f"Dataset root does not exist: {args.dataset_root}. "
            f"Generate a Phase 5 dataset first."
        )

    missing_required = dataset_report.get("missing_required", [])
    if missing_required:
        raise RuntimeError(
            "Dataset missing required files: {0}".format(", ".join(missing_required))
        )

    payload = orchestrator.run(
        scenario_id=args.scenario_id,
        release_id=args.release_id,
        check_label=args.check_label,
        labels_path=args.labels_path,
        strict_schema=False,  # Enforced after output so payload is still visible.
    )

    return payload


def main() -> None:
    args = parse_args()

    try:
        payload = run_agent5(args)
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
    except Agent5LCError as exc:
        print(
            json.dumps(
                {
                    "error": "agent5_langchain_error",
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
                    "error": "agent5_runtime_error",
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
            json_text + ("\n" if not json_text.endswith("\n") else ""),
            encoding="utf-8",
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
