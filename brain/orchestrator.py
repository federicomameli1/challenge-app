"""
Brain orchestrator engine with dependency-aware execution and gating policies.

This module provides a generic orchestration runtime that can manage:
- current stages (Agent 4 -> Agent 5),
- future stages (Agent 6, Agent 7, ...),
without changing core orchestration behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from uuid import uuid4

from .models import (
    BrainRunReport,
    BrainRunRequest,
    DependencyPolicy,
    RunStatus,
    StageDependency,
    StageExecutionResult,
    StageStatus,
)
from .stages import BrainStage, BrainStageError, StageExecutionContext, StageRegistry


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BrainOrchestratorError(Exception):
    """Raised for orchestrator-level planning or runtime failures."""


@dataclass(frozen=True)
class DependencyCheckResult:
    can_run: bool
    reason: Optional[str]
    snapshot: Dict[str, Any]


class BrainOrchestrator:
    """
    Generic stage orchestrator with dependency and gating policies.

    Core behavior:
    - Executes stages in configured order.
    - Validates dependency outcomes before running each stage.
    - Supports policy-based gating:
        * require_success
        * require_go
        * allow_any
    - Produces typed run report with stage results and handoffs.
    """

    def __init__(
        self,
        *,
        registry: StageRegistry,
        stage_order: Sequence[str],
    ) -> None:
        if not stage_order:
            raise BrainOrchestratorError("stage_order cannot be empty.")

        self.registry = registry
        self.stage_order: Tuple[str, ...] = tuple(stage_order)
        self._validate_plan()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def run(self, request: BrainRunRequest) -> BrainRunReport:
        run_id = self._new_run_id()
        report = BrainRunReport(
            run_id=run_id,
            scenario_id=request.scenario_id,
            release_id=request.release_id,
            stage_order=self.stage_order,
            metadata=dict(request.metadata),
            started_at=_utc_now(),
        )

        for stage_name in self.stage_order:
            stage = self.registry.get(stage_name)

            if not stage.spec.enabled:
                result = StageExecutionResult(
                    stage_name=stage_name,
                    status=StageStatus.SKIPPED,
                    scenario_id=request.scenario_id,
                    release_id=request.release_id,
                    skip_reason="stage_disabled",
                    metadata={"enabled": False},
                    started_at=_utc_now(),
                    ended_at=_utc_now(),
                )
                report.add_stage_result(result)
                continue

            dep_check = self._check_dependencies(
                stage=stage,
                report=report,
                options=request.options,
            )
            if not dep_check.can_run:
                result = StageExecutionResult(
                    stage_name=stage_name,
                    status=StageStatus.SKIPPED,
                    scenario_id=request.scenario_id,
                    release_id=request.release_id,
                    skip_reason=dep_check.reason or "dependency_policy_blocked",
                    dependency_snapshot=dep_check.snapshot,
                    started_at=_utc_now(),
                    ended_at=_utc_now(),
                )
                report.add_stage_result(result)
                continue

            stage_input = request.stage_inputs.get(stage_name, {})
            context = StageExecutionContext(
                run_id=run_id,
                stage_name=stage_name,
                scenario_id=request.scenario_id,
                release_id=request.release_id,
                stage_input=dict(stage_input),
                options=dict(request.options),
                metadata=dict(request.metadata),
                handoffs=dict(report.handoffs),
                prior_stage_results=dict(report.stages),
            )

            try:
                raw_result = stage.run(context)
            except Exception as exc:
                raw_result = StageExecutionResult(
                    stage_name=stage_name,
                    status=StageStatus.FAILED,
                    scenario_id=request.scenario_id,
                    release_id=request.release_id,
                    error=str(exc),
                    dependency_snapshot=dep_check.snapshot,
                    started_at=_utc_now(),
                    ended_at=_utc_now(),
                    metadata={"orchestrator_caught_exception": True},
                )

            result = self._normalize_stage_result(
                stage_name=stage_name,
                request=request,
                result=raw_result,
                dependency_snapshot=dep_check.snapshot,
            )
            report.add_stage_result(result)

            if result.status == StageStatus.SUCCESS:
                try:
                    handoff = stage.build_handoff(context, result)
                except Exception as exc:
                    # Handoff construction failure is stage failure from orchestration perspective.
                    fail = StageExecutionResult(
                        stage_name=stage_name,
                        status=StageStatus.FAILED,
                        scenario_id=result.scenario_id,
                        release_id=result.release_id,
                        decision=result.decision,
                        payload=dict(result.payload),
                        metadata=dict(result.metadata),
                        error="handoff_build_failed: {0}".format(exc),
                        dependency_snapshot=dict(result.dependency_snapshot),
                        started_at=result.started_at or _utc_now(),
                        ended_at=_utc_now(),
                    )
                    report.add_stage_result(fail)
                    report.errors.append(
                        "Stage '{0}' handoff build failed: {1}".format(stage_name, exc)
                    )
                    continue

                if handoff is not None:
                    report.add_handoff(handoff)

            if result.status == StageStatus.FAILED:
                report.errors.append(
                    "Stage '{0}' failed: {1}".format(
                        stage_name, result.error or "unknown_error"
                    )
                )

        report.set_finished()
        report.finalize_status()
        return report

    # ---------------------------------------------------------------------
    # Planning + validation
    # ---------------------------------------------------------------------

    def _validate_plan(self) -> None:
        seen = set()
        for stage_name in self.stage_order:
            if stage_name in seen:
                raise BrainOrchestratorError(
                    "Duplicate stage in stage_order: {0}".format(stage_name)
                )
            seen.add(stage_name)

            if not self.registry.has(stage_name):
                raise BrainOrchestratorError(
                    "Stage '{0}' is not registered.".format(stage_name)
                )

        known = set(self.stage_order)
        for stage_name in self.stage_order:
            stage = self.registry.get(stage_name)
            for dep in stage.depends_on:
                if dep.stage_name not in known:
                    raise BrainOrchestratorError(
                        "Stage '{0}' depends on unknown stage '{1}'.".format(
                            stage_name, dep.stage_name
                        )
                    )

    # ---------------------------------------------------------------------
    # Dependency policy checks
    # ---------------------------------------------------------------------

    def _check_dependencies(
        self,
        *,
        stage: BrainStage,
        report: BrainRunReport,
        options: Mapping[str, Any],
    ) -> DependencyCheckResult:
        if not stage.depends_on:
            return DependencyCheckResult(can_run=True, reason=None, snapshot={})

        snapshot: Dict[str, Any] = {}
        blocking_reasons: List[str] = []

        for dep in stage.depends_on:
            dep_result = report.stage_result(dep.stage_name)
            dep_snapshot = self._check_one_dependency(
                stage_name=stage.name,
                dependency=dep,
                dep_result=dep_result,
                options=options,
            )
            snapshot[dep.stage_name] = dep_snapshot

            if not dep_snapshot["allowed"] and dep.required:
                blocking_reasons.append(dep_snapshot["reason"])

        if blocking_reasons:
            return DependencyCheckResult(
                can_run=False,
                reason="; ".join([r for r in blocking_reasons if r]),
                snapshot=snapshot,
            )

        return DependencyCheckResult(can_run=True, reason=None, snapshot=snapshot)

    def _check_one_dependency(
        self,
        *,
        stage_name: str,
        dependency: StageDependency,
        dep_result: Optional[StageExecutionResult],
        options: Mapping[str, Any],
    ) -> Dict[str, Any]:
        dep_name = dependency.stage_name
        policy = dependency.policy

        base = {
            "dependency_stage": dep_name,
            "required": dependency.required,
            "policy": policy.value,
            "status": dep_result.status.value if dep_result is not None else None,
            "decision": dep_result.decision if dep_result is not None else None,
            "allowed": False,
            "reason": "",
        }

        if dep_result is None:
            if dependency.required:
                base["reason"] = "required dependency missing"
                return base
            base["allowed"] = True
            base["reason"] = "optional dependency missing"
            return base

        if policy == DependencyPolicy.ALLOW_ANY:
            base["allowed"] = True
            base["reason"] = "allow_any policy"
            return base

        if policy == DependencyPolicy.REQUIRE_SUCCESS:
            if dep_result.status == StageStatus.SUCCESS:
                base["allowed"] = True
                base["reason"] = "dependency succeeded"
            else:
                base["reason"] = "dependency must be success"
            return base

        if policy == DependencyPolicy.REQUIRE_GO:
            allow_after_hold = self._allow_after_hold(
                stage_name=stage_name,
                dependency_stage=dep_name,
                options=options,
            )
            dep_decision = (dep_result.decision or "").strip().upper()

            if dep_result.status == StageStatus.SUCCESS and dep_decision == "GO":
                base["allowed"] = True
                base["reason"] = "dependency decision is GO"
                return base

            if dep_result.status == StageStatus.SUCCESS and dep_decision == "HOLD":
                if allow_after_hold:
                    base["allowed"] = True
                    base["reason"] = "dependency HOLD overridden by option"
                else:
                    base["reason"] = "dependency decision HOLD blocks downstream"
                return base

            base["reason"] = "dependency must be success with GO decision"
            return base

        base["reason"] = "unknown dependency policy"
        return base

    def _allow_after_hold(
        self,
        *,
        stage_name: str,
        dependency_stage: str,
        options: Mapping[str, Any],
    ) -> bool:
        # Generic per-link override
        generic_key = "allow_{0}_after_{1}_hold".format(stage_name, dependency_stage)
        if generic_key in options:
            return bool(options.get(generic_key))

        # Backward-compatible specific key requested in CLI contract.
        if stage_name == "agent5" and dependency_stage == "agent4":
            if "allow_agent5_after_agent4_hold" in options:
                return bool(options.get("allow_agent5_after_agent4_hold"))

        return False

    # ---------------------------------------------------------------------
    # Result normalization
    # ---------------------------------------------------------------------

    def _normalize_stage_result(
        self,
        *,
        stage_name: str,
        request: BrainRunRequest,
        result: StageExecutionResult,
        dependency_snapshot: Mapping[str, Any],
    ) -> StageExecutionResult:
        scenario_id = result.scenario_id or request.scenario_id
        release_id = (
            result.release_id if result.release_id is not None else request.release_id
        )

        return StageExecutionResult(
            stage_name=stage_name,
            status=result.status,
            scenario_id=scenario_id,
            release_id=release_id,
            decision=(result.decision.strip().upper() if result.decision else None),
            payload=dict(result.payload),
            metadata=dict(result.metadata),
            error=result.error,
            skip_reason=result.skip_reason,
            dependency_snapshot=dict(dependency_snapshot),
            started_at=result.started_at or _utc_now(),
            ended_at=result.ended_at or _utc_now(),
        )

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _new_run_id() -> str:
        return "brain-{0}".format(uuid4().hex[:12])


def build_default_stage_order() -> Tuple[str, ...]:
    """
    Default linear flow for current system.
    """
    return ("agent4", "agent5")


__all__ = [
    "BrainOrchestrator",
    "BrainOrchestratorError",
    "build_default_stage_order",
]
