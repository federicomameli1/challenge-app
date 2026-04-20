"""
LangChain-compatible state container for Agent 5 pipeline.

Design goals:
- Keep state as plain dictionaries for seamless Runnable usage.
- Keep schema explicit and typed for future LangGraph migration.
- Preserve deterministic policy authority while allowing optional explanation layers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, TypedDict


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Agent5State(TypedDict, total=False):
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
    evidence_conflict: bool
    evidence_incomplete: bool
    missing_artifacts: List[str]
    continuity_flags: Dict[str, Any]

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


def new_agent5_state(
    *,
    scenario_id: str,
    dataset_root: str = "synthetic_data/phase5/v1",
    release_id: Optional[str] = None,
    use_llm_summary: bool = True,
    policy_version: str = "phase5-policy-v1",
    metadata: Optional[Dict[str, Any]] = None,
) -> Agent5State:
    """
    Create a clean Agent5State instance suitable for LangChain Runnable pipelines.
    """
    return Agent5State(
        scenario_id=scenario_id,
        dataset_root=dataset_root,
        release_id=release_id,
        environment="TEST",
        policy_version=policy_version,
        use_llm_summary=use_llm_summary,
        llm_enabled=use_llm_summary,
        evidence_conflict=False,
        evidence_incomplete=False,
        missing_artifacts=[],
        continuity_flags={},
        trace=[],
        errors=[],
        schema_valid=False,
        schema_errors=[],
        metadata=dict(metadata or {}),
        started_at_utc=_utc_now_iso(),
    )


def clone_state(state: Agent5State) -> Agent5State:
    """
    Defensive shallow clone of state for functional-style pipeline steps.
    """
    cloned: Agent5State = Agent5State(**state)

    if "trace" in cloned:
        cloned["trace"] = list(cloned["trace"])
    if "errors" in cloned:
        cloned["errors"] = list(cloned["errors"])
    if "schema_errors" in cloned:
        cloned["schema_errors"] = list(cloned["schema_errors"])
    if "missing_artifacts" in cloned:
        cloned["missing_artifacts"] = list(cloned["missing_artifacts"])
    if "metadata" in cloned:
        cloned["metadata"] = dict(cloned["metadata"])
    if "continuity_flags" in cloned:
        cloned["continuity_flags"] = dict(cloned["continuity_flags"])
    if "output" in cloned and isinstance(cloned["output"], dict):
        cloned["output"] = dict(cloned["output"])
    if "evaluation" in cloned and isinstance(cloned["evaluation"], dict):
        cloned["evaluation"] = dict(cloned["evaluation"])

    return cloned


def merge_state(state: Agent5State, **updates: Any) -> Agent5State:
    """
    Return a new state with shallow updates.
    """
    merged = clone_state(state)
    for k, v in updates.items():
        merged[k] = v
    return merged


def push_trace(
    state: Agent5State, step: str, detail: Optional[str] = None
) -> Agent5State:
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


def push_error(state: Agent5State, message: str) -> Agent5State:
    """
    Append a non-fatal error message and trace marker.
    """
    updated = clone_state(state)
    updated.setdefault("errors", []).append(message.strip())
    updated.setdefault("trace", []).append(f"error: {message.strip()}")
    return updated


def finalize_state(
    state: Agent5State,
    *,
    output: Optional[Dict[str, Any]] = None,
    schema_valid: Optional[bool] = None,
    schema_errors: Optional[Sequence[str]] = None,
    evaluation: Optional[Dict[str, Any]] = None,
    continuity_flags: Optional[Dict[str, Any]] = None,
    missing_artifacts: Optional[Sequence[str]] = None,
) -> Agent5State:
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
    if continuity_flags is not None:
        updated["continuity_flags"] = dict(continuity_flags)
    if missing_artifacts is not None:
        updated["missing_artifacts"] = [str(x) for x in missing_artifacts]

    updated["finished_at_utc"] = _utc_now_iso()
    updated.setdefault("trace", []).append("completed")
    return updated


def require_state_keys(state: Agent5State, keys: Sequence[str]) -> List[str]:
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


def as_langchain_input(state: Agent5State) -> Dict[str, Any]:
    """
    Convert to plain dict for Runnable.invoke(...) input.
    """
    return dict(state)


def from_langchain_output(payload: Dict[str, Any]) -> Agent5State:
    """
    Convert Runnable output payload back into Agent5State.
    """
    return Agent5State(**payload)
