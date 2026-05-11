"""
LangChain-compatible state container for Agent 6 pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Agent6State(TypedDict, total=False):
    scenario_id: str
    dataset_root: str
    release_id: Optional[str]
    environment: str
    policy_version: str
    agent4_handoff: Optional[Dict[str, Any]]
    agent5_handoff: Optional[Dict[str, Any]]
    use_llm_summary: bool
    raw: Any
    normalized: Any
    rule_findings: Any
    output: Dict[str, Any]
    evidence_conflict: bool
    evidence_incomplete: bool
    missing_artifacts: List[str]
    cross_phase_context: Dict[str, Any]
    llm_prompt: str
    llm_response: str
    schema_valid: bool
    schema_errors: List[str]
    expected_decision: Optional[str]
    evaluation: Dict[str, Any]
    trace: List[str]
    errors: List[str]
    metadata: Dict[str, Any]
    started_at_utc: str
    finished_at_utc: str


def new_agent6_state(
    scenario_id: str,
    release_id: Optional[str] = None,
    dataset_root: str = "synthetic_data/phase6/v1",
) -> Agent6State:
    return Agent6State(
        scenario_id=scenario_id,
        release_id=release_id,
        dataset_root=dataset_root,
        environment="RELEASE",
        policy_version="phase6-policy-v1",
        agent4_handoff=None,
        agent5_handoff=None,
        use_llm_summary=False,
        trace=[],
        errors=[],
        metadata={},
        started_at_utc=_utc_now_iso(),
    )


def clone_state(state: Agent6State) -> Agent6State:
    out = dict(state)
    out["trace"] = list(state.get("trace", []))
    out["errors"] = list(state.get("errors", []))
    out["metadata"] = dict(state.get("metadata", {}))
    return out


def merge_state(base: Agent6State, updates: Dict[str, Any]) -> Agent6State:
    merged = clone_state(base)
    merged.update(updates)
    return merged


def push_trace(state: Agent6State, message: str) -> Agent6State:
    out = clone_state(state)
    out["trace"] = list(state.get("trace", [])) + [message]
    return out


def push_error(state: Agent6State, error: str) -> Agent6State:
    out = clone_state(state)
    out["errors"] = list(state.get("errors", [])) + [error]
    return out


def finalize_state(state: Agent6State) -> Agent6State:
    out = clone_state(state)
    out["finished_at_utc"] = _utc_now_iso()
    return out


__all__ = [
    "Agent6State",
    "new_agent6_state",
    "clone_state",
    "merge_state",
    "push_trace",
    "push_error",
    "finalize_state",
]
