"""
LangChain-compatible state container for Agent 4 pipeline.

Design goals:
- Keep state as plain dictionaries for seamless LangChain Runnable usage.
- Keep schema explicit and typed for future LangGraph migration.
- Preserve current Agent 4 behavior and contracts (v1/v2 datasets, deterministic gates).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, TypedDict


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Agent4State(TypedDict, total=False):
    # Identity / routing
    scenario_id: str
    dataset_root: str
    release_id: Optional[str]
    environment: str
    policy_version: str

    # Execution controls
    use_llm_summary: bool
    llm_enabled: bool

    # Pipeline artifacts
    raw_bundle: Any
    normalized_bundle: Any
    rule_findings: Any
    output: Dict[str, Any]

    # Explanation-side hints
    non_blocking_warning: bool
    evidence_conflict: bool
    evidence_incomplete: bool

    # Optional LLM intermediate artifacts
    llm_prompt: str
    llm_response: str

    # Validation / evaluation
    schema_valid: bool
    schema_errors: List[str]
    expected_decision: Optional[str]
    evaluation: Dict[str, Any]

    # Diagnostics / observability
    trace: List[str]
    errors: List[str]
    metadata: Dict[str, Any]
    started_at_utc: str
    finished_at_utc: str


def new_agent4_state(
    *,
    scenario_id: str,
    dataset_root: str = "synthetic_data/v1",
    release_id: Optional[str] = None,
    use_llm_summary: bool = True,
    policy_version: str = "phase4-policy-v1",
    metadata: Optional[Dict[str, Any]] = None,
) -> Agent4State:
    """
    Create a clean Agent4State instance suitable for LangChain Runnable pipelines.
    """
    return Agent4State(
        scenario_id=scenario_id,
        dataset_root=dataset_root,
        release_id=release_id,
        environment="DEV",
        policy_version=policy_version,
        use_llm_summary=use_llm_summary,
        llm_enabled=use_llm_summary,
        trace=[],
        errors=[],
        schema_valid=False,
        schema_errors=[],
        metadata=dict(metadata or {}),
        started_at_utc=_utc_now_iso(),
    )


def clone_state(state: Agent4State) -> Agent4State:
    """
    Defensive shallow clone of state for functional-style pipeline steps.
    """
    cloned: Agent4State = Agent4State(**state)
    if "trace" in cloned:
        cloned["trace"] = list(cloned["trace"])
    if "errors" in cloned:
        cloned["errors"] = list(cloned["errors"])
    if "schema_errors" in cloned:
        cloned["schema_errors"] = list(cloned["schema_errors"])
    if "metadata" in cloned:
        cloned["metadata"] = dict(cloned["metadata"])
    if "output" in cloned and isinstance(cloned["output"], dict):
        cloned["output"] = dict(cloned["output"])
    if "evaluation" in cloned and isinstance(cloned["evaluation"], dict):
        cloned["evaluation"] = dict(cloned["evaluation"])
    return cloned


def merge_state(state: Agent4State, **updates: Any) -> Agent4State:
    """
    Return a new state with shallow updates.
    """
    merged = clone_state(state)
    for k, v in updates.items():
        merged[k] = v
    return merged


def push_trace(
    state: Agent4State, step: str, detail: Optional[str] = None
) -> Agent4State:
    """
    Append a normalized trace event.
    """
    updated = clone_state(state)
    trace = updated.setdefault("trace", [])
    item = step.strip()
    if detail:
        item = f"{item}: {detail.strip()}"
    trace.append(item)
    return updated


def push_error(state: Agent4State, message: str) -> Agent4State:
    """
    Append a non-fatal error message and trace marker.
    """
    updated = clone_state(state)
    updated.setdefault("errors", []).append(message.strip())
    updated.setdefault("trace", []).append(f"error: {message.strip()}")
    return updated


def finalize_state(
    state: Agent4State,
    *,
    output: Optional[Dict[str, Any]] = None,
    schema_valid: Optional[bool] = None,
    schema_errors: Optional[Sequence[str]] = None,
    evaluation: Optional[Dict[str, Any]] = None,
) -> Agent4State:
    """
    Mark state as completed and optionally attach final artifacts.
    """
    updated = clone_state(state)
    if output is not None:
        updated["output"] = dict(output)
    if schema_valid is not None:
        updated["schema_valid"] = bool(schema_valid)
    if schema_errors is not None:
        updated["schema_errors"] = [str(x) for x in schema_errors]
    if evaluation is not None:
        updated["evaluation"] = dict(evaluation)
    updated["finished_at_utc"] = _utc_now_iso()
    updated.setdefault("trace", []).append("completed")
    return updated


def require_state_keys(state: Agent4State, keys: Sequence[str]) -> List[str]:
    """
    Return missing or empty keys. Useful for Runnable precondition checks.
    """
    missing: List[str] = []
    for key in keys:
        if key not in state:
            missing.append(key)
            continue
        value = state.get(key)
        if value is None:
            missing.append(key)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(key)
    return missing


def as_langchain_input(state: Agent4State) -> Dict[str, Any]:
    """
    Convert to plain dict for Runnable.invoke(...) input.
    """
    return dict(state)


def from_langchain_output(payload: Dict[str, Any]) -> Agent4State:
    """
    Convert Runnable output payload back into Agent4State.
    """
    return Agent4State(**payload)
