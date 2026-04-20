"""
Brain orchestration package exports.

This package provides a dependency-aware, future-extensible orchestration layer
that can coordinate Agent 4 -> Agent 5 now and support additional stages
(Agent 6, Agent 7, ...) with minimal alignment changes.
"""

from .adapters import (
    AdapterConfig,
    Agent4StageAdapter,
    Agent4StageSettings,
    Agent5StageAdapter,
    Agent5StageSettings,
    BrainStageAdapterBase,
    StageAdapterError,
    build_agent4_stage,
    build_agent5_stage,
)
from .models import (
    BrainRunReport,
    BrainRunRequest,
    DependencyPolicy,
    HandoffEnvelope,
    RunStatus,
    StageDependency,
    StageExecutionResult,
    StageSpec,
    StageStatus,
    utc_now_iso,
)
from .orchestrator import (
    BrainOrchestrator,
    BrainOrchestratorError,
    build_default_stage_order,
)
from .stages import (
    BrainStage,
    BrainStageError,
    StageExecutionContext,
    StageRegistry,
)

__all__ = [
    # models
    "utc_now_iso",
    "StageStatus",
    "RunStatus",
    "DependencyPolicy",
    "StageDependency",
    "StageSpec",
    "HandoffEnvelope",
    "StageExecutionResult",
    "BrainRunRequest",
    "BrainRunReport",
    # stage interfaces
    "BrainStageError",
    "BrainStage",
    "StageExecutionContext",
    "StageRegistry",
    # orchestrator
    "BrainOrchestratorError",
    "BrainOrchestrator",
    "build_default_stage_order",
    # adapters
    "AdapterConfig",
    "BrainStageAdapterBase",
    "StageAdapterError",
    "Agent4StageSettings",
    "Agent4StageAdapter",
    "build_agent4_stage",
    "Agent5StageSettings",
    "Agent5StageAdapter",
    "build_agent5_stage",
]
