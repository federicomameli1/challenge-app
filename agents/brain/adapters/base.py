"""
Base adapter abstraction for Brain stage wrappers.

Adapters in `brain/adapters/` wrap concrete agents/tools and expose them as
Brain-compatible stages.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ..models import (
    StageDependency,
    StageExecutionResult,
    StageSpec,
    StageStatus,
)
from ..stages import BrainStage, BrainStageError, StageExecutionContext


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StageAdapterError(BrainStageError):
    """Raised when a stage adapter fails to execute or validate."""


@dataclass(frozen=True)
class AdapterConfig:
    """
    Shared adapter configuration for Brain stage wrappers.
    """

    stage_name: str
    depends_on: Tuple[StageDependency, ...] = ()
    enabled: bool = True
    metadata: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.stage_name or not self.stage_name.strip():
            raise StageAdapterError("stage_name cannot be empty.")
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


class BrainStageAdapterBase(BrainStage):
    """
    Base class for adapter-backed Brain stages.

    Subclasses implement `_run_stage` and optionally `preflight`.
    """

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config
        self._spec = StageSpec(
            name=config.stage_name,
            depends_on=config.depends_on,
            enabled=config.enabled,
            metadata=dict(config.metadata),
        )

    @property
    def spec(self) -> StageSpec:
        return self._spec

    def run(self, context: StageExecutionContext) -> StageExecutionResult:
        started_at = _utc_now()
        try:
            self.preflight(context)
            raw = self._run_stage(context)
            result = self._normalize_result(
                context=context, raw=raw, started_at=started_at
            )
        except Exception as exc:
            result = StageExecutionResult(
                stage_name=self.name,
                status=StageStatus.FAILED,
                scenario_id=context.scenario_id,
                release_id=context.release_id,
                error=str(exc),
                started_at=started_at,
                ended_at=_utc_now(),
                metadata={"adapter": self.__class__.__name__},
            )
        return result

    @abstractmethod
    def _run_stage(
        self, context: StageExecutionContext
    ) -> StageExecutionResult | Mapping[str, Any]:
        """
        Execute concrete stage logic.

        Return either:
        - `StageExecutionResult`, or
        - mapping with optional keys:
          `status`, `decision`, `payload`, `metadata`, `error`, `skip_reason`,
          `scenario_id`, `release_id`.
        """

    def require_handoff(
        self, context: StageExecutionContext, source_stage: str
    ) -> Dict[str, Any]:
        """
        Return required upstream handoff payload or raise an adapter error.
        """
        handoff = context.handoff(source_stage)
        if handoff is None:
            raise StageAdapterError(
                f"Required handoff from stage '{source_stage}' is missing for '{self.name}'."
            )
        return dict(handoff.payload)

    def _normalize_result(
        self,
        *,
        context: StageExecutionContext,
        raw: StageExecutionResult | Mapping[str, Any],
        started_at: datetime,
    ) -> StageExecutionResult:
        if isinstance(raw, StageExecutionResult):
            # Ensure canonical stage name and default timestamps.
            return StageExecutionResult(
                stage_name=self.name,
                status=raw.status,
                scenario_id=raw.scenario_id or context.scenario_id,
                release_id=raw.release_id or context.release_id,
                decision=raw.decision,
                payload=dict(raw.payload),
                metadata=dict(raw.metadata),
                error=raw.error,
                skip_reason=raw.skip_reason,
                dependency_snapshot=dict(raw.dependency_snapshot),
                started_at=raw.started_at or started_at,
                ended_at=raw.ended_at or _utc_now(),
            )

        data = dict(raw)
        status_raw = str(data.get("status", StageStatus.SUCCESS.value)).strip().lower()
        try:
            status = StageStatus(status_raw)
        except Exception:
            status = StageStatus.SUCCESS

        decision_raw = data.get("decision")
        decision = (
            str(decision_raw).strip().upper() if decision_raw is not None else None
        )

        payload = data.get("payload")
        if isinstance(payload, Mapping):
            payload_out = dict(payload)
        else:
            payload_out = {}

        metadata = data.get("metadata")
        if isinstance(metadata, Mapping):
            metadata_out = dict(metadata)
        else:
            metadata_out = {}

        scenario_id = str(data.get("scenario_id", context.scenario_id)).strip()
        release_id_val = data.get("release_id", context.release_id)
        release_id = str(release_id_val).strip() if release_id_val is not None else None

        return StageExecutionResult(
            stage_name=self.name,
            status=status,
            scenario_id=scenario_id or context.scenario_id,
            release_id=release_id,
            decision=decision,
            payload=payload_out,
            metadata=metadata_out,
            error=(str(data["error"]) if data.get("error") is not None else None),
            skip_reason=(
                str(data["skip_reason"])
                if data.get("skip_reason") is not None
                else None
            ),
            started_at=started_at,
            ended_at=_utc_now(),
        )
