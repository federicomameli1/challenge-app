"""
Agent 5 LangChain-only orchestrator wrapper.

This module provides a clean façade over the LangChain pipeline implementation
for Phase 5 test-analysis assessment.

Design principles:
- LangChain-first orchestration only (no parallel non-LangChain runner path)
- Deterministic policy outcomes remain authoritative
- Optional label checking and strict schema enforcement for CLI integrations
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from .lc_pipeline import Agent5LCError, LangChainAgent5Pipeline, LCPipelineConfig
from .models import validate_output_schema


@dataclass(frozen=True)
class Agent5Config:
    """
    High-level Agent 5 orchestration configuration.
    """

    dataset_root: str = "synthetic_data/phase5/v1"
    policy_version: str = "phase5-policy-v1"
    use_llm_summary: bool = True
    strict_schema: bool = True
    evidence_limit_per_reason: int = 5
    total_evidence_limit: int = 20


class Agent5LangChainOrchestrator:
    """
    LangChain-only orchestrator for Agent 5.

    This wrapper delegates execution to `LangChainAgent5Pipeline` and exposes a
    stable API for scripts and application integrations.
    """

    def __init__(
        self,
        config: Optional[Agent5Config] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.config = config or Agent5Config()
        self.llm_generate = llm_generate

        lc_config = LCPipelineConfig(
            dataset_root=self.config.dataset_root,
            policy_version=self.config.policy_version,
            use_llm_summary=self.config.use_llm_summary,
            strict_schema=self.config.strict_schema,
            evidence_limit_per_reason=self.config.evidence_limit_per_reason,
            total_evidence_limit=self.config.total_evidence_limit,
        )
        self.pipeline = LangChainAgent5Pipeline(
            config=lc_config,
            llm_generate=self.llm_generate,
        )

    # ---------------------------------------------------------------------
    # Dataset / discovery APIs
    # ---------------------------------------------------------------------

    def validate_dataset(self) -> Dict[str, Any]:
        return self.pipeline.validate_dataset()

    def list_scenarios(self) -> Sequence[Dict[str, str]]:
        return self.pipeline.list_scenarios()

    # ---------------------------------------------------------------------
    # Assessment APIs
    # ---------------------------------------------------------------------

    def assess_scenario(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run Agent 5 for one scenario and return output payload.
        """
        payload = self.pipeline.assess_scenario(
            scenario_id=scenario_id,
            release_id=release_id,
        )
        return payload

    def assess_all_scenarios(self) -> Sequence[Dict[str, Any]]:
        """
        Run Agent 5 for all scenarios available in dataset release calendar.
        """
        return self.pipeline.assess_all_scenarios()

    def evaluate_against_labels(
        self,
        predictions: Optional[Sequence[Dict[str, Any]]] = None,
        labels_csv_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate predictions against phase5_decision_labels.csv.
        """
        return self.pipeline.evaluate_against_labels(
            predictions=predictions,
            labels_csv_path=labels_csv_path,
        )

    # ---------------------------------------------------------------------
    # Optional orchestration helpers
    # ---------------------------------------------------------------------

    def run(
        self,
        *,
        scenario_id: str,
        release_id: Optional[str] = None,
        check_label: bool = False,
        labels_path: Optional[str] = None,
        strict_schema: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Convenience one-shot execution helper.

        Adds:
        - schema validation snapshot
        - optional expected-label comparison
        """
        payload = self.assess_scenario(scenario_id=scenario_id, release_id=release_id)

        valid, errors = validate_output_schema(payload)
        payload["schema_validation"] = {"valid": valid, "errors": errors}

        effective_strict = (
            self.config.strict_schema if strict_schema is None else bool(strict_schema)
        )
        if effective_strict and not valid:
            raise Agent5LCError(
                f"Agent 5 schema validation failed for scenario {scenario_id}: {errors}"
            )

        if check_label:
            expected, err = self._load_expected_label(
                labels_path=labels_path,
                scenario_id=scenario_id,
            )
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

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def _load_expected_label(
        self,
        *,
        labels_path: Optional[str],
        scenario_id: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        path = (
            Path(labels_path)
            if labels_path
            else Path(self.config.dataset_root) / "phase5_decision_labels.csv"
        )
        if not path.exists():
            return None, f"Labels file not found: {path}"

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sid = (row.get("scenario_id") or "").strip()
                if sid != scenario_id:
                    continue

                expected = (row.get("expected_decision") or "").strip().upper()
                if expected not in {"GO", "HOLD"}:
                    return (
                        None,
                        f"Invalid expected_decision for {scenario_id}: {expected!r}",
                    )
                return expected, None

        return None, f"Scenario {scenario_id} not found in labels file."

    @staticmethod
    def schema_valid(payload: Dict[str, Any]) -> bool:
        """
        Small utility used by scripts/tests.
        """
        return bool(payload.get("schema_validation", {}).get("valid", False))


__all__ = [
    "Agent5Config",
    "Agent5LangChainOrchestrator",
]
