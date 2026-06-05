"""
Agent 7 — Production Deployment Gate with Live Monitoring.

Phase 7: Validates production deployment readiness and executes the release
with continuous health monitoring during the stabilization window.

Modules:
- models: Core enums, dataclasses, and schema validation
- normalization: Raw artifact to policy-bundle conversion
- ingestion: Phase 7 artifact ingestion (deployment manifest, health checks, etc.)
- policy: 6-rule deterministic policy engine
- deployment: Deployment executor with live monitoring
- lc_pipeline: LangChain pipeline orchestration
- agent: Agent7Orchestrator facade
"""

from __future__ import annotations

from .agent import Agent7Config, Agent7Orchestrator
from .lc_pipeline import Agent7LCError, LCPipelineConfig, LangChainAgent7Pipeline
from .models import (
    Decision,
    DecisionType,
    Confidence,
    RuleCode,
    RuleFindings,
    RuleFinding,
    DeploymentStatus,
    HealthProbeStatus,
    MonitoringSnapshot,
    MonitoringState,
    DeploymentRecord,
    SourceRef,
    ReasonItem,
    Agent7Output,
    validate_output_schema,
)
from .normalization import normalize_phase7_bundle
from .policy import Phase7PolicyEngine, PolicyConfig

__all__ = [
    # Agent orchestrator
    "Agent7Config",
    "Agent7Orchestrator",
    # Pipeline
    "Agent7LCError",
    "LCPipelineConfig",
    "LangChainAgent7Pipeline",
    # Models
    "Decision",
    "DecisionType",
    "Confidence",
    "RuleCode",
    "RuleFindings",
    "RuleFinding",
    "DeploymentStatus",
    "HealthProbeStatus",
    "MonitoringSnapshot",
    "MonitoringState",
    "DeploymentRecord",
    "SourceRef",
    "ReasonItem",
    "Agent7Output",
    "validate_output_schema",
    # Normalization
    "normalize_phase7_bundle",
    # Policy
    "Phase7PolicyEngine",
    "PolicyConfig",
]
