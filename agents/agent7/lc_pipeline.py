"""
Agent 7 LangChain pipeline with live monitoring.

Design goals:
- Preserve deterministic Phase 7 policy authority.
- Keep each step as a pure state transform suitable for LangGraph migration.
- Provide single orchestration entrypoints for:
  - Brain mode: from A6 handoff payload
  - Standalone mode: from file-based dataset
  - Live mode: from file-based + actual deployment execution
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, TypedDict, cast

try:
    _lc_runnables = import_module("langchain_core.runnables")
    RunnableLambda = getattr(_lc_runnables, "RunnableLambda")
    RunnableSequence = getattr(_lc_runnables, "RunnableSequence")
except Exception:
    class RunnableLambda:
        def __init__(self, fn: Callable[[Any], Any]) -> None:
            self.fn = fn

        def __or__(self, other: "RunnableLambda") -> "RunnableSequence":
            return RunnableSequence(self, other)

        def invoke(self, value: Any) -> Any:
            return self.fn(value)

    class RunnableSequence:
        def __init__(self, *steps: RunnableLambda) -> None:
            self.steps = list(steps)

        def __or__(self, other: RunnableLambda) -> "RunnableSequence":
            return RunnableSequence(*self.steps, other)

        def invoke(self, value: Any) -> Any:
            out = value
            for step in self.steps:
                out = step.invoke(out)
            return out


from .deployment import DeploymentConfig, DeploymentExecutor
from .ingestion import IngestionError, Phase7Ingestion, RawPhase7Bundle
from .models import (
    Agent7Output,
    Confidence,
    Decision,
    DecisionType,
    ReasonItem,
    SourceRef,
    default_human_action,
    utc_now_iso,
    validate_output_schema,
)
from .normalization import NormalizedPhase7Bundle, normalize_phase7_bundle
from .policy import Phase7PolicyEngine, PolicyConfig


class Agent7LCError(Exception):
    """Raised for Agent 7 LangChain orchestration errors."""


class Agent7State(TypedDict, total=False):
    scenario_id: str
    release_id: Optional[str]
    agent6_handoff: Optional[Mapping[str, Any]]
    raw: RawPhase7Bundle
    normalized: NormalizedPhase7Bundle
    findings: Any
    output: Any
    payload: Dict[str, Any]
    schema_valid: bool
    schema_errors: List[str]
    monitoring_state: Optional[Any]


@dataclass(frozen=True)
class LCPipelineConfig:
    dataset_root: str = "synthetic_data/phase7/v1"
    policy_version: str = "phase7-policy-v1"
    dry_run: bool = True
    strict_schema: bool = True
    stabilization_seconds: float = 60.0
    health_check_interval_seconds: float = 15.0


def build_step_functions(
    config: Optional[LCPipelineConfig] = None,
) -> Dict[str, Callable[[Agent7State], Agent7State]]:
    cfg = config or LCPipelineConfig()
    ingestion = Phase7Ingestion(dataset_root=cfg.dataset_root)
    policy_engine = Phase7PolicyEngine(config=PolicyConfig(target_environment="PRODUCTION"))

    def ingest_step(state: Agent7State) -> Agent7State:
        scenario_id = str(state.get("scenario_id", "")).strip()
        if not scenario_id:
            raise Agent7LCError("`scenario_id` is required.")
        release_id = state.get("release_id")
        a6 = state.get("agent6_handoff")

        if a6 is not None:
            raw = ingestion.ingest_from_handoffs(
                scenario_id=scenario_id,
                agent6_handoff=a6,
                release_id=release_id,
                dataset_root=cfg.dataset_root,
            )
        else:
            raw = ingestion.ingest(
                scenario_id=scenario_id,
                release_id=release_id,
            )

        new_state: Agent7State = cast(Agent7State, dict(state))
        new_state["raw"] = raw
        return new_state

    def normalize_step(state: Agent7State) -> Agent7State:
        raw = state.get("raw")
        if raw is None:
            raise Agent7LCError("Missing `raw` in state. Run ingest step first.")

        normalized = normalize_phase7_bundle(raw)

        new_state: Agent7State = cast(Agent7State, dict(state))
        new_state["normalized"] = normalized
        return new_state

    def policy_step(state: Agent7State) -> Agent7State:
        normalized = state.get("normalized")
        if normalized is None:
            raise Agent7LCError("Missing `normalized` in state.")

        findings = policy_engine.evaluate(normalized)

        new_state: Agent7State = cast(Agent7State, dict(state))
        new_state["findings"] = findings
        return new_state

    def deploy_step(state: Agent7State) -> Agent7State:
        """
        Deployment execution step.
        Only runs if all policy gates pass (decision == GO).
        In dry_run mode, simulates deployment with synthetic probes.
        """
        normalized = state.get("normalized")
        findings = state.get("findings")

        if normalized is None or findings is None:
            raise Agent7LCError("Missing `normalized` or `findings` in state.")

        new_state: Agent7State = cast(Agent7State, dict(state))
        new_state["monitoring_state"] = None

        if findings.decision.value != "GO":
            return new_state

        deploy_config = DeploymentConfig(
            dry_run=cfg.dry_run,
            stabilization_seconds=cfg.stabilization_seconds,
            health_check_interval_seconds=cfg.health_check_interval_seconds,
        )
        executor = DeploymentExecutor(config=deploy_config)

        version = _resolve_version(normalized)
        record = executor.execute(
            scenario_id=normalized.scenario_id,
            release_id=str(normalized.release_id or "unknown"),
            version=version,
        )

        new_state["deployment_record"] = record.to_dict()
        new_state["monitoring_state"] = record.monitoring.to_dict() if record.monitoring else None
        return new_state

    def assemble_step(state: Agent7State) -> Agent7State:
        """
        Assemble the final output payload from policy findings and deployment record.
        """
        findings = state.get("findings")
        normalized = state.get("normalized")
        raw = state.get("raw")

        if normalized is None or findings is None:
            raise Agent7LCError("Missing `normalized` or `findings` in state.")

        decision = findings.decision
        reason_items = _build_reason_items(findings)
        evidence = _build_evidence_from_findings(findings)
        confidence = Confidence.HIGH if decision == Decision.GO else Confidence.MEDIUM
        summary = _build_summary(decision, findings, normalized)

        deployment_record = state.get("deployment_record")
        monitoring_state = state.get("monitoring_state")

        payload: Dict[str, Any] = {
            "scenario_id": normalized.scenario_id,
            "release_id": str(normalized.release_id or "unknown"),
            "decision": decision.value,
            "decision_type": DecisionType.DETERMINISTIC.value,
            "reasons": [r.to_dict() for r in reason_items],
            "evidence": [e.to_dict() for e in evidence],
            "confidence": confidence.value,
            "human_action": default_human_action(decision),
            "summary": summary,
            "policy_version": cfg.policy_version,
            "timestamp_utc": utc_now_iso(),
        }

        # Attach rule findings
        payload["rule_findings"] = findings.to_dict()

        # Attach deployment record and monitoring state if present
        if deployment_record:
            payload["deployment_record"] = deployment_record
        if monitoring_state:
            payload["monitoring_state"] = monitoring_state

        # Add meta
        payload["meta"] = {
            "agent": "agent7_langchain",
            "dataset_root": cfg.dataset_root,
            "scenario_id": normalized.scenario_id,
            "release_id": raw.release_id if raw else normalized.release_id,
        }

        new_state: Agent7State = cast(Agent7State, dict(state))
        new_state["output"] = payload
        new_state["payload"] = payload
        return new_state

    def validate_step(state: Agent7State) -> Agent7State:
        payload = state.get("payload")
        if payload is None:
            raise Agent7LCError("Missing `payload` in state.")

        valid, errors = validate_output_schema(payload)
        payload["schema_validation"] = {"valid": valid, "errors": errors}

        if cfg.strict_schema and not valid:
            raise Agent7LCError("Output schema validation failed: {0}".format(errors))

        new_state: Agent7State = cast(Agent7State, dict(state))
        new_state["payload"] = payload
        new_state["schema_valid"] = valid
        new_state["schema_errors"] = errors
        return new_state

    return {
        "ingest": ingest_step,
        "normalize": normalize_step,
        "policy": policy_step,
        "deploy": deploy_step,
        "assemble": assemble_step,
        "validate": validate_step,
    }


def build_langchain_pipeline(
    config: Optional[LCPipelineConfig] = None,
) -> RunnableSequence:
    steps = build_step_functions(config=config)
    return (
        RunnableLambda(steps["ingest"])
        | RunnableLambda(steps["normalize"])
        | RunnableLambda(steps["policy"])
        | RunnableLambda(steps["deploy"])
        | RunnableLambda(steps["assemble"])
        | RunnableLambda(steps["validate"])
    )


# ---------------------------------------------------------------------------
# Orchestrator wrapper
# ---------------------------------------------------------------------------


class LangChainAgent7Pipeline:
    """
    LangChain-based orchestrator for Agent 7.

    Supports:
    - assess_from_handoffs: BrainOrchestrator mode with A6 handoff
    - assess_scenario: standalone file-based mode
    - assess_with_deployment: standalone + actual deployment execution
    """

    def __init__(self, config: Optional[LCPipelineConfig] = None) -> None:
        self.config = config or LCPipelineConfig()
        self.ingestion = Phase7Ingestion(dataset_root=self.config.dataset_root)
        self.pipeline = build_langchain_pipeline(config=self.config)

    def validate_dataset(self) -> Dict[str, Any]:
        return self.ingestion.validate_dataset()

    def list_scenarios(self) -> List[Dict[str, str]]:
        return self.ingestion.list_scenarios()

    def assess_from_handoffs(
        self,
        scenario_id: str,
        agent6_handoff: Optional[Mapping[str, Any]],
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        initial_state: Agent7State = {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "agent6_handoff": agent6_handoff,
        }
        try:
            final_state: Agent7State = self.pipeline.invoke(initial_state)
        except IngestionError as exc:
            raise Agent7LCError(
                "Ingestion failed for scenario {0}: {1}".format(scenario_id, exc)
            ) from exc

        payload = final_state.get("payload")
        if payload is None:
            raise Agent7LCError("Pipeline completed without payload.")
        return payload

    def assess_scenario(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        initial_state: Agent7State = {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "agent6_handoff": None,
        }
        try:
            final_state: Agent7State = self.pipeline.invoke(initial_state)
        except IngestionError as exc:
            raise Agent7LCError(
                "Ingestion failed for scenario {0}: {1}".format(scenario_id, exc)
            ) from exc

        payload = final_state.get("payload")
        if payload is None:
            raise Agent7LCError("Pipeline completed without payload.")
        return payload

    def evaluate_against_labels(
        self,
        predictions: Optional[Sequence[Dict[str, Any]]] = None,
        labels_csv_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        if predictions is None:
            predictions = self.assess_all_scenarios()

        labels_path = (
            Path(labels_csv_path)
            if labels_csv_path
            else Path(self.config.dataset_root) / "phase7_decision_labels.csv"
        )
        labels = self._read_labels(labels_path)

        pred_by_scenario = {
            str(p.get("scenario_id", "")).strip(): p for p in predictions
        }

        total = matched = 0
        rows: List[Dict[str, Any]] = []

        for label in labels:
            sid = label["scenario_id"]
            expected = label["expected_decision"]
            pred = pred_by_scenario.get(sid)
            total += 1
            if pred is None:
                rows.append({"scenario_id": sid, "match": False, "note": "missing"})
                continue

            predicted = str(pred.get("decision", "")).strip().upper()
            is_match = predicted == expected
            if is_match:
                matched += 1
            rows.append({
                "scenario_id": sid,
                "expected_decision": expected,
                "predicted_decision": predicted,
                "match": is_match,
            })

        accuracy = round(matched / total, 4) if total else 0.0
        return {
            "total_scenarios": total,
            "matched": matched,
            "accuracy": accuracy,
            "rows": rows,
        }

    def assess_all_scenarios(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for row in self.list_scenarios():
            scenario_id = str(row.get("scenario_id", "")).strip()
            release_id = str(row.get("release_id", "")).strip() or None
            if not scenario_id:
                continue
            results.append(
                self.assess_scenario(scenario_id=scenario_id, release_id=release_id)
            )
        return results

    @staticmethod
    def _read_labels(path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            return []
        rows: List[Dict[str, str]] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                expected = str(row.get("expected_decision", "")).strip().upper()
                if expected not in {"GO", "HOLD"}:
                    continue
                rows.append({
                    "scenario_id": str(row.get("scenario_id", "")).strip(),
                    "release_id": str(row.get("release_id", "")).strip(),
                    "expected_decision": expected,
                })
        return rows


def _resolve_version(bundle: NormalizedPhase7Bundle) -> str:
    """Extract version from agent6 context or module versions."""
    if bundle.agent6_context:
        a6 = bundle.agent6_context
        if hasattr(a6, "module_versions") and a6.module_versions:
            mods = dict(a6.module_versions)
            if mods:
                first = next(iter(mods.items()))
                return f"{first[0]}@{first[1]}"
    return "unknown@0.0.0"


def _build_reason_items(findings: Any) -> Tuple[ReasonItem, ...]:
    """Build human-readable reason items from triggered rule findings."""
    items: List[ReasonItem] = []
    for f in findings.findings:
        if f.triggered:
            items.append(ReasonItem(
                title=f.reason.split(".")[0] if "." in f.reason else f.reason,
                detail=f.reason,
                rule_code=f.code.value,
                evidence=f.evidence,
            ))
    return tuple(items)


def _build_evidence_from_findings(findings: Any) -> Tuple[SourceRef, ...]:
    """Collect all evidence refs from triggered findings."""
    refs: List[SourceRef] = []
    for f in findings.findings:
        if f.triggered:
            refs.extend(list(f.evidence))
    return tuple(refs)


def _build_summary(decision: Decision, findings: Any, normalized: NormalizedPhase7Bundle) -> str:
    """Build a one-line summary."""
    triggered = findings.triggered_rule_codes
    if decision == Decision.GO:
        return (
            f"GO for production deployment of {normalized.release_id or normalized.scenario_id}. "
            f"All Phase 7 gates passed."
        )
    codes = ", ".join(triggered) if triggered else "unknown"
    return (
        f"HOLD for production deployment of {normalized.release_id or normalized.scenario_id}. "
        f"Triggered rules: {codes}."
    )


__all__ = [
    "Agent7LCError",
    "Agent7State",
    "LCPipelineConfig",
    "build_step_functions",
    "build_langchain_pipeline",
    "LangChainAgent7Pipeline",
    "build_reason_items",
]