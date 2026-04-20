"""
Agent 4 stage adapter for Brain orchestration.

This adapter wraps Agent 4's LangChain pipeline and exposes a Brain-compatible
stage interface with deterministic output shape for downstream handoffs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from agent4.lc_pipeline import Agent4LCError, LangChainAgent4Pipeline, LCPipelineConfig

from ..models import StageDependency
from .base import AdapterConfig, BrainStageAdapterBase, StageAdapterError


@dataclass(frozen=True)
class Agent4StageSettings:
    """
    Settings for the Agent 4 stage adapter.
    """

    stage_name: str = "agent4"
    dataset_root: str = "synthetic_data/v1"
    source_adapter_kind: Optional[str] = None
    use_llm_summary: bool = False
    strict_schema: bool = False
    depends_on: Tuple[StageDependency, ...] = field(default_factory=tuple)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class Agent4StageAdapter(BrainStageAdapterBase):
    """
    Brain stage adapter for Agent 4 readiness assessment.
    """

    def __init__(
        self,
        settings: Optional[Agent4StageSettings] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.settings = settings or Agent4StageSettings()
        self.llm_generate = llm_generate

        adapter_metadata = {
            "agent": "agent4",
            "dataset_root": self.settings.dataset_root,
            "source_adapter_kind": self.settings.source_adapter_kind,
            "use_llm_summary": bool(self.settings.use_llm_summary),
        }
        adapter_metadata.update(dict(self.settings.metadata))

        super().__init__(
            AdapterConfig(
                stage_name=self.settings.stage_name,
                depends_on=self.settings.depends_on,
                enabled=self.settings.enabled,
                metadata=adapter_metadata,
            )
        )

        self.pipeline = LangChainAgent4Pipeline(
            config=LCPipelineConfig(
                dataset_root=self.settings.dataset_root,
                source_adapter_kind=self.settings.source_adapter_kind,
                use_llm_summary=self.settings.use_llm_summary,
                strict_schema=self.settings.strict_schema,
            ),
            llm_generate=self.llm_generate,
        )

    def preflight(self, context) -> None:
        scenario_id, _ = self._resolve_inputs(context)
        if not scenario_id:
            raise StageAdapterError(
                "Agent4 stage requires a non-empty scenario_id in context or stage input."
            )

    def _run_stage(self, context) -> Mapping[str, Any]:
        scenario_id, release_id = self._resolve_inputs(context)
        self._validate_dataset()

        try:
            payload = self.pipeline.assess_scenario(
                scenario_id=scenario_id,
                release_id=release_id,
            )
        except Agent4LCError as exc:
            raise StageAdapterError("Agent4 stage execution failed: {0}".format(exc))
        except Exception as exc:  # defensive wrapper
            raise StageAdapterError(
                "Unexpected Agent4 runtime failure: {0}".format(exc)
            )

        decision_raw = payload.get("decision")
        decision = (
            str(decision_raw).strip().upper() if decision_raw is not None else None
        )

        rule_findings = payload.get("rule_findings", {})
        triggered_codes = []
        if isinstance(rule_findings, Mapping):
            codes = rule_findings.get("triggered_rule_codes", [])
            if isinstance(codes, list):
                triggered_codes = [str(x) for x in codes if str(x).strip()]

        metadata = {
            "adapter": self.__class__.__name__,
            "agent": "agent4",
            "dataset_root": self.settings.dataset_root,
            "triggered_rule_codes": triggered_codes,
            "schema_valid": bool(
                payload.get("schema_validation", {}).get("valid", False)
                if isinstance(payload.get("schema_validation"), Mapping)
                else False
            ),
        }

        resolved_release_id = release_id
        if not resolved_release_id:
            rel = payload.get("release_id")
            resolved_release_id = str(rel).strip() if rel is not None else None

        return {
            "status": "success",
            "scenario_id": scenario_id,
            "release_id": resolved_release_id,
            "decision": decision,
            "payload": dict(payload),
            "metadata": metadata,
        }

    def _resolve_inputs(self, context) -> Tuple[str, Optional[str]]:
        stage_input = (
            context.stage_input if isinstance(context.stage_input, Mapping) else {}
        )

        scenario_override = stage_input.get("scenario_id")
        scenario_id = (
            str(scenario_override).strip()
            if scenario_override is not None
            else str(context.scenario_id).strip()
        )

        release_override = stage_input.get("release_id")
        release_id = (
            str(release_override).strip()
            if release_override is not None
            else (
                str(context.release_id).strip()
                if context.release_id is not None
                else None
            )
        )
        if release_id == "":
            release_id = None

        return scenario_id, release_id

    def _validate_dataset(self) -> None:
        report = self.pipeline.validate_dataset()
        if not bool(report.get("exists", False)):
            raise StageAdapterError(
                "Agent4 dataset root does not exist: {0}".format(
                    self.settings.dataset_root
                )
            )
        missing_required = report.get("missing_required", [])
        if isinstance(missing_required, list) and missing_required:
            raise StageAdapterError(
                "Agent4 dataset missing required files: {0}".format(
                    ", ".join([str(x) for x in missing_required])
                )
            )


def build_agent4_stage(
    *,
    dataset_root: str = "synthetic_data/v1",
    source_adapter_kind: Optional[str] = None,
    use_llm_summary: bool = False,
    strict_schema: bool = False,
    stage_name: str = "agent4",
    depends_on: Tuple[StageDependency, ...] = (),
    enabled: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    llm_generate: Optional[Callable[[str], str]] = None,
) -> Agent4StageAdapter:
    """
    Convenience factory for Agent 4 stage adapter.
    """
    settings = Agent4StageSettings(
        stage_name=stage_name,
        dataset_root=dataset_root,
        source_adapter_kind=source_adapter_kind,
        use_llm_summary=use_llm_summary,
        strict_schema=strict_schema,
        depends_on=depends_on,
        enabled=enabled,
        metadata=dict(metadata or {}),
    )
    return Agent4StageAdapter(settings=settings, llm_generate=llm_generate)


__all__ = [
    "Agent4StageSettings",
    "Agent4StageAdapter",
    "build_agent4_stage",
]
