"""
Agent 7 LangChain-only orchestrator wrapper.

This module provides a clean facade over the LangChain pipeline implementation
for Phase 7 production deployment & live monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .lc_pipeline import Agent7LCError, LCPipelineConfig, LangChainAgent7Pipeline
from .models import validate_output_schema


@dataclass(frozen=True)
class Agent7Config:
    dataset_root: str = "synthetic_data/phase7/v1"
    policy_version: str = "phase7-policy-v1"
    dry_run: bool = True
    strict_schema: bool = True
    stabilization_seconds: float = 60.0
    health_check_interval_seconds: float = 15.0


class Agent7Orchestrator:
    """
    LangChain-only orchestrator for Agent 7.

    Supports:
    - Brain mode: from A6 handoff payload
    - Standalone mode: from file-based dataset
    - Assess all scenarios for batch evaluation
    """

    def __init__(
        self,
        config: Optional[Agent7Config] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.config = config or Agent7Config()
        self.llm_generate = llm_generate

        lc_config = LCPipelineConfig(
            dataset_root=self.config.dataset_root,
            policy_version=self.config.policy_version,
            dry_run=self.config.dry_run,
            strict_schema=self.config.strict_schema,
            stabilization_seconds=self.config.stabilization_seconds,
            health_check_interval_seconds=self.config.health_check_interval_seconds,
        )
        self.pipeline = LangChainAgent7Pipeline(config=lc_config)

    def validate_dataset(self) -> Dict[str, Any]:
        return self.pipeline.validate_dataset()

    def list_scenarios(self) -> Sequence[Dict[str, str]]:
        return self.pipeline.list_scenarios()

    def assess_from_handoffs(
        self,
        scenario_id: str,
        agent6_handoff: Optional[Mapping[str, Any]],
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.pipeline.assess_from_handoffs(
            scenario_id=scenario_id,
            agent6_handoff=agent6_handoff,
            release_id=release_id,
        )

    def assess_scenario(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.pipeline.assess_scenario(
            scenario_id=scenario_id,
            release_id=release_id,
        )

    def assess_all_scenarios(self) -> Sequence[Dict[str, Any]]:
        return self.pipeline.assess_all_scenarios()

    def run(
        self,
        *,
        scenario_id: str,
        release_id: Optional[str] = None,
        agent6_handoff: Optional[Mapping[str, Any]] = None,
        check_label: bool = False,
        labels_path: Optional[str] = None,
        strict_schema: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if agent6_handoff is not None:
            payload = self.assess_from_handoffs(
                scenario_id=scenario_id,
                agent6_handoff=agent6_handoff,
                release_id=release_id,
            )
        else:
            payload = self.assess_scenario(
                scenario_id=scenario_id,
                release_id=release_id,
            )

        valid, errors = validate_output_schema(payload)
        payload["schema_validation"] = {"valid": valid, "errors": errors}

        effective_strict = (
            self.config.strict_schema if strict_schema is None else bool(strict_schema)
        )
        if effective_strict and not valid:
            raise Agent7LCError(
                f"Agent 7 schema validation failed for scenario {scenario_id}: {errors}"
            )

        if check_label and labels_path:
            payload["evaluation"] = self._check_label(labels_path, scenario_id, payload)

        return payload

    def _check_label(
        self, labels_path: str, scenario_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        from pathlib import Path
        import csv

        path = Path(labels_path)
        if not path.exists():
            return {"label_check_performed": False, "error": f"Labels not found: {path}"}

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sid = (row.get("scenario_id") or "").strip()
                if sid != scenario_id:
                    continue
                expected = (row.get("expected_decision") or "").strip().upper()
                if expected not in {"GO", "HOLD"}:
                    return {"label_check_performed": False, "error": f"Invalid label: {expected}"}
                actual = str(payload.get("decision", "")).strip().upper()
                return {
                    "label_check_performed": True,
                    "expected_decision": expected,
                    "actual_decision": actual,
                    "match": actual == expected,
                }

        return {"label_check_performed": False, "error": f"Scenario {scenario_id} not in labels"}


__all__ = [
    "Agent7Config",
    "Agent7Orchestrator",
]
