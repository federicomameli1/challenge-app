"""
Phase 5 normalization layer and derived policy flags.

This module converts raw ingestion artifacts into canonical structures and
computes deterministic rule-input flags for the Phase 5 policy engine.

Design goals:
- Keep policy inputs deterministic and auditable
- Preserve source traceability for each normalized artifact
- Gracefully handle partial inputs while surfacing evidence incompleteness
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .ingestion import RawInputBundle
from .models import SourceRef

# ---------------------------------------------------------------------------
# Normalized records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedRequirement:
    requirement_id: str
    description: str
    priority: str
    mandatory: bool
    source: SourceRef


@dataclass(frozen=True)
class NormalizedTestCase:
    test_case_id: str
    mapped_requirements: Tuple[str, ...]
    criticality: str
    source: SourceRef


@dataclass(frozen=True)
class NormalizedTraceLink:
    requirement_id: str
    test_case_id: str
    source: SourceRef


@dataclass(frozen=True)
class NormalizedExecution:
    test_case_id: str
    status: str
    executed: bool
    passed: bool
    failed: bool
    blocked: bool
    retest_required: bool
    retest_completed: bool
    source: SourceRef


@dataclass(frozen=True)
class NormalizedDefect:
    defect_id: str
    severity: str
    status: str
    is_open: bool
    is_critical_or_high: bool
    source: SourceRef


@dataclass(frozen=True)
class NormalizedAgent4Context:
    decision: str
    triggered_rules: Tuple[str, ...]
    unresolved_conditions: Tuple[str, ...]
    closure_confirmed: bool
    source: SourceRef


@dataclass(frozen=True)
class NormalizedEvidenceBundle:
    scenario_id: str
    release_id: str
    environment: str

    requirements: Tuple[NormalizedRequirement, ...]
    test_cases: Tuple[NormalizedTestCase, ...]
    traceability_links: Tuple[NormalizedTraceLink, ...]
    executions: Tuple[NormalizedExecution, ...]
    defects: Tuple[NormalizedDefect, ...]
    agent4_context: Optional[NormalizedAgent4Context]

    # Primary deterministic rule inputs
    mandatory_requirement_uncovered: bool
    mandatory_requirement_failed_or_blocked: bool
    critical_defect_open: bool
    test_evidence_incomplete: bool
    conditional_retest_unmet: bool
    agent4_unresolved_hard_blocker_unclosed: bool

    # Diagnostics
    missing_optional_artifacts: Tuple[str, ...] = field(default_factory=tuple)
    incompleteness_reasons: Tuple[str, ...] = field(default_factory=tuple)
    continuity_notes: Tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on", "pass", "passed", "closed", "done"}


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_upper(value: Any) -> str:
    return normalize_text(value).upper()


def split_multi(value: Any) -> List[str]:
    text = normalize_text(value)
    if not text:
        return []
    # Support common list separators in CSV/doc extraction.
    for sep in ("|", ";"):
        text = text.replace(sep, ",")
    parts = [p.strip() for p in text.split(",")]
    return [p for p in parts if p]


def normalize_execution_status(value: Any) -> str:
    raw = normalize_text(value).lower()
    if raw in {"pass", "passed", "ok", "success"}:
        return "PASS"
    if raw in {"fail", "failed", "failure", "error"}:
        return "FAIL"
    if raw in {"block", "blocked"}:
        return "BLOCKED"
    if raw in {"not-run", "not run", "not_executed", "pending"}:
        return "NOT_RUN"
    if raw in {"conditional_unmet", "retest_unmet"}:
        return "CONDITIONAL_UNMET"
    return raw.upper() if raw else "UNKNOWN"


def normalize_defect_status(value: Any) -> str:
    raw = normalize_text(value).lower()
    if raw in {"open", "new", "reopened", "in progress", "todo", "pending"}:
        return "OPEN"
    if raw in {"closed", "resolved", "done", "fixed"}:
        return "CLOSED"
    return raw.upper() if raw else "UNKNOWN"


def normalize_severity(value: Any) -> str:
    raw = normalize_text(value).lower()
    if raw in {"critical", "sev1", "s1", "blocker"}:
        return "CRITICAL"
    if raw in {"high", "sev2", "s2"}:
        return "HIGH"
    if raw in {"medium", "med", "sev3", "s3"}:
        return "MEDIUM"
    if raw in {"low", "sev4", "s4"}:
        return "LOW"
    return raw.upper() if raw else "UNKNOWN"


def _to_source_ref(path: str) -> SourceRef:
    return SourceRef(file_path=path or "unknown")


def _get_source_path(raw: RawInputBundle, key: str, fallback: str) -> str:
    ref = raw.source_references.get(key)
    if ref is None:
        return fallback
    return ref.path


def _first_non_empty(
    row: Dict[str, str], keys: Sequence[str], default: str = ""
) -> str:
    for k in keys:
        val = normalize_text(row.get(k))
        if val:
            return val
    return default


def _email_indicates_agent4_closure(email_text: str) -> bool:
    low = (email_text or "").lower()
    if not low.strip():
        return False
    # Conservative closure cues; do not over-infer.
    positive = any(
        marker in low
        for marker in (
            "no blocking issues remain",
            "ready for test promotion",
            "approve",
            "approved",
            "proceed with",
            "all re-tests pass",
            "all retests pass",
        )
    )
    negative = any(
        marker in low
        for marker in (
            "still blocked",
            "unresolved",
            "known limitation",
            "cannot proceed",
            "do not proceed",
        )
    )
    return positive and not negative


# ---------------------------------------------------------------------------
# Normalization pipeline
# ---------------------------------------------------------------------------


def normalize_evidence_bundle(raw: RawInputBundle) -> NormalizedEvidenceBundle:
    """
    Normalize all raw Phase 5 evidence and compute deterministic derived flags.
    """
    req_source = _to_source_ref(
        _get_source_path(raw, "requirements", "requirements_master.csv")
    )
    tc_source = _to_source_ref(
        _get_source_path(raw, "test_cases", "test_cases_master.csv")
    )
    tr_source = _to_source_ref(
        _get_source_path(raw, "traceability_matrix", "traceability_matrix.csv")
    )
    ex_source = _to_source_ref(
        _get_source_path(raw, "test_execution_results", "test_execution_results.csv")
    )
    df_source = _to_source_ref(
        _get_source_path(raw, "defect_register", "defect_register.csv")
    )
    a4_source = _to_source_ref(
        _get_source_path(raw, "agent4_context", "missing:agent4_context")
    )

    # Requirements
    requirements: List[NormalizedRequirement] = []
    for row in raw.requirements:
        req_id = _first_non_empty(row, ("requirement_id", "req_id", "id"))
        if not req_id:
            continue
        requirements.append(
            NormalizedRequirement(
                requirement_id=req_id,
                description=_first_non_empty(row, ("description", "requirement_text")),
                priority=normalize_upper(row.get("priority", "MEDIUM")) or "MEDIUM",
                mandatory=parse_bool(
                    _first_non_empty(
                        row,
                        (
                            "mandatory_for_phase5",
                            "mandatory",
                            "mandatory_for_phase4",
                        ),
                        "true",
                    )
                ),
                source=req_source,
            )
        )

    # Test cases
    test_cases: List[NormalizedTestCase] = []
    for row in raw.test_cases:
        tc_id = _first_non_empty(row, ("test_case_id", "tc_id", "id"))
        if not tc_id:
            continue
        mapped = split_multi(
            _first_non_empty(
                row,
                ("mapped_requirement_ids", "requirement_ids", "requirement_id"),
            )
        )
        test_cases.append(
            NormalizedTestCase(
                test_case_id=tc_id,
                mapped_requirements=tuple(mapped),
                criticality=normalize_upper(row.get("criticality", "MEDIUM"))
                or "MEDIUM",
                source=tc_source,
            )
        )

    # Traceability
    traceability_links: List[NormalizedTraceLink] = []
    for row in raw.traceability_matrix:
        req_id = _first_non_empty(row, ("requirement_id", "req_id"))
        tc_id = _first_non_empty(row, ("test_case_id", "tc_id"))
        if not req_id or not tc_id:
            continue
        traceability_links.append(
            NormalizedTraceLink(
                requirement_id=req_id,
                test_case_id=tc_id,
                source=tr_source,
            )
        )

    # Executions
    executions: List[NormalizedExecution] = []
    for row in raw.test_execution_results:
        tc_id = _first_non_empty(row, ("test_case_id", "tc_id"))
        if not tc_id:
            continue

        status = normalize_execution_status(
            _first_non_empty(row, ("status", "result", "outcome"), "UNKNOWN")
        )
        explicit_executed = row.get("executed")
        executed = (
            parse_bool(explicit_executed)
            if explicit_executed is not None and str(explicit_executed).strip() != ""
            else status in {"PASS", "FAIL", "BLOCKED", "CONDITIONAL_UNMET"}
        )

        passed = status == "PASS"
        failed = status == "FAIL"
        blocked = status == "BLOCKED"

        retest_required = (
            parse_bool(
                _first_non_empty(
                    row,
                    (
                        "retest_required",
                        "conditional_retest_required",
                        "compliance_retest_required",
                    ),
                    "false",
                )
            )
            or status == "CONDITIONAL_UNMET"
        )

        retest_completed = (
            parse_bool(
                _first_non_empty(
                    row,
                    (
                        "retest_completed",
                        "conditional_retest_completed",
                        "compliance_met",
                    ),
                    "false",
                )
            )
            or passed
        )

        executions.append(
            NormalizedExecution(
                test_case_id=tc_id,
                status=status,
                executed=executed,
                passed=passed,
                failed=failed,
                blocked=blocked,
                retest_required=retest_required,
                retest_completed=retest_completed,
                source=ex_source,
            )
        )

    # Defects
    defects: List[NormalizedDefect] = []
    for row in raw.defect_register:
        defect_id = _first_non_empty(row, ("defect_id", "ticket_id", "id"))
        if not defect_id:
            continue
        sev = normalize_severity(
            _first_non_empty(row, ("severity", "priority"), "UNKNOWN")
        )
        st = normalize_defect_status(
            _first_non_empty(row, ("status", "state"), "UNKNOWN")
        )
        is_open = st == "OPEN"
        defects.append(
            NormalizedDefect(
                defect_id=defect_id,
                severity=sev,
                status=st,
                is_open=is_open,
                is_critical_or_high=sev in {"CRITICAL", "HIGH"},
                source=df_source,
            )
        )

    # Agent 4 context
    agent4_context: Optional[NormalizedAgent4Context] = None
    if isinstance(raw.agent4_context, dict):
        ctx = raw.agent4_context
        decision = normalize_upper(ctx.get("agent4_decision", ctx.get("decision", "")))
        trig = ctx.get("agent4_triggered_rules", ctx.get("triggered_rules", []))
        unresolved = ctx.get(
            "unresolved_conditions",
            ctx.get("unresolved_hard_blockers", []),
        )

        triggered_rules = (
            tuple(split_multi(trig))
            if not isinstance(trig, list)
            else tuple([normalize_text(x) for x in trig if normalize_text(x)])
        )
        unresolved_conditions = (
            tuple(split_multi(unresolved))
            if not isinstance(unresolved, list)
            else tuple([normalize_text(x) for x in unresolved if normalize_text(x)])
        )

        closure_confirmed = parse_bool(
            ctx.get("closure_confirmed")
            or ctx.get("all_closed")
            or ctx.get("phase5_closure_evidence")
            or False
        )
        if not closure_confirmed:
            closure_confirmed = _email_indicates_agent4_closure(
                raw.test_analysis_email_thread or ""
            )

        # If A4 was HOLD and unresolved list absent, treat triggered rules as unresolved continuity.
        if decision == "HOLD" and not unresolved_conditions and triggered_rules:
            unresolved_conditions = triggered_rules

        agent4_context = NormalizedAgent4Context(
            decision=decision or "UNKNOWN",
            triggered_rules=triggered_rules,
            unresolved_conditions=unresolved_conditions,
            closure_confirmed=closure_confirmed,
            source=a4_source,
        )

    # ---------------------------------------------------------------------
    # Derived deterministic flags
    # ---------------------------------------------------------------------

    trace_by_req: Dict[str, set] = {}
    for link in traceability_links:
        trace_by_req.setdefault(link.requirement_id, set()).add(link.test_case_id)

    # Also include direct mappings from test case catalog.
    for tc in test_cases:
        for req_id in tc.mapped_requirements:
            trace_by_req.setdefault(req_id, set()).add(tc.test_case_id)

    exec_by_tc: Dict[str, List[NormalizedExecution]] = {}
    for ex in executions:
        exec_by_tc.setdefault(ex.test_case_id, []).append(ex)

    mandatory_requirements = [r for r in requirements if r.mandatory]

    mandatory_requirement_uncovered = False
    mandatory_requirement_failed_or_blocked = False

    for req in mandatory_requirements:
        mapped_tcs = trace_by_req.get(req.requirement_id, set())
        if not mapped_tcs:
            mandatory_requirement_uncovered = True
            continue

        mapped_execs: List[NormalizedExecution] = []
        for tc_id in mapped_tcs:
            mapped_execs.extend(exec_by_tc.get(tc_id, []))

        executed_any = any(ex.executed for ex in mapped_execs)
        if not executed_any:
            mandatory_requirement_uncovered = True

        if any((ex.failed or ex.blocked) for ex in mapped_execs):
            mandatory_requirement_failed_or_blocked = True

    critical_defect_open = any(d.is_open and d.is_critical_or_high for d in defects)

    conditional_retest_unmet = any(
        ex.retest_required and not ex.retest_completed for ex in executions
    ) or any(ex.status == "CONDITIONAL_UNMET" for ex in executions)

    incompleteness_reasons: List[str] = []
    if not requirements:
        incompleteness_reasons.append("requirements_missing_or_empty")
    if not test_cases:
        incompleteness_reasons.append("test_cases_missing_or_empty")
    if not traceability_links:
        incompleteness_reasons.append("traceability_missing_or_empty")
    if not executions:
        incompleteness_reasons.append("test_execution_results_missing_or_empty")
    if not defects:
        incompleteness_reasons.append("defect_register_missing_or_empty")
    if mandatory_requirements and mandatory_requirement_uncovered:
        incompleteness_reasons.append("mandatory_scope_not_fully_traceable_or_executed")

    test_evidence_incomplete = len(incompleteness_reasons) > 0

    continuity_notes: List[str] = []
    agent4_unresolved_hard_blocker_unclosed = False
    if agent4_context is not None:
        if agent4_context.decision == "HOLD" and agent4_context.unresolved_conditions:
            if not agent4_context.closure_confirmed:
                agent4_unresolved_hard_blocker_unclosed = True
                continuity_notes.append(
                    "agent4_hold_unresolved_conditions_not_explicitly_closed"
                )
            else:
                continuity_notes.append("agent4_unresolved_conditions_closed_in_phase5")
        elif agent4_context.decision == "HOLD" and not agent4_context.closure_confirmed:
            # Conservative fallback when HOLD exists but unresolved fields are sparse.
            if agent4_context.triggered_rules:
                agent4_unresolved_hard_blocker_unclosed = True
                continuity_notes.append(
                    "agent4_hold_triggered_rules_present_without_explicit_closure"
                )

    return NormalizedEvidenceBundle(
        scenario_id=raw.scenario_id,
        release_id=raw.release_id,
        environment=raw.environment,
        requirements=tuple(requirements),
        test_cases=tuple(test_cases),
        traceability_links=tuple(traceability_links),
        executions=tuple(executions),
        defects=tuple(defects),
        agent4_context=agent4_context,
        mandatory_requirement_uncovered=mandatory_requirement_uncovered,
        mandatory_requirement_failed_or_blocked=mandatory_requirement_failed_or_blocked,
        critical_defect_open=critical_defect_open,
        test_evidence_incomplete=test_evidence_incomplete,
        conditional_retest_unmet=conditional_retest_unmet,
        agent4_unresolved_hard_blocker_unclosed=agent4_unresolved_hard_blocker_unclosed,
        missing_optional_artifacts=tuple(raw.missing_optional_artifacts),
        incompleteness_reasons=tuple(incompleteness_reasons),
        continuity_notes=tuple(continuity_notes),
    )


__all__ = [
    "NormalizedRequirement",
    "NormalizedTestCase",
    "NormalizedTraceLink",
    "NormalizedExecution",
    "NormalizedDefect",
    "NormalizedAgent4Context",
    "NormalizedEvidenceBundle",
    "parse_bool",
    "normalize_evidence_bundle",
]
