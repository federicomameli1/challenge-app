"""
Abstract stage interfaces and execution context for the Brain pipeline.

This module defines the stage contract used by the orchestrator so current
(Agent 4, Agent 5) and future stages (Agent 6, Agent 7, ...) can be plugged in
without changing orchestration fundamentals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .models import (
    HandoffEnvelope,
    StageDependency,
    StageExecutionResult,
    StageSpec,
    StageStatus,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class BrainStageError(Exception):
    """Base error for stage-level failures."""


@dataclass(frozen=True)
class StageExecutionContext:
    """
    Immutable execution context passed to every stage.

    Attributes:
        run_id: Orchestrator run identifier.
        stage_name: Current stage logical name.
        scenario_id: Scenario being processed.
        release_id: Optional release identifier.
        stage_input: Stage-specific input arguments.
        options: Global run options and feature flags.
        metadata: Global run metadata.
        handoffs: Upstream handoff envelopes keyed by source stage name.
        prior_stage_results: Prior stage execution results keyed by stage name.
    """

    run_id: str
    stage_name: str
    scenario_id: str
    release_id: Optional[str]
    stage_input: Mapping[str, Any] = field(default_factory=dict)
    options: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    handoffs: Mapping[str, HandoffEnvelope] = field(default_factory=dict)
    prior_stage_results: Mapping[str, StageExecutionResult] = field(
        default_factory=dict
    )

    def handoff(self, source_stage: str) -> Optional[HandoffEnvelope]:
        return self.handoffs.get(source_stage)

    def prior_result(self, stage_name: str) -> Optional[StageExecutionResult]:
        return self.prior_stage_results.get(stage_name)


class BrainStage(ABC):
    """
    Abstract stage contract for Brain orchestration.

    Implementations should remain deterministic where possible and return
    `StageExecutionResult` with payload/decision details.
    """

    @property
    @abstractmethod
    def spec(self) -> StageSpec:
        """Immutable stage specification used by orchestrator planning."""

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def depends_on(self) -> Tuple[StageDependency, ...]:
        return self.spec.depends_on

    def preflight(self, context: StageExecutionContext) -> None:
        """
        Optional validation hook before `run`.

        Raise `BrainStageError` if stage input or required handoff shape is invalid.
        """

    @abstractmethod
    def run(self, context: StageExecutionContext) -> StageExecutionResult:
        """
        Execute stage logic and return stage result.

        Implementations should set:
          - status: success/failed
          - decision: optional GO/HOLD-style decision
          - payload: structured output for downstream processing
          - metadata/error as needed
        """

    def build_handoff(
        self,
        context: StageExecutionContext,
        result: StageExecutionResult,
    ) -> Optional[HandoffEnvelope]:
        """
        Create default handoff envelope for downstream stages.

        By default:
          - returns handoff only for successful stages
          - includes full stage payload and metadata
        """
        if result.status != StageStatus.SUCCESS:
            return None

        return HandoffEnvelope(
            source_stage=self.name,
            scenario_id=result.scenario_id or context.scenario_id,
            release_id=result.release_id if result.release_id else context.release_id,
            decision=result.decision,
            payload=dict(result.payload),
            metadata=dict(result.metadata),
        )


class StageRegistry:
    """
    Lightweight registry for stage instances.

    This keeps stage lookup decoupled from orchestrator implementation and enables
    incremental onboarding of future stages.
    """

    def __init__(self) -> None:
        self._stages: Dict[str, BrainStage] = {}

    def register(self, stage: BrainStage) -> None:
        name = stage.name.strip()
        if not name:
            raise BrainStageError("Stage name cannot be empty.")
        if name in self._stages:
            raise BrainStageError(f"Stage already registered: {name}")
        self._stages[name] = stage

    def get(self, stage_name: str) -> BrainStage:
        if stage_name not in self._stages:
            raise BrainStageError(f"Unknown stage: {stage_name}")
        return self._stages[stage_name]

    def has(self, stage_name: str) -> bool:
        return stage_name in self._stages

    def names(self) -> Tuple[str, ...]:
        return tuple(self._stages.keys())

    def all(self) -> Tuple[BrainStage, ...]:
        return tuple(self._stages.values())
