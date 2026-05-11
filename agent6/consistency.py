"""
Cross-phase consistency checker for Phase 6.

This module detects version mismatches and traceability gaps between
Agent 4 and Agent 5 evidence, producing a structured audit report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .models import ConsistencyAudit, SourceRef
from .normalization import NormalizedPhase6Bundle


@dataclass(frozen=True)
class VersionConflict:
    module: str
    a4_version: Optional[str]
    a5_version: Optional[str]
    conflict_type: str  # "mismatch" | "missing_in_a5" | "missing_in_a4"


def check_cross_phase_version_consistency(
    bundle: NormalizedPhase6Bundle,
) -> Tuple[Tuple[VersionConflict, ...], bool]:
    """
    Compare module versions declared by Agent 4 vs Agent 5.

    Returns (conflicts, has_conflicts).
    """
    conflicts: List[VersionConflict] = []

    if bundle.agent4_context is None or bundle.agent5_context is None:
        return tuple(conflicts), False

    a4_versions = dict(bundle.agent4_context.module_versions)
    a5_versions = _extract_a5_versions(bundle)

    # Check A4 modules present in A5
    for mod, a4_ver in a4_versions.items():
        a5_ver = a5_versions.get(mod)
        if a5_ver is None:
            conflicts.append(VersionConflict(
                module=mod,
                a4_version=a4_ver,
                a5_version=None,
                conflict_type="missing_in_a5",
            ))
        elif a4_ver != a5_ver:
            conflicts.append(VersionConflict(
                module=mod,
                a4_version=a4_ver,
                a5_version=a5_ver,
                conflict_type="mismatch",
            ))

    # Check A5 modules not in A4 (informational)
    for mod, a5_ver in a5_versions.items():
        if mod not in a4_versions:
            conflicts.append(VersionConflict(
                module=mod,
                a4_version=None,
                a5_version=a5_ver,
                conflict_type="missing_in_a4",
            ))

    has_conflicts = any(c.conflict_type in {"mismatch", "missing_in_a5"} for c in conflicts)
    return tuple(conflicts), has_conflicts


def _extract_a5_versions(bundle: NormalizedPhase6Bundle) -> Dict[str, str]:
    """Extract module -> tested_version map from Agent 5 handoff."""
    versions: Dict[str, str] = {}

    if bundle.agent5_context is None:
        return versions

    # NormalizedAgent5Context now stores module_versions as Mapping[str, str]
    # directly on the dataclass.
    a5_mv = bundle.agent5_context.module_versions
    if isinstance(a5_mv, Mapping):
        for mod, ver in a5_mv.items():
            versions[str(mod)] = str(ver)

    # Backward compatibility: handle raw dict-style module_versions (list of entries)
    raw_ctx = getattr(bundle.agent5_context, "__dict__", {})
    if isinstance(raw_ctx, Mapping):
        mv = raw_ctx.get("module_versions", [])
        if isinstance(mv, list):
            for entry in mv:
                if isinstance(entry, Mapping):
                    mod = entry.get("module", "")
                    ver = entry.get("tested_version") or entry.get("version", "")
                    if mod and ver:
                        versions[str(mod)] = str(ver)

        # Also check coverage_metrics for version data
        cm = raw_ctx.get("coverage_metrics", {})
        if isinstance(cm, Mapping):
            tv = cm.get("tested_versions", {})
            if isinstance(tv, Mapping):
                for mod, ver in tv.items():
                    versions[str(mod)] = str(ver)

    return versions


def build_consistency_audit(
    bundle: NormalizedPhase6Bundle,
) -> ConsistencyAudit:
    """
    Build a comprehensive cross-phase consistency audit report.
    """
    version_conflicts_raw, has_vc = check_cross_phase_version_consistency(bundle)

    version_conflict_strings: List[str] = []
    for vc in version_conflicts_raw:
        if vc.conflict_type == "mismatch":
            version_conflict_strings.append(
                f"module:{vc.module}:A4={vc.a4_version}≠A5={vc.a5_version}"
            )
        elif vc.conflict_type == "missing_in_a5":
            version_conflict_strings.append(
                f"module:{vc.module}:A4={vc.a4_version}:not_in_agent5"
            )

    traceability_gaps: List[str] = []
    if bundle.agent5_context is None:
        traceability_gaps.append("agent5_context_missing")
    elif bundle.requirements_coverage_gap:
        ratio = bundle.agent5_context.requirements_coverage_ratio
        if ratio is not None:
            traceability_gaps.append(
                f"requirements_coverage:{ratio:.0%}_below_100%"
            )

    approval_gaps: List[str] = []
    for item in bundle.approval_items:
        if item.required and not item.signed:
            approval_gaps.append(f"missing_approval:{item.role}")

    return ConsistencyAudit(
        version_conflicts=tuple(version_conflict_strings),
        traceability_gaps=tuple(traceability_gaps),
        approval_gaps=tuple(approval_gaps),
    )


__all__ = [
    "VersionConflict",
    "check_cross_phase_version_consistency",
    "build_consistency_audit",
]
