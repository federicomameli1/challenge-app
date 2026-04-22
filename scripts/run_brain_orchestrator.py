#!/usr/bin/env python3
"""
CLI entrypoint for Brain orchestration (Agent 4 -> Agent 5).

Goals:
- Run a dependency-aware orchestration pipeline.
- Enforce default gating: Agent 5 runs only if Agent 4 decision == GO.
- Allow explicit override to continue Agent 5 even when Agent 4 is HOLD.
- Keep stage wiring future-extensible for upcoming agents.

Examples:
  python scripts/run_brain_orchestrator.py --scenario-id S4-001 --agent5-scenario-id P5-001 --pretty
  python scripts/run_brain_orchestrator.py --scenario-id S4-002 --agent5-scenario-id P5-021 --pretty
  python scripts/run_brain_orchestrator.py --scenario-id S4-002 --agent5-scenario-id P5-021 --allow-agent5-after-agent4-hold --pretty
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Ensure project root is importable when script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from brain import (
    BrainOrchestrator,
    BrainOrchestratorError,
    BrainRunRequest,
    DependencyPolicy,
    StageDependency,
    StageRegistry,
    build_default_stage_order,
)
from brain.adapters import build_agent4_stage, build_agent5_stage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Brain orchestrator for Agent4 -> Agent5 flow."
    )

    # Shared run context
    parser.add_argument(
        "--scenario-id",
        required=True,
        help="Shared scenario ID for the run (stage-specific IDs can override).",
    )
    parser.add_argument(
        "--release-id",
        default=None,
        help="Optional shared release ID (stage-specific release IDs can override).",
    )

    # Stage-specific scenario/release overrides
    parser.add_argument(
        "--agent4-scenario-id",
        default=None,
        help="Optional scenario override for Agent 4 stage.",
    )
    parser.add_argument(
        "--agent5-scenario-id",
        default=None,
        help="Optional scenario override for Agent 5 stage.",
    )
    parser.add_argument(
        "--agent4-release-id",
        default=None,
        help="Optional release override for Agent 4 stage.",
    )
    parser.add_argument(
        "--agent5-release-id",
        default=None,
        help="Optional release override for Agent 5 stage.",
    )

    # Dataset roots
    parser.add_argument(
        "--agent4-dataset-root",
        default="synthetic_data/v1",
        help="Agent 4 dataset root (default: synthetic_data/v1).",
    )
    parser.add_argument(
        "--agent5-dataset-root",
        default="synthetic_data/phase5/v1",
        help="Agent 5 dataset root (default: synthetic_data/phase5/v1).",
    )

    # Agent 4 adapter options
    parser.add_argument(
        "--agent4-source-adapter-kind",
        default=None,
        help="Optional Agent 4 source adapter kind (e.g. structured_dataset).",
    )
    parser.add_argument(
        "--agent4-use-llm-summary",
        action="store_true",
        help="Enable optional LLM summary layer for Agent 4.",
    )
    parser.add_argument(
        "--agent4-strict-schema",
        action="store_true",
        help="Enable strict schema enforcement in Agent 4 pipeline.",
    )

    # Agent 5 adapter options
    parser.add_argument(
        "--agent5-use-llm-summary",
        action="store_true",
        help="Enable optional LLM summary layer for Agent 5.",
    )
    parser.add_argument(
        "--agent5-strict-schema",
        action="store_true",
        help="Enable strict schema enforcement in Agent 5 pipeline.",
    )

    # Gating override
    parser.add_argument(
        "--allow-agent5-after-agent4-hold",
        action="store_true",
        help="Override default gating and allow Agent 5 even when Agent 4 decision is HOLD.",
    )

    # Output controls
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write JSON report.",
    )

    return parser.parse_args()


def _build_registry(args: argparse.Namespace) -> Tuple[StageRegistry, Tuple[str, ...]]:
    registry = StageRegistry()

    agent4_stage = build_agent4_stage(
        dataset_root=str(args.agent4_dataset_root),
        source_adapter_kind=(
            str(args.agent4_source_adapter_kind).strip()
            if args.agent4_source_adapter_kind is not None
            else None
        ),
        use_llm_summary=bool(args.agent4_use_llm_summary),
        strict_schema=bool(args.agent4_strict_schema),
        stage_name="agent4",
        depends_on=(),
        enabled=True,
        metadata={"managed_by": "brain_orchestrator"},
    )

    agent5_stage = build_agent5_stage(
        dataset_root=str(args.agent5_dataset_root),
        use_llm_summary=bool(args.agent5_use_llm_summary),
        strict_schema=bool(args.agent5_strict_schema),
        stage_name="agent5",
        depends_on=(
            StageDependency(
                stage_name="agent4",
                required=True,
                policy=DependencyPolicy.REQUIRE_GO,
            ),
        ),
        enabled=True,
        metadata={"managed_by": "brain_orchestrator"},
        require_agent4_handoff=True,
        expected_agent4_stage_name="agent4",
    )

    registry.register(agent4_stage)
    registry.register(agent5_stage)

    stage_order = build_default_stage_order()
    return registry, stage_order


def _stage_inputs_from_args(args: argparse.Namespace) -> Dict[str, Dict[str, Any]]:
    stage_inputs: Dict[str, Dict[str, Any]] = {
        "agent4": {},
        "agent5": {},
    }

    if args.agent4_scenario_id:
        stage_inputs["agent4"]["scenario_id"] = str(args.agent4_scenario_id).strip()
    if args.agent5_scenario_id:
        stage_inputs["agent5"]["scenario_id"] = str(args.agent5_scenario_id).strip()

    if args.agent4_release_id is not None:
        value = str(args.agent4_release_id).strip()
        stage_inputs["agent4"]["release_id"] = value if value else None
    if args.agent5_release_id is not None:
        value = str(args.agent5_release_id).strip()
        stage_inputs["agent5"]["release_id"] = value if value else None

    # Keep explicit handoff requirement as part of stage input contract.
    stage_inputs["agent5"]["require_agent4_handoff"] = True

    return stage_inputs


def _options_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "allow_agent5_after_agent4_hold": bool(args.allow_agent5_after_agent4_hold),
    }


def _build_request(args: argparse.Namespace) -> BrainRunRequest:
    scenario_id = str(args.scenario_id).strip()
    if not scenario_id:
        raise ValueError("--scenario-id cannot be empty.")

    release_id = None
    if args.release_id is not None:
        rid = str(args.release_id).strip()
        release_id = rid if rid else None

    stage_inputs = _stage_inputs_from_args(args)
    options = _options_from_args(args)

    metadata = {
        "runner": "scripts/run_brain_orchestrator.py",
        "agent4_dataset_root": str(args.agent4_dataset_root),
        "agent5_dataset_root": str(args.agent5_dataset_root),
    }

    return BrainRunRequest(
        scenario_id=scenario_id,
        release_id=release_id,
        stage_inputs=stage_inputs,
        options=options,
        metadata=metadata,
    )


def _write_output(path: str, payload: Dict[str, Any], pretty: bool) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2 if pretty else None)
    if not text.endswith("\n"):
        text += "\n"
    out_path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()

    try:
        registry, stage_order = _build_registry(args)
        orchestrator = BrainOrchestrator(registry=registry, stage_order=stage_order)
        request = _build_request(args)
        report = orchestrator.run(request)
        payload = report.to_dict()
    except (BrainOrchestratorError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "error": "brain_orchestrator_configuration_error",
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
                    "error": "brain_orchestrator_runtime_error",
                    "message": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    if args.output:
        _write_output(args.output, payload, args.pretty)

    print(json.dumps(payload, indent=2 if args.pretty else None))

    # Non-zero only for runtime failure status.
    # Partial runs (e.g., policy-based skip of Agent 5) are valid outcomes.
    if payload.get("status") == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
