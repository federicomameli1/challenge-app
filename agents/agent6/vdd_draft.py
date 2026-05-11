"""
VDD (Version Description Document) draft builder for Phase 6.

This module produces a structured VDD draft from cross-phase evidence,
consolidating data from Agent 4 and Agent 5 handoffs into a human-readable
release document template.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .models import (
    ModuleInventoryEntry,
    SourceRef,
    VDDSection,
    VDDDraft,
)
from .normalization import NormalizedPhase6Bundle


# Required VDD sections for Phase 6 release gate
_REQUIRED_VDD_SECTIONS = (
    "functional_requirements",
    "test_traceability",
    "defect_summary",
    "approval_section",
)


@dataclass(frozen=True)
class VDDSectionBuilder:
    name: str
    present: bool
    populated: bool


def build_vdd_draft(
    bundle: NormalizedPhase6Bundle,
    *,
    use_llm_summary: bool = False,
) -> VDDDraft:
    """
    Build a structured VDD draft from normalized Phase 6 evidence.

    The VDD draft is the primary Phase 6 output artifact, providing
    a consolidated view of the release for human reviewers and approval
    workflow automation.
    """
    scope = _build_scope(bundle)
    module_inventory = _build_module_inventory(bundle)
    requirements_coverage = _build_requirements_coverage(bundle)
    test_evidence_summary = _build_test_evidence_summary(bundle)
    open_issues = _build_open_issues(bundle)
    change_log = _build_change_log(bundle)
    approval_checklist = _build_approval_checklist(bundle)
    sections = _build_vdd_sections(
        bundle,
        scope,
        requirements_coverage,
        test_evidence_summary,
        open_issues,
        approval_checklist,
    )

    # Compute release summary
    release_summary = _build_release_summary(bundle)

    return VDDDraft(
        release_summary=release_summary,
        scope=scope,
        module_inventory=module_inventory,
        requirements_coverage=requirements_coverage,
        test_evidence_summary=test_evidence_summary,
        open_issues=open_issues,
        change_log=change_log,
        approval_checklist=approval_checklist,
        sections=sections,
    )


def _build_release_summary(bundle: NormalizedPhase6Bundle) -> str:
    rid = bundle.release_id
    sid = bundle.scenario_id
    a4_dec = bundle.agent4_context.decision if bundle.agent4_context else "UNKNOWN"
    a5_dec = bundle.agent5_context.decision if bundle.agent5_context else "UNKNOWN"
    return (
        f"Release {rid} / Scenario {sid}: "
        f"Agent 4 decision={a4_dec}, Agent 5 decision={a5_dec}. "
        f"This VDD draft consolidates evidence from Phase 4 and Phase 5 governance assessments."
    )


def _build_scope(bundle: NormalizedPhase6Bundle) -> Tuple[str, ...]:
    scope_items: List[str] = []

    # Modules from A4
    if bundle.agent4_context:
        for mod in bundle.agent4_context.module_versions:
            version = bundle.agent4_context.module_versions[mod]
            scope_items.append(f"module:{mod}@{version}")

    # Requirements from A5
    if bundle.agent5_context:
        ratio = bundle.agent5_context.requirements_coverage_ratio
        if ratio is not None:
            scope_items.append(f"requirements_coverage:{ratio:.0%}")

    return tuple(scope_items) if scope_items else ("scope:no_evidence",)


def _build_module_inventory(bundle: NormalizedPhase6Bundle) -> Tuple[ModuleInventoryEntry, ...]:
    entries: List[ModuleInventoryEntry] = []

    if bundle.agent4_context:
        for mod, deployed_ver in bundle.agent4_context.module_versions.items():
            # Try to get A5 tested version
            tested_ver = _get_a5_tested_version(bundle, mod)
            entries.append(ModuleInventoryEntry(
                module=mod,
                planned_version=deployed_ver,
                deployed_version=deployed_ver,
                tested_version=tested_ver or deployed_ver,
                source=SourceRef(
                    file_path="agent4_handoff",
                    snippet=f"module={mod}, deployed={deployed_ver}",
                ),
            ))

    return tuple(entries) if entries else ()


def _get_a5_tested_version(bundle: NormalizedPhase6Bundle, module: str) -> Optional[str]:
    if bundle.agent5_context:
        # A5 may store tested versions in coverage metrics or rule findings
        payload = bundle.agent5_context
        if hasattr(payload, "__dict__"):
            ctx_dict = bundle.agent5_context.__dict__ if hasattr(bundle.agent5_context, "__dict__") else {}
        # Try coverage_metrics
        cm = getattr(bundle.agent5_context, "vdd_completeness", {})
        if isinstance(cm, dict):
            tv = cm.get("tested_versions", {}).get(module)
            if tv:
                return tv
    return None


def _build_requirements_coverage(bundle: NormalizedPhase6Bundle) -> Dict[str, Any]:
    if bundle.agent5_context:
        ratio = bundle.agent5_context.requirements_coverage_ratio
        if ratio is not None:
            return {
                "coverage_ratio": ratio,
                "status": "covered" if ratio >= 1.0 else "gap",
            }

    return {"coverage_ratio": None, "status": "unknown"}


def _build_test_evidence_summary(bundle: NormalizedPhase6Bundle) -> str:
    if bundle.agent5_context:
        a5_dec = bundle.agent5_context.decision
        triggered = bundle.agent5_context.triggered_rules
        if triggered:
            return (
                f"Agent 5 decision: {a5_dec}. "
                f"Triggered rules: {', '.join(triggered)}."
            )
        return f"Agent 5 decision: {a5_dec}. No triggered rules."

    return "No Agent 5 context available for test evidence summary."


def _build_open_issues(bundle: NormalizedPhase6Bundle) -> Tuple[str, ...]:
    issues: List[str] = []

    if bundle.agent4_context and bundle.agent4_context.open_blocker_detected:
        issues.append("Agent4: Open blocker email present")

    if bundle.agent5_context and bundle.agent5_context.critical_defect_open:
        ids = bundle.agent5_context.open_critical_defect_ids
        if ids:
            issues.append(f"Agent5: Open critical/high defects: {', '.join(ids)}")

    if bundle.cross_phase_version_mismatch:
        issues.append("Cross-phase: Version mismatch between Agent 4 and Agent 5")

    if bundle.requirements_coverage_gap:
        issues.append("Coverage: Requirements coverage below 100%")

    if bundle.missing_approval_trigger:
        issues.append("Approvals: Missing required sign-off")

    return tuple(issues) if issues else ("no_open_issues",)


def _build_change_log(bundle: NormalizedPhase6Bundle) -> str:
    changelog_parts: List[str] = [f"Release: {bundle.release_id}"]

    if bundle.agent4_context:
        changelog_parts.append(
            f"Phase 4 (DEV→TEST): Agent 4 decision={bundle.agent4_context.decision}"
        )
        if bundle.agent4_context.unresolved_conditions:
            changelog_parts.append(
                f"  Unresolved conditions: {', '.join(bundle.agent4_context.unresolved_conditions)}"
            )

    if bundle.agent5_context:
        changelog_parts.append(
            f"Phase 5 (TEST analysis): Agent 5 decision={bundle.agent5_context.decision}"
        )

    return "\n".join(changelog_parts)


def _build_approval_checklist(bundle: NormalizedPhase6Bundle) -> Dict[str, Any]:
    checklist: Dict[str, Any] = {"items": [], "all_signed": True}

    for item in bundle.approval_items:
        checklist["items"].append({
            "role": item.role,
            "required": item.required,
            "signed": item.signed,
            "signed_by": item.signed_by,
        })
        if item.required and not item.signed:
            checklist["all_signed"] = False

    return checklist


def _build_vdd_sections(
    bundle: NormalizedPhase6Bundle,
    scope: Tuple[str, ...],
    requirements_coverage: Dict[str, Any],
    test_evidence_summary: str,
    open_issues: Tuple[str, ...],
    approval_checklist: Dict[str, Any],
) -> Tuple[VDDSection, ...]:
    sections: List[VDDSection] = []

    # Functional requirements section
    func_present = bool(scope)
    func_populated = func_present and requirements_coverage.get("status") != "unknown"
    sections.append(VDDSection(
        name="functional_requirements",
        present=func_present,
        populated=func_populated,
        evidence_refs=(SourceRef(file_path="agent5_handoff:requirements"),),
    ))

    # Test traceability section
    trace_present = bool(test_evidence_summary)
    trace_populated = trace_present and "Agent 5 decision" in test_evidence_summary
    sections.append(VDDSection(
        name="test_traceability",
        present=trace_present,
        populated=trace_populated,
        evidence_refs=(SourceRef(file_path="agent5_handoff:traceability"),),
    ))

    # Defect summary section
    defect_present = bundle.agent5_context is not None
    defect_populated = defect_present and (
        not bundle.agent5_context.critical_defect_open
        if bundle.agent5_context
        else True
    )
    sections.append(VDDSection(
        name="defect_summary",
        present=defect_present,
        populated=defect_populated,
        evidence_refs=(SourceRef(file_path="agent5_handoff:defects"),),
    ))

    # Approval section
    approval_present = bool(bundle.approval_items)
    approval_populated = approval_present and approval_checklist.get("all_signed", False)
    sections.append(VDDSection(
        name="approval_section",
        present=approval_present,
        populated=approval_populated,
        evidence_refs=(SourceRef(file_path="approval_workflow_manifest"),),
    ))

    return tuple(sections)


def check_vdd_completeness(vdd: VDDDraft) -> Tuple[bool, List[str]]:
    """
    Check if all required VDD sections are present and populated.

    Returns (is_complete, list_of_incomplete_sections).
    """
    incomplete: List[str] = []
    for section in vdd.sections:
        if section.name in _REQUIRED_VDD_SECTIONS:
            if not section.present or not section.populated:
                incomplete.append(section.name)

    return len(incomplete) == 0, incomplete


__all__ = [
    "VDDSectionBuilder",
    "build_vdd_draft",
    "check_vdd_completeness",
    "_REQUIRED_VDD_SECTIONS",
]
