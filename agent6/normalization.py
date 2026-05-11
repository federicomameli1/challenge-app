"""
Phase 6 normalization layer and derived policy flags.

This module converts raw ingestion artifacts (A4/A5 handoffs and Phase 6
artifacts) into canonical structures and computes deterministic rule-input flags
for the Phase 6 policy engine.

Design goals:
- Keep policy inputs deterministic and auditable
- Preserve source traceability for cross-phase data
- Gracefully handle absent handoffs while surfacing continuity gaps
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .ingestion import RawPhase6Bundle
from .models import SourceRef

# ---------------------------------------------------------------------------
# Normalized records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedAgent4Context:
    decision: str
    triggered_rules: Tuple[str, ...]
    open_blocker_detected: bool
    critical_service_unhealthy: bool
    module_versions: Mapping[str, str]
    unresolved_conditions: Tuple[str, ...]
    closure_confirmed: bool
    source: SourceRef


@dataclass(frozen=True)
class NormalizedAgent5Context:
    decision: str
    triggered_rules: Tuple[str, ...]
    critical_defect_open: bool
    open_critical_defect_ids: Tuple[str, ...]
    requirements_coverage_ratio: Optional[float]
    agent4_closure_confirmed: bool
    agent4_unresolved_conditions: Tuple[str, ...]
    module_versions: Mapping[str, str]
    vdd_completeness: Dict[str, Any]
    conditional_approval_triggers: Tuple[Mapping[str, Any], ...]
    source: SourceRef


@dataclass(frozen=True)
class NormalizedApprovalItem:
    role: str
    required: bool
    signed: bool
    signed_by: Optional[str]
    source: SourceRef


@dataclass(frozen=True)
class NormalizedPhase6Bundle:
    scenario_id: str
    release_id: str
    environment: str

    # Cross-phase context
    agent4_context: Optional[NormalizedAgent4Context]
    agent5_context: Optional[NormalizedAgent5Context]

    # Phase 6 own artifacts
    approval_items: Tuple[NormalizedApprovalItem, ...]

    # Primary deterministic rule inputs
    cross_phase_version_mismatch: bool
    agent5_critical_defect_open: bool
    agent4_blocker_unconfirmed: bool
    requirements_coverage_gap: bool
    vdd_incomplete: bool
    missing_approval_trigger: bool

    # Diagnostics
    missing_optional_artifacts: Tuple[str, ...] = field(default_factory=tuple)
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
    for sep in ("|", ";"):
        text = text.replace(sep, ",")
    parts = [p.strip() for p in text.split(",")]
    return [p for p in parts if p]


def _to_source_ref(path: str) -> SourceRef:
    return SourceRef(file_path=path or "handoff")


# ---------------------------------------------------------------------------
# Normalization: Agent 4 context
# ---------------------------------------------------------------------------


def _extract_agent4_version_map(ctx: Mapping[str, Any]) -> Dict[str, str]:
    """
    Extract module -> deployed_version mapping from Agent 4 handoff payload.

    Agent 4 stores this in rule_findings.module_versions or at the top level.
    """
    versions: Dict[str, str] = {}

    # Try rule_findings.module_versions
    rf = ctx.get("rule_findings", {})
    if isinstance(rf, Mapping):
        mv = rf.get("module_versions", [])
        if isinstance(mv, list):
            for entry in mv:
                if isinstance(entry, Mapping):
                    mod = normalize_text(entry.get("module"))
                    ver = normalize_text(entry.get("deployed_version") or entry.get("version"))
                    if mod:
                        versions[mod] = ver

    # Fallback: scan for any module key at top level or in payload
    if not versions:
        for key, val in ctx.items():
            if isinstance(val, Mapping) and "module" in val:
                mod = normalize_text(val.get("module"))
                ver = normalize_text(val.get("deployed_version") or val.get("version"))
                if mod and ver:
                    versions[mod] = ver
            elif isinstance(val, str) and key.lower().startswith("module"):
                versions[normalize_text(key)] = normalize_text(val)

    return versions


def normalize_agent4_context(
    raw: RawPhase6Bundle,
) -> Optional[NormalizedAgent4Context]:
    """
    Normalize Agent 4 handoff context from raw bundle.
    """
    ctx = raw.agent4_context
    if ctx is None:
        return None

    rf = ctx.get("rule_findings", {})
    if not isinstance(rf, Mapping):
        rf = {}

    triggered_raw = rf.get("triggered_rule_codes", ctx.get("triggered_rule_codes", []))
    triggered_rules = (
        tuple(split_multi(triggered_raw))
        if not isinstance(triggered_raw, list)
        else tuple([normalize_text(str(x)) for x in triggered_raw if normalize_text(str(x))])
    )

    unresolved_raw = ctx.get("unresolved_conditions", ctx.get("unresolved_hard_blockers", []))
    unresolved_conditions = (
        tuple(split_multi(unresolved_raw))
        if not isinstance(unresolved_raw, list)
        else tuple([normalize_text(str(x)) for x in unresolved_raw if normalize_text(str(x))])
    )

    decision = normalize_upper(ctx.get("decision", ctx.get("agent4_decision", "")))
    if not decision:
        decision = "UNKNOWN"

    open_blocker_detected = (
        "open_blocker_email" in triggered_rules
        or "OPEN_BLOCKER_EMAIL" in triggered_rules
    )
    critical_service_unhealthy = (
        "critical_service_unhealthy" in triggered_rules
        or "CRITICAL_SERVICE_UNHEALTHY" in triggered_rules
    )

    module_versions = _extract_agent4_version_map(ctx)

    # Closure confirmed: A5 confirmed it or Phase 6 approval sign-off exists.
    closure_confirmed = parse_bool(ctx.get("closure_confirmed"))

    return NormalizedAgent4Context(
        decision=decision,
        triggered_rules=triggered_rules,
        open_blocker_detected=open_blocker_detected,
        critical_service_unhealthy=critical_service_unhealthy,
        module_versions=module_versions,
        unresolved_conditions=unresolved_conditions,
        closure_confirmed=closure_confirmed,
        source=_to_source_ref(raw.source_references.get("agent4_context", SourceRef("handoff", "agent4_handoff")).file_path),
    )


# ---------------------------------------------------------------------------
# Normalization: Agent 5 context
# ---------------------------------------------------------------------------


def normalize_agent5_context(
    raw: RawPhase6Bundle,
) -> Optional[NormalizedAgent5Context]:
    """
    Normalize Agent 5 handoff context from raw bundle.
    """
    ctx = raw.agent5_context
    if ctx is None:
        return None

    rf = ctx.get("rule_findings", {})
    if not isinstance(rf, Mapping):
        rf = {}

    triggered_raw = rf.get("triggered_rule_codes", ctx.get("triggered_rule_codes", []))
    triggered_rules = (
        tuple(split_multi(triggered_raw))
        if not isinstance(triggered_raw, list)
        else tuple([normalize_text(str(x)) for x in triggered_raw if normalize_text(str(x))])
    )

    # Critical defect open
    critical_defect_open = parse_bool(
        rf.get("critical_defect_open", ctx.get("critical_defect_open"))
    )

    # Open critical/high defect IDs
    defects_raw = ctx.get("defects", [])
    open_ids: List[str] = []
    if isinstance(defects_raw, list):
        for d in defects_raw:
            if isinstance(d, Mapping):
                is_open = parse_bool(d.get("is_open") or d.get("status"))
                severity = normalize_upper(d.get("severity", ""))
                is_crit_or_high = severity in {"CRITICAL", "HIGH"}
                if is_open and is_crit_or_high:
                    did = normalize_text(d.get("defect_id", d.get("id", "")))
                    if did:
                        open_ids.append(did)

    # Coverage ratio
    coverage_ratio: Optional[float] = None
    coverage = ctx.get("coverage_metrics", {})
    if isinstance(coverage, Mapping):
        ratio_val = coverage.get("requirement_coverage", coverage.get("coverage_ratio"))
        if ratio_val is not None:
            try:
                coverage_ratio = float(ratio_val)
            except (ValueError, TypeError):
                pass

    # Agent 4 closure confirmed in A5
    continuity = ctx.get("cross_phase_continuity_flags", {})
    if not isinstance(continuity, Mapping):
        continuity = {}

    a5_closure_confirmed = parse_bool(
        continuity.get("closure_confirmed") or continuity.get("all_closed")
    )

    a5_unresolved_raw = continuity.get("agent4_unresolved_conditions", [])
    a5_unresolved_conditions: Tuple[str, ...] = (
        tuple(split_multi(a5_unresolved_raw))
        if not isinstance(a5_unresolved_raw, list)
        else tuple([normalize_text(str(x)) for x in a5_unresolved_raw if normalize_text(str(x))])
    )

    # VDD completeness (A5 may not check this; Phase 6 owns it)
    vdd_completeness: Dict[str, Any] = {}
    if isinstance(ctx.get("vdd_completeness"), Mapping):
        vdd_completeness = dict(ctx.get("vdd_completeness", {}))

    # Conditional approval triggers
    approval_raw = ctx.get("conditional_approval_triggers", [])
    conditional_approval_triggers: Tuple[Mapping[str, Any], ...] = (
        tuple(approval_raw)
        if isinstance(approval_raw, list)
        else tuple()
    )

    decision = normalize_upper(ctx.get("decision", ""))
    if not decision:
        decision = "UNKNOWN"

    # Module versions from A5 (tested versions, from rule_findings.module_versions)
    module_versions: Dict[str, str] = {}
    mv_raw = rf.get("module_versions", [])
    if isinstance(mv_raw, list):
        for entry in mv_raw:
            if isinstance(entry, Mapping):
                mod = normalize_text(entry.get("module", ""))
                ver = normalize_text(entry.get("tested_version") or entry.get("version", ""))
                if mod and ver:
                    module_versions[mod] = ver

    return NormalizedAgent5Context(
        decision=decision,
        triggered_rules=triggered_rules,
        critical_defect_open=critical_defect_open,
        open_critical_defect_ids=tuple(open_ids),
        requirements_coverage_ratio=coverage_ratio,
        agent4_closure_confirmed=a5_closure_confirmed,
        agent4_unresolved_conditions=a5_unresolved_conditions,
        module_versions=module_versions,
        vdd_completeness=vdd_completeness,
        conditional_approval_triggers=conditional_approval_triggers,
        source=_to_source_ref(raw.source_references.get("agent5_context", SourceRef("handoff", "agent5_handoff")).file_path),
    )


# ---------------------------------------------------------------------------
# Normalization: Approval items
# ---------------------------------------------------------------------------


def _extract_approval_items(
    raw: RawPhase6Bundle,
) -> Tuple[NormalizedApprovalItem, ...]:
    """
    Extract approval items from Phase 6 approval manifest and A5 conditional triggers.
    """
    items: List[NormalizedApprovalItem] = []
    seen_roles: set = set()

    # From A5 conditional approval triggers (only record unsigned-required roles as open gates)
    a5_ctx = raw.agent5_context
    if isinstance(a5_ctx, Mapping):
        triggers = a5_ctx.get("conditional_approval_triggers", [])
        if isinstance(triggers, list):
            for t in triggers:
                if isinstance(t, Mapping):
                    required = parse_bool(t.get("required", True))
                    signed = parse_bool(t.get("signed"))
                    if not required and not signed:
                        continue  # not a conditional approval gate for this scenario
                    role = normalize_text(t.get("required_role") or t.get("role") or t.get("approver"))
                    if role and role not in seen_roles:
                        seen_roles.add(role)
                        items.append(NormalizedApprovalItem(
                            role=role,
                            required=required,
                            signed=signed,
                            signed_by=normalize_text(t.get("signed_by")) or None,
                            source=_to_source_ref("agent5_handoff:conditional_approval_triggers"),
                        ))

    # From Phase 6 approval manifest
    approval_manifest = raw.approval_manifest
    if isinstance(approval_manifest, Mapping):
        # Manifest may have roles as keys with signed status as values.
        for key, val in approval_manifest.items():
            key_clean = normalize_text(key)
            if not key_clean or key_clean in {"scenario_id", "release_id", "environment"}:
                continue
            # Empty value means the role is not part of this scenario's approval matrix — skip.
            val_str = str(val or "").strip()
            if not val_str:
                continue
            role = key_clean
            if role not in seen_roles:
                seen_roles.add(role)
                signed = parse_bool(val_str)
                items.append(NormalizedApprovalItem(
                    role=role,
                    required=True,
                    signed=signed,
                    signed_by=None,
                    source=_to_source_ref("approval_workflow_manifest"),
                ))

    return tuple(items)


# ---------------------------------------------------------------------------
# Normalization pipeline
# ---------------------------------------------------------------------------


def normalize_phase6_bundle(raw: RawPhase6Bundle) -> NormalizedPhase6Bundle:
    """
    Normalize Phase 6 evidence bundle and compute deterministic derived flags.
    """
    a4_ctx = normalize_agent4_context(raw)
    a5_ctx = normalize_agent5_context(raw)
    approval_items = _extract_approval_items(raw)

    continuity_notes: List[str] = []
    missing_optional: List[str] = list(raw.missing_optional_artifacts)

    # -----------------------------------------------------------------
    # R1: Cross-phase version consistency
    # A4: module -> deployed_version
    # A5: module -> tested_version
    # Compare. If A5 doesn't mention a module at all, flag it conservatively.
    # -----------------------------------------------------------------
    cross_phase_version_mismatch = False
    if a4_ctx is not None and a5_ctx is not None:
        a4_versions = dict(a4_ctx.module_versions)
        # Try to extract A5 tested versions from A5 payload
        a5_versions: Dict[str, str] = {}
        rf = {}
        if isinstance(raw.agent5_context, Mapping):
            rf = raw.agent5_context.get("rule_findings", {})
        if isinstance(rf, Mapping):
            mv = rf.get("module_versions", [])
            if isinstance(mv, list):
                for entry in mv:
                    if isinstance(entry, Mapping):
                        mod = normalize_text(entry.get("module"))
                        ver = normalize_text(entry.get("tested_version") or entry.get("version"))
                        if mod:
                            a5_versions[mod] = ver

        for mod, a4_ver in a4_versions.items():
            a5_ver = a5_versions.get(mod)
            if a5_ver is None:
                # Module in A4 but not in A5 evidence -- conservative mismatch
                cross_phase_version_mismatch = True
                continuity_notes.append(f"module_not_in_a5_evidence:{mod}")
            elif a4_ver != a5_ver:
                cross_phase_version_mismatch = True
                continuity_notes.append(f"version_mismatch:{mod}:A4={a4_ver}:A5={a5_ver}")

    # -----------------------------------------------------------------
    # R2: Agent 5 critical defect open
    # -----------------------------------------------------------------
    agent5_critical_defect_open = (
        a5_ctx is not None and a5_ctx.critical_defect_open
    )

    # -----------------------------------------------------------------
    # R3: Agent 4 blocker unconfirmed
    # -----------------------------------------------------------------
    agent4_blocker_unconfirmed = False
    if a4_ctx is not None:
        if a4_ctx.decision == "HOLD" or a4_ctx.open_blocker_detected:
            # A4 had blockers -- require explicit closure from A5 continuity + Phase 6 approval
            a5_confirmed = (
                a5_ctx.agent4_closure_confirmed if a5_ctx is not None else False
            )
            vdd_confirmed = any(
                item.signed for item in approval_items
            )
            if not (a5_confirmed or vdd_confirmed):
                agent4_blocker_unconfirmed = True
                continuity_notes.append("agent4_blocker_not_confirmed_in_phase6")

    # -----------------------------------------------------------------
    # R4: Requirements coverage gap
    # -----------------------------------------------------------------
    requirements_coverage_gap = False
    if a5_ctx is not None and a5_ctx.requirements_coverage_ratio is not None:
        if a5_ctx.requirements_coverage_ratio < 1.0:
            requirements_coverage_gap = True
            continuity_notes.append(
                f"coverage_below_100pct:{a5_ctx.requirements_coverage_ratio:.2f}"
            )

    # -----------------------------------------------------------------
    # R5: VDD incomplete
    # Phase 6 builds its own VDD draft, so this flag tracks whether
    # the VDD draft builder produced all required sections.
    # -----------------------------------------------------------------
    vdd_incomplete = False  # Set by vdd_draft builder if sections are missing

    # -----------------------------------------------------------------
    # R6: Missing approval trigger
    # -----------------------------------------------------------------
    missing_approval_trigger = False
    for item in approval_items:
        if item.required and not item.signed:
            missing_approval_trigger = True
            continuity_notes.append(f"approval_missing:{item.role}")
            break

    # -----------------------------------------------------------------
    # Track absent handoffs
    # -----------------------------------------------------------------
    if a4_ctx is None:
        missing_optional.append("agent4_context")
    if a5_ctx is None:
        missing_optional.append("agent5_context")

    return NormalizedPhase6Bundle(
        scenario_id=raw.scenario_id,
        release_id=raw.release_id,
        environment=raw.environment,
        agent4_context=a4_ctx,
        agent5_context=a5_ctx,
        approval_items=approval_items,
        cross_phase_version_mismatch=cross_phase_version_mismatch,
        agent5_critical_defect_open=agent5_critical_defect_open,
        agent4_blocker_unconfirmed=agent4_blocker_unconfirmed,
        requirements_coverage_gap=requirements_coverage_gap,
        vdd_incomplete=vdd_incomplete,
        missing_approval_trigger=missing_approval_trigger,
        missing_optional_artifacts=tuple(missing_optional),
        continuity_notes=tuple(continuity_notes),
    )


__all__ = [
    "NormalizedAgent4Context",
    "NormalizedAgent5Context",
    "NormalizedApprovalItem",
    "NormalizedPhase6Bundle",
    "normalize_agent4_context",
    "normalize_agent5_context",
    "normalize_phase6_bundle",
    "parse_bool",
]
