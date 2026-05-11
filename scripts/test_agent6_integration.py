#!/usr/bin/env python3
"""
Agent 6 integration smoke test.

Reads phase6_decision_labels.csv for ground truth, reads the agent4_context/
and agent5_context/ JSON files, runs Agent6Orchestrator.assess_from_handoffs()
for each scenario, and reports actual vs. expected decisions.

Usage:
  python scripts/test_agent6_integration.py
  python scripts/test_agent6_integration.py --dataset-root synthetic_data/phase6/v1
  python scripts/test_agent6_integration.py --dataset-root synthetic_data/phase6/v1 --verbose
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on the path.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.agent6.agent import Agent6Config, Agent6Orchestrator
from agents.agent6.models import validate_output_schema


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent 6 integration smoke test.")
    parser.add_argument(
        "--dataset-root",
        default="synthetic_data/phase6/v1",
        help="Path to Phase 6 dataset root.",
    )
    parser.add_argument(
        "--labels",
        default=None,
        help="Path to phase6_decision_labels.csv (defaults to <dataset-root>/phase6_decision_labels.csv).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full output payload for each scenario.",
    )
    return parser.parse_args()


def read_labels(labels_path: Path) -> Dict[str, Dict[str, str]]:
    """Read phase6_decision_labels.csv into a dict keyed by scenario_id."""
    rows: Dict[str, Dict[str, str]] = {}
    with labels_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = (row.get("scenario_id") or "").strip()
            if sid:
                rows[sid] = row
    return rows


def load_handoff(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON handoff file, returning None if it doesn't exist."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def run_scenario(
    orch: Agent6Orchestrator,
    scenario_id: str,
    release_id: str,
    a4_handoff: Optional[Dict[str, Any]],
    a5_handoff: Optional[Dict[str, Any]],
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run Agent 6 assessment and return the payload."""
    try:
        payload = orch.assess_from_handoffs(
            scenario_id=scenario_id,
            agent4_handoff=a4_handoff,
            agent5_handoff=a5_handoff,
            release_id=release_id,
        )
    except Exception as exc:
        return {
            "decision": "ERROR",
            "rule_findings": {},
            "schema_valid": False,
            "error": str(exc),
        }

    valid, errors = validate_output_schema(payload)
    payload["schema_valid"] = valid
    if errors:
        payload["schema_errors"] = errors

    if verbose:
        print(f"\n  --- {scenario_id} output ---")
        print(f"  decision: {payload.get('decision')}")
        print(f"  rule_findings: {payload.get('rule_findings', {})}")
        reasons = payload.get("reasons", [])
        if reasons:
            print(f"  reasons ({len(reasons)}):")
            for r in reasons:
                print(f"    - [{r.get('title', '?')}] {r.get('detail', '')[:80]}")

    return payload


def main() -> None:
    args = parse_args()
    dataset_root = Path(args.dataset_root)

    labels_path = Path(args.labels) if args.labels else (dataset_root / "phase6_decision_labels.csv")
    if not labels_path.exists():
        print(f"ERROR: Labels file not found: {labels_path}", file=sys.stderr)
        sys.exit(1)

    a4_dir = dataset_root / "agent4_context"
    a5_dir = dataset_root / "agent5_context"

    orch = Agent6Orchestrator(
        config=Agent6Config(
            dataset_root=str(dataset_root),
            use_llm_summary=False,
            strict_schema=False,
        )
    )

    labels = read_labels(labels_path)

    print(f"Agent 6 Integration Smoke Test")
    print(f"=" * 60)
    print(f"Dataset root : {dataset_root}")
    print(f"Labels file  : {labels_path}")
    print(f"Scenarios    : {len(labels)}")
    print()

    results: List[Dict[str, Any]] = []
    passed = failed = 0

    for scenario_id in sorted(labels.keys()):
        row = labels[scenario_id]
        release_id = (row.get("release_id") or scenario_id).strip()
        expected = (row.get("expected_decision") or "").strip().upper()

        a4_path = a4_dir / f"{scenario_id}.json"
        a5_path = a5_dir / f"{scenario_id}.json"

        a4_handoff = load_handoff(a4_path)
        a5_handoff = load_handoff(a5_path)

        if a4_handoff is None:
            print(f"WARNING: agent4_context/{scenario_id}.json not found — skipping")
            continue

        payload = run_scenario(
            orch=orch,
            scenario_id=scenario_id,
            release_id=release_id,
            a4_handoff=a4_handoff,
            a5_handoff=a5_handoff,
            verbose=args.verbose,
        )

        actual = (payload.get("decision") or "").strip().upper()
        triggered = payload.get("rule_findings", {}).get("triggered_rule_codes", [])
        triggered_str = ", ".join(triggered) if triggered else "none"

        match = actual == expected
        status = "PASS" if match else "FAIL"

        if match:
            passed += 1
        else:
            failed += 1

        expected_reason = (row.get("scenario_type") or "").strip()
        print(
            f"[{status}] {scenario_id:8s}  expected={expected:4s}  actual={actual:4s}  "
            f"triggered={triggered_str}  ({expected_reason})"
        )

        results.append({
            "scenario_id": scenario_id,
            "expected": expected,
            "actual": actual,
            "match": match,
            "triggered": triggered,
        })

    print()
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

    if failed > 0:
        print("\nFailures:")
        for r in results:
            if not r["match"]:
                print(f"  {r['scenario_id']}: expected {r['expected']}, got {r['actual']}")
                print(f"    triggered: {r['triggered']}")
        sys.exit(1)

    print("\nAll scenarios matched expected decisions.")
    sys.exit(0)


if __name__ == "__main__":
    main()