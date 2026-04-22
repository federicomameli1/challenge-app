"""
Agent 5 stage adapter for Brain orchestration.

This adapter wraps Agent 5's LangChain pipeline and exposes a Brain-compatible
stage interface while remaining explicitly aware of Agent 4 handoff data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from agent5.lc_pipeline import Agent5LCError, LangChainAgent5Pipeline, LCPipelineConfig

from ..models import StageDependency
from .base import AdapterConfig, BrainStageAdapterBase, StageAdapterError


@dataclass(frozen=True)
class Agent5StageSettings:
    """
    Settings for the Agent 5 stage adapter.
    """

    stage_name: str = "agent5"
    dataset_root: str = "synthetic_data/phase5/v1"
    use_llm_summary: bool = False
    strict_schema: bool = False
    depends_on: Tuple[StageDependency, ...] = field(default_factory=tuple)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Handoff behavior
    require_agent4_handoff: bool = True
    expected_agent4_stage_name: str = "agent4"


class Agent5StageAdapter(BrainStageAdapterBase):
    """
    Brain stage adapter for Agent 5 test-analysis assessment.

    Handoff awareness:
    - Validates Agent 4 handoff presence/shape when required.
    - Captures Agent 4 decision and continuity-related metadata for auditability.
    - Executes Agent 5 assessment using its native pipeline API.
    """

    def __init__(
        self,
        settings: Optional[Agent5StageSettings] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.settings = settings or Agent5StageSettings()
        self.llm_generate = llm_generate

        adapter_metadata = {
            "agent": "agent5",
            "dataset_root": self.settings.dataset_root,
            "use_llm_summary": bool(self.settings.use_llm_summary),
            "require_agent4_handoff": bool(self.settings.require_agent4_handoff),
            "expected_agent4_stage_name": self.settings.expected_agent4_stage_name,
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

        self.pipeline = LangChainAgent5Pipeline(
            config=LCPipelineConfig(
                dataset_root=self.settings.dataset_root,
                use_llm_summary=self.settings.use_llm_summary,
                strict_schema=self.settings.strict_schema,
            ),
            llm_generate=self.llm_generate,
        )

    def preflight(self, context) -> None:
        scenario_id, _ = self._resolve_inputs(context)
        if not scenario_id:
            raise StageAdapterError(
                "Agent5 stage requires a non-empty scenario_id in context or stage input."
            )

        self._validate_dataset()
        self._validate_agent4_handoff_if_required(context)

    def _run_stage(self, context) -> Mapping[str, Any]:
        scenario_id, release_id = self._resolve_inputs(context)
        handoff_summary = self._extract_agent4_handoff_summary(context)

        try:
            payload = self.pipeline.assess_scenario(
                scenario_id=scenario_id,
                release_id=release_id,
            )
        except Agent5LCError as exc:
            raise StageAdapterError("Agent5 stage execution failed: {0}".format(exc))
        except Exception as exc:  # defensive wrapper
            raise StageAdapterError(
                "Unexpected Agent5 runtime failure: {0}".format(exc)
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
            "agent": "agent5",
            "dataset_root": self.settings.dataset_root,
            "triggered_rule_codes": triggered_codes,
            "schema_valid": bool(
                payload.get("schema_validation", {}).get("valid", False)
                if isinstance(payload.get("schema_validation"), Mapping)
                else False
            ),
            "agent4_handoff": handoff_summary,
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
                "Agent5 dataset root does not exist: {0}".format(
                    self.settings.dataset_root
                )
            )
        missing_required = report.get("missing_required", [])
        if isinstance(missing_required, list) and missing_required:
            raise StageAdapterError(
                "Agent5 dataset missing required files: {0}".format(
                    ", ".join([str(x) for x in missing_required])
                )
            )

    def _validate_agent4_handoff_if_required(self, context) -> None:
        stage_input = (
            context.stage_input if isinstance(context.stage_input, Mapping) else {}
        )
        options = context.options if isinstance(context.options, Mapping) else {}

        required = bool(self.settings.require_agent4_handoff)
        if "require_agent4_handoff" in stage_input:
            required = bool(stage_input.get("require_agent4_handoff"))
        elif "require_agent4_handoff" in options:
            required = bool(options.get("require_agent4_handoff"))

        if not required:
            return

        src_stage = self.settings.expected_agent4_stage_name
        handoff = context.handoff(src_stage)
        if handoff is None:
            raise StageAdapterError(
                "Agent5 requires handoff from stage '{0}', but it is missing.".format(
                    src_stage
                )
            )

        if handoff.source_stage != src_stage:
            raise StageAdapterError(
                "Invalid handoff source for Agent5. Expected '{0}', got '{1}'.".format(
                    src_stage, handoff.source_stage
                )
            )

        # Minimal shape validation for awareness and auditability.
        if not isinstance(handoff.payload, Mapping):
            raise StageAdapterError("Agent4 handoff payload must be a mapping.")

    def _extract_agent4_handoff_summary(self, context) -> Dict[str, Any]:
        src_stage = self.settings.expected_agent4_stage_name
        handoff = context.handoff(src_stage)

        if handoff is None:
            return {
                "present": False,
                "source_stage": src_stage,
                "decision": None,
                "triggered_rule_codes": [],
                "notes": ["agent4_handoff_missing"],
            }

        triggered_rule_codes = []
        payload = handoff.payload if isinstance(handoff.payload, Mapping) else {}
        rf = payload.get("rule_findings", {})
        if isinstance(rf, Mapping):
            codes = rf.get("triggered_rule_codes", [])
            if isinstance(codes, list):
                triggered_rule_codes = [str(x) for x in codes if str(x).strip()]

        return {
            "present": True,
            "source_stage": handoff.source_stage,
            "decision": (
                str(handoff.decision).strip().upper()
                if handoff.decision is not None
                else None
            ),
            "scenario_id": handoff.scenario_id,
            "release_id": handoff.release_id,
            "triggered_rule_codes": triggered_rule_codes,
            "produced_at_utc": handoff.produced_at_utc,
        }


def build_agent5_stage(
    *,
    dataset_root: str = "synthetic_data/phase5/v1",
    use_llm_summary: bool = False,
    strict_schema: bool = False,
    stage_name: str = "agent5",
    depends_on: Tuple[StageDependency, ...] = (),
    enabled: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    require_agent4_handoff: bool = True,
    expected_agent4_stage_name: str = "agent4",
    llm_generate: Optional[Callable[[str], str]] = None,
) -> Agent5StageAdapter:
    """
    Convenience factory for Agent 5 stage adapter.
    """
    settings = Agent5StageSettings(
        stage_name=stage_name,
        dataset_root=dataset_root,
        use_llm_summary=use_llm_summary,
        strict_schema=strict_schema,
        depends_on=depends_on,
        enabled=enabled,
        metadata=dict(metadata or {}),
        require_agent4_handoff=require_agent4_handoff,
        expected_agent4_stage_name=expected_agent4_stage_name,
    )
    return Agent5StageAdapter(settings=settings, llm_generate=llm_generate)


__all__ = [
    "Agent5StageSettings",
    "Agent5StageAdapter",
    "build_agent5_stage",
]
