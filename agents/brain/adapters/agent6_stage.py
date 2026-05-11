"""
Agent 6 stage adapter for Brain orchestration.

This adapter wraps Agent 6's pipeline and exposes a Brain-compatible
stage interface while remaining explicitly aware of Agent 4 and Agent 5 handoff data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from agent6.agent import Agent6Config, Agent6Orchestrator
from agent6.models import validate_output_schema

from ..models import StageDependency
from .base import AdapterConfig, BrainStageAdapterBase, StageAdapterError


@dataclass(frozen=True)
class Agent6StageSettings:
    """
    Settings for the Agent 6 stage adapter.
    """

    stage_name: str = "agent6"
    dataset_root: str = "synthetic_data/phase6/v1"
    use_llm_summary: bool = False
    strict_schema: bool = True
    depends_on: Tuple[StageDependency, ...] = field(default_factory=tuple)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Handoff behavior
    require_agent4_handoff: bool = False
    require_agent5_handoff: bool = False
    expected_agent4_stage_name: str = "agent4"
    expected_agent5_stage_name: str = "agent5"


class Agent6StageAdapter(BrainStageAdapterBase):
    """
    Brain stage adapter for Agent 6 VDD drafting and approvals assessment.

    Handoff awareness:
    - Accepts Agent 4 and/or Agent 5 handoff payloads.
    - Uses handoffs to populate the VDD draft via HandoffBundleAdapter.
    - Works in Brain mode (handoffs) or standalone mode (file-based dataset).
    """

    def __init__(
        self,
        settings: Optional[Agent6StageSettings] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.settings = settings or Agent6StageSettings()
        self.llm_generate = llm_generate

        adapter_metadata = {
            "agent": "agent6",
            "dataset_root": self.settings.dataset_root,
            "use_llm_summary": bool(self.settings.use_llm_summary),
            "require_agent4_handoff": bool(self.settings.require_agent4_handoff),
            "require_agent5_handoff": bool(self.settings.require_agent5_handoff),
            "expected_agent4_stage_name": self.settings.expected_agent4_stage_name,
            "expected_agent5_stage_name": self.settings.expected_agent5_stage_name,
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

        config = Agent6Config(
            dataset_root=self.settings.dataset_root,
            use_llm_summary=self.settings.use_llm_summary,
            strict_schema=self.settings.strict_schema,
        )
        self.orchestrator = Agent6Orchestrator(
            config=config,
            llm_generate=self.llm_generate,
        )

    def preflight(self, context) -> None:
        scenario_id, _ = self._resolve_inputs(context)
        if not scenario_id:
            raise StageAdapterError(
                "Agent6 stage requires a non-empty scenario_id in context or stage input."
            )

        # Agent 6 can run without handoffs (standalone mode), but if required,
        # validate that expected handoffs are present.
        if self.settings.require_agent4_handoff or self.settings.require_agent5_handoff:
            self._validate_handoffs_if_required(context)

    def _run_stage(self, context) -> Mapping[str, Any]:
        scenario_id, release_id = self._resolve_inputs(context)
        a4_handoff = self._extract_handoff(context, self.settings.expected_agent4_stage_name)
        a5_handoff = self._extract_handoff(context, self.settings.expected_agent5_stage_name)

        try:
            if a4_handoff is not None or a5_handoff is not None:
                payload = self.orchestrator.assess_from_handoffs(
                    scenario_id=scenario_id,
                    agent4_handoff=a4_handoff,
                    agent5_handoff=a5_handoff,
                    release_id=release_id,
                )
            else:
                payload = self.orchestrator.assess_scenario(
                    scenario_id=scenario_id,
                    release_id=release_id,
                )
        except Exception as exc:
            raise StageAdapterError("Agent6 stage execution failed: {0}".format(exc))

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

        schema_validation = payload.get("schema_validation", {})
        schema_valid = bool(
            schema_validation.get("valid", False) if isinstance(schema_validation, Mapping) else False
        )

        metadata = {
            "adapter": self.__class__.__name__,
            "agent": "agent6",
            "dataset_root": self.settings.dataset_root,
            "triggered_rule_codes": triggered_codes,
            "schema_valid": schema_valid,
            "agent4_handoff_present": a4_handoff is not None,
            "agent5_handoff_present": a5_handoff is not None,
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

    def _validate_handoffs_if_required(self, context) -> None:
        stage_input = (
            context.stage_input if isinstance(context.stage_input, Mapping) else {}
        )
        options = context.options if isinstance(context.options, Mapping) else {}

        # Check Agent 4 handoff requirement
        require_a4 = bool(self.settings.require_agent4_handoff)
        if "require_agent4_handoff" in stage_input:
            require_a4 = bool(stage_input.get("require_agent4_handoff"))
        elif "require_agent4_handoff" in options:
            require_a4 = bool(options.get("require_agent4_handoff"))

        if require_a4:
            handoff = context.handoff(self.settings.expected_agent4_stage_name)
            if handoff is None:
                raise StageAdapterError(
                    "Agent6 requires handoff from stage '{0}', but it is missing.".format(
                        self.settings.expected_agent4_stage_name
                    )
                )

        # Check Agent 5 handoff requirement
        require_a5 = bool(self.settings.require_agent5_handoff)
        if "require_agent5_handoff" in stage_input:
            require_a5 = bool(stage_input.get("require_agent5_handoff"))
        elif "require_agent5_handoff" in options:
            require_a5 = bool(options.get("require_agent5_handoff"))

        if require_a5:
            handoff = context.handoff(self.settings.expected_agent5_stage_name)
            if handoff is None:
                raise StageAdapterError(
                    "Agent6 requires handoff from stage '{0}', but it is missing.".format(
                        self.settings.expected_agent5_stage_name
                    )
                )

    def _extract_handoff(
        self, context, stage_name: str
    ) -> Optional[Mapping[str, Any]]:
        handoff = context.handoff(stage_name)
        if handoff is None:
            return None
        if isinstance(handoff.payload, Mapping):
            return dict(handoff.payload)
        return None


def build_agent6_stage(
    *,
    dataset_root: str = "synthetic_data/phase6/v1",
    use_llm_summary: bool = False,
    strict_schema: bool = True,
    stage_name: str = "agent6",
    depends_on: Tuple[StageDependency, ...] = (),
    enabled: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    require_agent4_handoff: bool = False,
    require_agent5_handoff: bool = False,
    expected_agent4_stage_name: str = "agent4",
    expected_agent5_stage_name: str = "agent5",
    llm_generate: Optional[Callable[[str], str]] = None,
) -> Agent6StageAdapter:
    """
    Convenience factory for Agent 6 stage adapter.
    """
    settings = Agent6StageSettings(
        stage_name=stage_name,
        dataset_root=dataset_root,
        use_llm_summary=use_llm_summary,
        strict_schema=strict_schema,
        depends_on=depends_on,
        enabled=enabled,
        metadata=dict(metadata or {}),
        require_agent4_handoff=require_agent4_handoff,
        require_agent5_handoff=require_agent5_handoff,
        expected_agent4_stage_name=expected_agent4_stage_name,
        expected_agent5_stage_name=expected_agent5_stage_name,
    )
    return Agent6StageAdapter(settings=settings, llm_generate=llm_generate)


__all__ = [
    "Agent6StageSettings",
    "Agent6StageAdapter",
    "build_agent6_stage",
]