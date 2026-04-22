"""
LangChain-based Agent 5 pipeline with migration-friendly step boundaries.

Design goals:
- Preserve deterministic Phase 5 policy authority.
- Keep each step as a pure state transform suitable for LangGraph migration.
- Provide a single orchestration entrypoint for:
  - single-scenario assessment
  - full-dataset assessment
  - benchmark evaluation against labels
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, TypedDict, cast

try:
    _lc_runnables = import_module("langchain_core.runnables")
    RunnableLambda = getattr(_lc_runnables, "RunnableLambda")
    RunnableSequence = getattr(_lc_runnables, "RunnableSequence")
except Exception:
    # Lightweight fallback so this module remains usable without LangChain installed.
    class RunnableLambda:  # type: ignore[override]
        def __init__(self, fn: Callable[[Any], Any]) -> None:
            self.fn = fn

        def __or__(self, other: "RunnableLambda") -> "RunnableSequence":
            return RunnableSequence(self, other)

        def invoke(self, value: Any) -> Any:
            return self.fn(value)

    class RunnableSequence:  # type: ignore[override]
        def __init__(self, *steps: RunnableLambda) -> None:
            self.steps = list(steps)

        def __or__(self, other: RunnableLambda) -> "RunnableSequence":
            return RunnableSequence(*self.steps, other)

        def invoke(self, value: Any) -> Any:
            out = value
            for step in self.steps:
                out = step.invoke(out)
            return out


from .evidence import (
    build_traceable_reasons_and_evidence,
    reason_evidence_coverage_report,
)
from .explanation import ExplanationContext, build_explanation_with_optional_llm
from .ingestion import IngestionError, Phase5Ingestion, RawInputBundle
from .models import validate_output_schema
from .normalization import NormalizedEvidenceBundle, normalize_evidence_bundle
from .policy import Phase5PolicyEngine, PolicyConfig


class Agent5LCError(Exception):
    """Raised for Agent 5 LangChain orchestration errors."""


class Agent5State(TypedDict, total=False):
    # Inputs
    scenario_id: str
    release_id: Optional[str]
    dataset_root: str

    # Intermediate artifacts
    raw: RawInputBundle
    normalized: NormalizedEvidenceBundle
    findings: Any  # RuleFindings
    context: ExplanationContext

    # Outputs
    output: Any  # Agent5Output
    payload: Dict[str, Any]
    schema_valid: bool
    schema_errors: List[str]


@dataclass(frozen=True)
class LCPipelineConfig:
    dataset_root: str = "synthetic_data/phase5/v1"
    policy_version: str = "phase5-policy-v1"
    use_llm_summary: bool = True
    strict_schema: bool = True
    evidence_limit_per_reason: int = 5
    total_evidence_limit: int = 20


def _has_evidence_incomplete(normalized: NormalizedEvidenceBundle) -> bool:
    return bool(normalized.test_evidence_incomplete)


def _has_evidence_conflict(normalized: NormalizedEvidenceBundle) -> bool:
    """
    Lightweight conflict heuristic:
    - A4 indicates unresolved continuity blockers unclosed while phase5 summary
      appears complete/non-blocking.
    """
    if (
        normalized.agent4_context is not None
        and normalized.agent4_context.decision == "HOLD"
        and normalized.agent4_unresolved_hard_blocker_unclosed
        and not normalized.test_evidence_incomplete
    ):
        return True
    return False


def _build_continuity_flags(normalized: NormalizedEvidenceBundle) -> Dict[str, Any]:
    ctx = normalized.agent4_context
    if ctx is None:
        return {
            "agent4_context_present": False,
            "agent4_decision": None,
            "agent4_unresolved_conditions": [],
            "closure_confirmed": False,
            "continuity_hold": False,
        }

    return {
        "agent4_context_present": True,
        "agent4_decision": ctx.decision,
        "agent4_unresolved_conditions": list(ctx.unresolved_conditions),
        "closure_confirmed": bool(ctx.closure_confirmed),
        "continuity_hold": bool(normalized.agent4_unresolved_hard_blocker_unclosed),
    }


def _merge_traceability(
    payload: Dict[str, Any],
    findings: Any,
    evidence_limit_per_reason: int,
    total_evidence_limit: int,
) -> Dict[str, Any]:
    trace_reasons, trace_evidence = build_traceable_reasons_and_evidence(
        findings=findings,
        evidence_limit_per_reason=evidence_limit_per_reason,
        total_evidence_limit=total_evidence_limit,
    )

    if not isinstance(payload.get("reasons"), list) or len(payload["reasons"]) == 0:
        payload["reasons"] = [r.to_dict() for r in trace_reasons]

    if not isinstance(payload.get("evidence"), list) or len(payload["evidence"]) == 0:
        payload["evidence"] = [e.to_dict() for e in trace_evidence]

    # Attach/merge lightweight coverage diagnostics.
    coverage = reason_evidence_coverage_report(trace_reasons)
    if not isinstance(payload.get("coverage_metrics"), dict):
        payload["coverage_metrics"] = {}
    payload["coverage_metrics"].update(coverage)

    return payload


def build_step_functions(
    config: Optional[LCPipelineConfig] = None,
    llm_generate: Optional[Callable[[str], str]] = None,
) -> Dict[str, Callable[[Agent5State], Agent5State]]:
    """
    Build migration-friendly step functions.
    Each step is a pure state transform: state_in -> state_out.
    """
    cfg = config or LCPipelineConfig()
    ingestion = Phase5Ingestion(dataset_root=cfg.dataset_root)
    policy_engine = Phase5PolicyEngine(config=PolicyConfig(target_environment="TEST"))

    def ingest_step(state: Agent5State) -> Agent5State:
        scenario_id = str(state.get("scenario_id", "")).strip()
        if not scenario_id:
            raise Agent5LCError("`scenario_id` is required.")
        release_id = state.get("release_id")

        raw = ingestion.ingest(scenario_id=scenario_id, release_id=release_id)

        new_state: Agent5State = cast(Agent5State, dict(state))
        new_state["raw"] = raw
        return new_state

    def normalize_step(state: Agent5State) -> Agent5State:
        raw = state.get("raw")
        if raw is None:
            raise Agent5LCError("Missing `raw` in state. Run ingest step first.")

        normalized = normalize_evidence_bundle(raw)

        new_state: Agent5State = cast(Agent5State, dict(state))
        new_state["normalized"] = normalized
        return new_state

    def policy_step(state: Agent5State) -> Agent5State:
        raw = state.get("raw")
        normalized = state.get("normalized")
        if raw is None or normalized is None:
            raise Agent5LCError("Missing `raw` or `normalized` in state.")

        findings = policy_engine.evaluate(normalized, environment=raw.environment)

        continuity_flags = _build_continuity_flags(normalized)

        context = ExplanationContext(
            scenario_id=raw.scenario_id,
            release_id=raw.release_id,
            findings=findings,
            evidence_conflict=_has_evidence_conflict(normalized),
            evidence_incomplete=_has_evidence_incomplete(normalized),
            policy_version=cfg.policy_version,
            missing_artifacts=tuple(normalized.missing_optional_artifacts),
            cross_phase_continuity_flags=continuity_flags,
        )

        new_state: Agent5State = cast(Agent5State, dict(state))
        new_state["findings"] = findings
        new_state["context"] = context
        return new_state

    def explain_step(state: Agent5State) -> Agent5State:
        context = state.get("context")
        raw = state.get("raw")
        findings = state.get("findings")
        if context is None or raw is None or findings is None:
            raise Agent5LCError("Missing `context`, `raw`, or `findings` in state.")

        llm_callable = llm_generate if cfg.use_llm_summary else None
        output_obj = build_explanation_with_optional_llm(
            context=context,
            llm_generate=llm_callable,
        )
        payload = output_obj.to_dict()

        payload = _merge_traceability(
            payload=payload,
            findings=findings,
            evidence_limit_per_reason=cfg.evidence_limit_per_reason,
            total_evidence_limit=cfg.total_evidence_limit,
        )

        payload["meta"] = {
            "agent": "agent5_langchain",
            "dataset_root": cfg.dataset_root,
            "scenario_id": raw.scenario_id,
            "release_id": raw.release_id,
        }

        new_state: Agent5State = cast(Agent5State, dict(state))
        new_state["output"] = output_obj
        new_state["payload"] = payload
        return new_state

    def validate_step(state: Agent5State) -> Agent5State:
        payload = state.get("payload")
        if payload is None:
            raise Agent5LCError("Missing `payload` in state.")

        valid, errors = validate_output_schema(payload)
        payload["schema_validation"] = {"valid": valid, "errors": errors}

        if cfg.strict_schema and not valid:
            raise Agent5LCError("Output schema validation failed: {0}".format(errors))

        new_state: Agent5State = cast(Agent5State, dict(state))
        new_state["payload"] = payload
        new_state["schema_valid"] = valid
        new_state["schema_errors"] = errors
        return new_state

    return {
        "ingest": ingest_step,
        "normalize": normalize_step,
        "policy": policy_step,
        "explain": explain_step,
        "validate": validate_step,
    }


def build_langchain_pipeline(
    config: Optional[LCPipelineConfig] = None,
    llm_generate: Optional[Callable[[str], str]] = None,
) -> RunnableSequence:
    """
    Build RunnableSequence pipeline for Agent 5.
    """
    steps = build_step_functions(config=config, llm_generate=llm_generate)
    return (
        RunnableLambda(steps["ingest"])
        | RunnableLambda(steps["normalize"])
        | RunnableLambda(steps["policy"])
        | RunnableLambda(steps["explain"])
        | RunnableLambda(steps["validate"])
    )


class LangChainAgent5Pipeline:
    """
    LangChain-based orchestrator wrapper for Agent 5.

    Exposes:
    - single-scenario assessment
    - full dataset assessment
    - benchmark evaluation against labels
    """

    def __init__(
        self,
        config: Optional[LCPipelineConfig] = None,
        llm_generate: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.config = config or LCPipelineConfig()
        self.llm_generate = llm_generate
        self.ingestion = Phase5Ingestion(dataset_root=self.config.dataset_root)
        self.pipeline = build_langchain_pipeline(
            config=self.config,
            llm_generate=self.llm_generate,
        )

    def validate_dataset(self) -> Dict[str, Any]:
        return self.ingestion.validate_dataset()

    def list_scenarios(self) -> List[Dict[str, str]]:
        return self.ingestion.list_scenarios()

    def assess_scenario(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        initial_state: Agent5State = {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "dataset_root": self.config.dataset_root,
        }
        try:
            final_state: Agent5State = self.pipeline.invoke(initial_state)
        except IngestionError as exc:
            raise Agent5LCError(
                "Ingestion failed for scenario {0}: {1}".format(scenario_id, exc)
            ) from exc

        payload = final_state.get("payload")
        if payload is None:
            raise Agent5LCError("Pipeline completed without payload.")
        return payload

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
            else Path(self.config.dataset_root) / "phase5_decision_labels.csv"
        )
        labels = self._read_labels(labels_path)

        pred_by_scenario = {
            str(p.get("scenario_id", "")).strip(): p for p in predictions
        }

        total = 0
        matched = 0
        false_go = 0
        false_hold = 0
        missing_predictions = 0
        rows: List[Dict[str, Any]] = []

        for label in labels:
            scenario_id = label["scenario_id"]
            expected = label["expected_decision"]
            pred = pred_by_scenario.get(scenario_id)
            total += 1

            if pred is None:
                missing_predictions += 1
                rows.append(
                    {
                        "scenario_id": scenario_id,
                        "release_id": label["release_id"],
                        "expected_decision": expected,
                        "predicted_decision": None,
                        "match": False,
                        "note": "missing prediction",
                    }
                )
                continue

            predicted = str(pred.get("decision", "")).strip().upper()
            is_match = predicted == expected
            if is_match:
                matched += 1
            else:
                if predicted == "GO" and expected == "HOLD":
                    false_go += 1
                elif predicted == "HOLD" and expected == "GO":
                    false_hold += 1

            rows.append(
                {
                    "scenario_id": scenario_id,
                    "release_id": label["release_id"],
                    "expected_decision": expected,
                    "predicted_decision": predicted,
                    "match": is_match,
                }
            )

        evaluated = total - missing_predictions
        accuracy = (matched / total) if total else 0.0
        false_go_rate = (false_go / evaluated) if evaluated else 0.0
        false_hold_rate = (false_hold / evaluated) if evaluated else 0.0

        return {
            "dataset_root": self.config.dataset_root,
            "labels_path": str(labels_path),
            "total_scenarios": total,
            "evaluated_scenarios": evaluated,
            "missing_predictions": missing_predictions,
            "matched": matched,
            "accuracy": round(accuracy, 4),
            "false_go": false_go,
            "false_hold": false_hold,
            "false_go_rate": round(false_go_rate, 4),
            "false_hold_rate": round(false_hold_rate, 4),
            "rows": rows,
        }

    @staticmethod
    def _read_labels(path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            raise Agent5LCError("Labels file not found: {0}".format(path))

        rows: List[Dict[str, str]] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise Agent5LCError("Labels CSV has no header row: {0}".format(path))

            required = {"scenario_id", "release_id", "expected_decision"}
            missing = required - set(reader.fieldnames)
            if missing:
                raise Agent5LCError(
                    "Labels CSV missing required columns: {0}".format(
                        ", ".join(sorted(missing))
                    )
                )

            for row in reader:
                expected = str(row.get("expected_decision", "")).strip().upper()
                if expected not in {"GO", "HOLD"}:
                    continue
                rows.append(
                    {
                        "scenario_id": str(row.get("scenario_id", "")).strip(),
                        "release_id": str(row.get("release_id", "")).strip(),
                        "expected_decision": expected,
                    }
                )
        return rows


__all__ = [
    "Agent5LCError",
    "Agent5State",
    "LCPipelineConfig",
    "build_step_functions",
    "build_langchain_pipeline",
    "LangChainAgent5Pipeline",
]
