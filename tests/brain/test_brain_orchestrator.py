from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from brain.models import (
    BrainRunRequest,
    DependencyPolicy,
    StageDependency,
    StageExecutionResult,
    StageSpec,
    StageStatus,
)
from brain.orchestrator import BrainOrchestrator
from brain.stages import BrainStage, StageExecutionContext, StageRegistry
from scripts.run_brain_orchestrator import (
    _build_request,
    _options_from_args,
    _stage_inputs_from_args,
)


@dataclass(frozen=True)
class _FakeStageConfig:
    name: str
    decision: Optional[str] = None
    status: StageStatus = StageStatus.SUCCESS
    depends_on: Tuple[StageDependency, ...] = ()
    enabled: bool = True


class _FakeStage(BrainStage):
    def __init__(self, cfg: _FakeStageConfig) -> None:
        self._cfg = cfg
        self._spec = StageSpec(
            name=cfg.name,
            depends_on=cfg.depends_on,
            enabled=cfg.enabled,
            metadata={"fake": True},
        )

    @property
    def spec(self) -> StageSpec:
        return self._spec

    def run(self, context: StageExecutionContext) -> StageExecutionResult:
        return StageExecutionResult(
            stage_name=self._cfg.name,
            status=self._cfg.status,
            scenario_id=context.scenario_id,
            release_id=context.release_id,
            decision=self._cfg.decision,
            payload={"source": self._cfg.name},
            metadata={"ran": True},
        )


def _make_orchestrator(*stages: BrainStage) -> BrainOrchestrator:
    registry = StageRegistry()
    for stage in stages:
        registry.register(stage)
    return BrainOrchestrator(
        registry=registry,
        stage_order=tuple(stage.name for stage in stages),
    )


def test_downstream_skipped_when_dependency_hold_default_policy() -> None:
    agent4 = _FakeStage(_FakeStageConfig(name="agent4", decision="HOLD"))
    agent5 = _FakeStage(
        _FakeStageConfig(
            name="agent5",
            decision="GO",
            depends_on=(
                StageDependency(
                    stage_name="agent4",
                    required=True,
                    policy=DependencyPolicy.REQUIRE_GO,
                ),
            ),
        )
    )

    orchestrator = _make_orchestrator(agent4, agent5)
    report = orchestrator.run(
        BrainRunRequest(scenario_id="S4-002", stage_inputs={}, options={})
    )

    agent4_result = report.stage_result("agent4")
    agent5_result = report.stage_result("agent5")

    assert agent4_result is not None
    assert agent4_result.status == StageStatus.SUCCESS
    assert agent4_result.decision == "HOLD"

    assert agent5_result is not None
    assert agent5_result.status == StageStatus.SKIPPED
    assert "HOLD blocks downstream" in (agent5_result.skip_reason or "")
    assert report.status.value == "partial"


def test_downstream_runs_when_dependency_go() -> None:
    agent4 = _FakeStage(_FakeStageConfig(name="agent4", decision="GO"))
    agent5 = _FakeStage(
        _FakeStageConfig(
            name="agent5",
            decision="GO",
            depends_on=(
                StageDependency(
                    stage_name="agent4",
                    required=True,
                    policy=DependencyPolicy.REQUIRE_GO,
                ),
            ),
        )
    )

    orchestrator = _make_orchestrator(agent4, agent5)
    report = orchestrator.run(BrainRunRequest(scenario_id="S4-001", options={}))

    agent4_result = report.stage_result("agent4")
    agent5_result = report.stage_result("agent5")

    assert agent4_result is not None
    assert agent4_result.status == StageStatus.SUCCESS
    assert agent4_result.decision == "GO"

    assert agent5_result is not None
    assert agent5_result.status == StageStatus.SUCCESS
    assert agent5_result.decision == "GO"
    assert report.status.value == "success"


def test_downstream_skipped_when_dependency_failed() -> None:
    failing_stage = _FakeStage(
        _FakeStageConfig(name="agent4", status=StageStatus.FAILED, decision=None)
    )
    downstream = _FakeStage(
        _FakeStageConfig(
            name="agent5",
            decision="GO",
            depends_on=(
                StageDependency(
                    stage_name="agent4",
                    required=True,
                    policy=DependencyPolicy.REQUIRE_SUCCESS,
                ),
            ),
        )
    )

    orchestrator = _make_orchestrator(failing_stage, downstream)
    report = orchestrator.run(BrainRunRequest(scenario_id="S4-009", options={}))

    a4 = report.stage_result("agent4")
    a5 = report.stage_result("agent5")

    assert a4 is not None
    assert a4.status == StageStatus.FAILED

    assert a5 is not None
    assert a5.status == StageStatus.SKIPPED
    assert "dependency must be success" in (a5.skip_reason or "")


def test_allow_override_allows_agent5_after_agent4_hold() -> None:
    agent4 = _FakeStage(_FakeStageConfig(name="agent4", decision="HOLD"))
    agent5 = _FakeStage(
        _FakeStageConfig(
            name="agent5",
            decision="GO",
            depends_on=(
                StageDependency(
                    stage_name="agent4",
                    required=True,
                    policy=DependencyPolicy.REQUIRE_GO,
                ),
            ),
        )
    )

    orchestrator = _make_orchestrator(agent4, agent5)
    report = orchestrator.run(
        BrainRunRequest(
            scenario_id="S4-008",
            options={"allow_agent5_after_agent4_hold": True},
        )
    )

    a5 = report.stage_result("agent5")
    assert a5 is not None
    assert a5.status == StageStatus.SUCCESS
    assert report.status.value == "success"


def _namespace(**overrides: object) -> argparse.Namespace:
    base: Dict[str, object] = {
        "scenario_id": "S4-001",
        "release_id": None,
        "agent4_scenario_id": None,
        "agent5_scenario_id": None,
        "agent4_release_id": None,
        "agent5_release_id": None,
        "agent4_dataset_root": "synthetic_data/v1",
        "agent5_dataset_root": "synthetic_data/phase5/v1",
        "agent4_source_adapter_kind": None,
        "agent4_use_llm_summary": False,
        "agent4_strict_schema": False,
        "agent5_use_llm_summary": False,
        "agent5_strict_schema": False,
        "allow_agent5_after_agent4_hold": False,
        "pretty": False,
        "output": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cli_stage_input_mapping_with_overrides() -> None:
    args = _namespace(
        scenario_id="SHARED-001",
        agent4_scenario_id="S4-007",
        agent5_scenario_id="P5-021",
        agent4_release_id="REL-A4-1",
        agent5_release_id="REL-P5-9",
    )

    stage_inputs = _stage_inputs_from_args(args)

    assert stage_inputs["agent4"]["scenario_id"] == "S4-007"
    assert stage_inputs["agent5"]["scenario_id"] == "P5-021"
    assert stage_inputs["agent4"]["release_id"] == "REL-A4-1"
    assert stage_inputs["agent5"]["release_id"] == "REL-P5-9"
    assert stage_inputs["agent5"]["require_agent4_handoff"] is True


def test_cli_request_building_and_options_mapping() -> None:
    args = _namespace(
        scenario_id="S4-010",
        release_id="REL-2026.04.10",
        agent5_scenario_id="P5-048",
        allow_agent5_after_agent4_hold=True,
    )

    options = _options_from_args(args)
    assert options["allow_agent5_after_agent4_hold"] is True

    request = _build_request(args)
    assert request.scenario_id == "S4-010"
    assert request.release_id == "REL-2026.04.10"
    assert request.stage_inputs["agent5"]["scenario_id"] == "P5-048"
    assert request.options["allow_agent5_after_agent4_hold"] is True
    assert "agent4_dataset_root" in request.metadata
    assert "agent5_dataset_root" in request.metadata
