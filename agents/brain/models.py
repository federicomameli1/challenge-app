"""
Core data models for the Brain orchestrator.

These models are intentionally generic so future stages (Agent 6, Agent 7, etc.)
can be added without changing orchestration fundamentals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(microsecond=0).isoformat()


def _duration_ms(
    started_at: Optional[datetime], ended_at: Optional[datetime]
) -> Optional[int]:
    if started_at is None or ended_at is None:
        return None
    return int((ended_at - started_at).total_seconds() * 1000)


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class DependencyPolicy(str, Enum):
    """
    Policy used to decide if a stage can execute based on dependency outcomes.
    """

    REQUIRE_SUCCESS = "require_success"
    REQUIRE_GO = "require_go"
    ALLOW_ANY = "allow_any"


@dataclass(frozen=True)
class StageDependency:
    """
    Declarative dependency edge for a stage.
    """

    stage_name: str
    required: bool = True
    policy: DependencyPolicy = DependencyPolicy.REQUIRE_SUCCESS


@dataclass(frozen=True)
class StageSpec:
    """
    Immutable stage blueprint used by the orchestrator plan.
    """

    name: str
    depends_on: Tuple[StageDependency, ...] = field(default_factory=tuple)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HandoffEnvelope:
    """
    Typed handoff from one stage to another.
    """

    source_stage: str
    scenario_id: str
    release_id: Optional[str]
    decision: Optional[str]
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    produced_at_utc: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_stage": self.source_stage,
            "scenario_id": self.scenario_id,
            "release_id": self.release_id,
            "decision": self.decision,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "produced_at_utc": self.produced_at_utc,
        }


@dataclass
class StageExecutionResult:
    """
    Runtime result for one stage execution.
    """

    stage_name: str
    status: StageStatus
    scenario_id: str
    release_id: Optional[str] = None
    decision: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    skip_reason: Optional[str] = None
    dependency_snapshot: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    @property
    def duration_ms(self) -> Optional[int]:
        return _duration_ms(self.started_at, self.ended_at)

    @property
    def is_success(self) -> bool:
        return self.status == StageStatus.SUCCESS

    @property
    def is_terminal_problem(self) -> bool:
        return self.status in {StageStatus.FAILED}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "status": self.status.value,
            "scenario_id": self.scenario_id,
            "release_id": self.release_id,
            "decision": self.decision,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "error": self.error,
            "skip_reason": self.skip_reason,
            "dependency_snapshot": dict(self.dependency_snapshot),
            "started_at_utc": _to_iso(self.started_at),
            "ended_at_utc": _to_iso(self.ended_at),
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class BrainRunRequest:
    """
    Input contract for a single Brain orchestrator run.
    """

    scenario_id: str
    release_id: Optional[str] = None
    stage_inputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrainRunReport:
    """
    Full run report emitted by the Brain orchestrator.
    """

    run_id: str
    scenario_id: str
    release_id: Optional[str]
    stage_order: Tuple[str, ...]
    stages: Dict[str, StageExecutionResult] = field(default_factory=dict)
    handoffs: Dict[str, HandoffEnvelope] = field(default_factory=dict)
    status: RunStatus = RunStatus.SUCCESS
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None

    @property
    def duration_ms(self) -> Optional[int]:
        return _duration_ms(self.started_at, self.ended_at)

    def add_stage_result(self, result: StageExecutionResult) -> None:
        self.stages[result.stage_name] = result

    def add_handoff(self, handoff: HandoffEnvelope) -> None:
        self.handoffs[handoff.source_stage] = handoff

    def stage_result(self, stage_name: str) -> Optional[StageExecutionResult]:
        return self.stages.get(stage_name)

    def set_finished(self) -> None:
        self.ended_at = datetime.now(timezone.utc)

    def finalize_status(self) -> RunStatus:
        if any(r.status == StageStatus.FAILED for r in self.stages.values()):
            self.status = RunStatus.FAILED
        elif any(r.status == StageStatus.SKIPPED for r in self.stages.values()):
            self.status = RunStatus.PARTIAL
        else:
            self.status = RunStatus.SUCCESS
        return self.status

    def summary(self) -> Dict[str, Any]:
        counts = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "running": 0,
            "pending": 0,
        }
        for r in self.stages.values():
            counts[r.status.value] = counts.get(r.status.value, 0) + 1

        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "release_id": self.release_id,
            "status": self.status.value,
            "stage_counts": counts,
            "duration_ms": self.duration_ms,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "release_id": self.release_id,
            "status": self.status.value,
            "stage_order": list(self.stage_order),
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "handoffs": {k: v.to_dict() for k, v in self.handoffs.items()},
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
            "started_at_utc": _to_iso(self.started_at),
            "ended_at_utc": _to_iso(self.ended_at),
            "duration_ms": self.duration_ms,
            "summary": self.summary(),
        }
