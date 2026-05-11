"""
Agent 6 LangChain-only orchestrator wrapper.

This module provides a clean facade over the LangChain pipeline implementation
for Phase 6 release-documentation & approvals assessment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from .lc_pipeline import Agent6LCError, LangChainAgent6Pipeline, LCPipelineConfig
from .models import validate_output_schema


@dataclass(frozen=True)
class Agent6Config:
    dataset_root: str = "synthetic_data/phase6/v1"
    policy_version: str = "phase6-policy-v1"
    use_llm_summary: bool = True
    strict_schema: bool = True
    evidence_limit_per_reason: int = 5
    total_evidence_limit: int = 20


class Agent6Orchestrator:
    """
    LangChain-only orchestrator for Agent 6.

    This wrapper delegates execution to `LangChainAgent6Pipeline` and exposes a
    stable API for scripts and application integrations.

    Agent 6 supports two modes:
    - Brain mode: from BrainOrchestrator handoff payloads (agent4_handoff, agent5_handoff)
    - Standalone mode: from file-based dataset
    """

    def __init__(
        self,
        config: Optional[Agent6Config] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.config = config or Agent6Config()
        self.llm_generate = llm_generate

        lc_config = LCPipelineConfig(
            dataset_root=self.config.dataset_root,
            policy_version=self.config.policy_version,
            use_llm_summary=self.config.use_llm_summary,
            strict_schema=self.config.strict_schema,
            evidence_limit_per_reason=self.config.evidence_limit_per_reason,
            total_evidence_limit=self.config.total_evidence_limit,
        )
        self.pipeline = LangChainAgent6Pipeline(
            config=lc_config,
            llm_generate=self.llm_generate,
        )

    def validate_dataset(self) -> Dict[str, Any]:
        return self.pipeline.validate_dataset()

    def list_scenarios(self) -> Sequence[Dict[str, str]]:
        return self.pipeline.list_scenarios()

    def assess_from_handoffs(
        self,
        scenario_id: str,
        agent4_handoff: Optional[Mapping[str, Any]],
        agent5_handoff: Optional[Mapping[str, Any]],
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Primary BrainOrchestrator entry point.
        Assess Phase 6 readiness from Agent 4 and Agent 5 handoff payloads.
        """
        return self.pipeline.assess_from_handoffs(
            scenario_id=scenario_id,
            agent4_handoff=agent4_handoff,
            agent5_handoff=agent5_handoff,
            release_id=release_id,
        )

    def assess_scenario(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Standalone mode: assess Phase 6 from file-based dataset.
        """
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
        agent4_handoff: Optional[Mapping[str, Any]] = None,
        agent5_handoff: Optional[Mapping[str, Any]] = None,
        check_label: bool = False,
        labels_path: Optional[str] = None,
        strict_schema: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Convenience one-shot execution helper.

        Chooses Brain mode (handoffs provided) or standalone mode automatically.
        """
        if agent4_handoff is not None or agent5_handoff is not None:
            payload = self.assess_from_handoffs(
                scenario_id=scenario_id,
                agent4_handoff=agent4_handoff,
                agent5_handoff=agent5_handoff,
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
            raise Agent6LCError(
                f"Agent 6 schema validation failed for scenario {scenario_id}: {errors}"
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

    @staticmethod
    def schema_valid(payload: Dict[str, Any]) -> bool:
        return bool(payload.get("schema_validation", {}).get("valid", False))


__all__ = [
    "Agent6Config",
    "Agent6Orchestrator",
]
