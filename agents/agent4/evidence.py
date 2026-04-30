"""
Evidence mapping utilities for Agent 4.

This module focuses on one responsibility: converting rule findings into
human-readable, traceable reason objects with stable evidence references.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import ReasonItem, RuleCode, RuleFinding, RuleFindings, SourceRef

# ---------------------------------------------------------------------------
# Rule metadata
# ---------------------------------------------------------------------------

_RULE_TITLES: Dict[RuleCode, str] = {
    RuleCode.CRITICAL_SERVICE_UNHEALTHY: "Critical service is unhealthy in DEV",
    RuleCode.UNRESOLVED_ERROR_OR_CRITICAL_LOG: "Unresolved ERROR/CRITICAL runtime issue detected",
    RuleCode.OPEN_BLOCKER_EMAIL: "Open blocker remains in email thread",
    RuleCode.MANDATORY_VERSION_MISMATCH: "Mandatory module version mismatch detected",
    RuleCode.UNMET_CONDITIONAL_REQUIREMENT: "Conditional release requirement is unmet",
}

_RULE_DEFAULT_DETAILS: Dict[RuleCode, str] = {
    RuleCode.CRITICAL_SERVICE_UNHEALTHY: (
        "At least one critical service is not healthy, so promotion must be held."
    ),
    RuleCode.UNRESOLVED_ERROR_OR_CRITICAL_LOG: (
        "Deployment/runtime evidence includes unresolved ERROR or CRITICAL failure."
    ),
    RuleCode.OPEN_BLOCKER_EMAIL: (
        "An unresolved blocker is still open in the communication thread."
    ),
    RuleCode.MANDATORY_VERSION_MISMATCH: (
        "Planned and deployed versions differ for a module marked mandatory for Phase 4."
    ),
    RuleCode.UNMET_CONDITIONAL_REQUIREMENT: (
        "A required conditional step (such as retest evidence) is not yet satisfied."
    ),
}

_GO_DEFAULT_TITLE = "No blocking readiness gates triggered"
_GO_DEFAULT_DETAIL = "All hard readiness gates passed for DEV->TEST recommendation. Human review remains required."

# ---------------------------------------------------------------------------
# SourceRef utilities
# ---------------------------------------------------------------------------


def dedupe_source_refs(refs: Iterable[SourceRef]) -> Tuple[SourceRef, ...]:
    """
    Return source refs in original order without duplicates.
    """
    seen = set()
    out: List[SourceRef] = []
    for ref in refs:
        key = (ref.file_path, ref.line_start, ref.line_end, ref.snippet)
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return tuple(out)


def merge_evidence(
    *evidence_groups: Iterable[SourceRef],
    limit: Optional[int] = None,
) -> Tuple[SourceRef, ...]:
    """
    Merge multiple evidence groups and deduplicate while preserving order.
    """
    merged: List[SourceRef] = []
    for group in evidence_groups:
        for ref in group:
            merged.append(ref)

    deduped = list(dedupe_source_refs(merged))
    if limit is not None and limit >= 0:
        deduped = deduped[:limit]
    return tuple(deduped)


# ---------------------------------------------------------------------------
# Finding -> Reason mapping
# ---------------------------------------------------------------------------


def _title_for_rule(code: RuleCode) -> str:
    return _RULE_TITLES.get(code, f"Policy rule triggered: {code.value}")


def _detail_for_finding(finding: RuleFinding) -> str:
    text = (finding.reason or "").strip()
    if text:
        return text
    return _RULE_DEFAULT_DETAILS.get(
        finding.code, "A blocking policy condition was triggered."
    )


def finding_to_reason(
    finding: RuleFinding,
    evidence_limit: Optional[int] = None,
) -> ReasonItem:
    """
    Convert one triggered rule finding to one user-facing reason item.
    """
    evidence = tuple(finding.evidence)
    if evidence_limit is not None and evidence_limit >= 0:
        evidence = evidence[:evidence_limit]

    return ReasonItem(
        title=_title_for_rule(finding.code),
        detail=_detail_for_finding(finding),
        rule_code=finding.code.value,
        evidence=evidence,
    )


def build_reasons_from_findings(
    findings: RuleFindings,
    include_non_triggered: bool = False,
    evidence_limit_per_reason: Optional[int] = None,
    go_title: str = _GO_DEFAULT_TITLE,
    go_detail: str = _GO_DEFAULT_DETAIL,
) -> Tuple[ReasonItem, ...]:
    """
    Build traceable reasons from rule findings.

    Behavior:
    - If blocking rules are triggered, returns one reason per triggered finding.
    - If no blocking rule is triggered, returns one GO reason.
    - If include_non_triggered=True, non-triggered findings are included as
      informational reasons with rule code attached.
    """
    reasons: List[ReasonItem] = []

    for finding in findings.findings:
        if finding.triggered:
            reasons.append(
                finding_to_reason(
                    finding,
                    evidence_limit=evidence_limit_per_reason,
                )
            )
        elif include_non_triggered:
            reasons.append(
                ReasonItem(
                    title=_title_for_rule(finding.code),
                    detail="Rule checked and not triggered.",
                    rule_code=finding.code.value,
                    evidence=(),
                )
            )

    if not reasons:
        reasons.append(
            ReasonItem(
                title=go_title,
                detail=go_detail,
                rule_code=None,
                evidence=(),
            )
        )

    return tuple(reasons)


# ---------------------------------------------------------------------------
# Cross-reason evidence helpers
# ---------------------------------------------------------------------------


def flatten_reason_evidence(
    reasons: Sequence[ReasonItem],
    limit: Optional[int] = None,
) -> Tuple[SourceRef, ...]:
    """
    Flatten all reason-level evidence into a deduplicated list.
    """
    merged: List[SourceRef] = []
    for reason in reasons:
        merged.extend(reason.evidence)
    deduped = list(dedupe_source_refs(merged))
    if limit is not None and limit >= 0:
        deduped = deduped[:limit]
    return tuple(deduped)


def flatten_finding_evidence(
    findings: RuleFindings,
    triggered_only: bool = True,
    limit: Optional[int] = None,
) -> Tuple[SourceRef, ...]:
    """
    Flatten all finding evidence into a deduplicated list.
    """
    merged: List[SourceRef] = []
    for finding in findings.findings:
        if triggered_only and not finding.triggered:
            continue
        merged.extend(finding.evidence)

    deduped = list(dedupe_source_refs(merged))
    if limit is not None and limit >= 0:
        deduped = deduped[:limit]
    return tuple(deduped)


def build_traceable_reasons_and_evidence(
    findings: RuleFindings,
    evidence_limit_per_reason: Optional[int] = None,
    total_evidence_limit: Optional[int] = None,
) -> Tuple[Tuple[ReasonItem, ...], Tuple[SourceRef, ...]]:
    """
    High-level utility used by orchestrators:

    1) Build user-facing reasons from findings.
    2) Build one deduplicated evidence list for output contract.
    """
    reasons = build_reasons_from_findings(
        findings=findings,
        include_non_triggered=False,
        evidence_limit_per_reason=evidence_limit_per_reason,
    )
    evidence = flatten_reason_evidence(reasons, limit=total_evidence_limit)
    return reasons, evidence


# ---------------------------------------------------------------------------
# Optional enhancement helpers
# ---------------------------------------------------------------------------


def ensure_reason_has_evidence(
    reason: ReasonItem,
    fallback_evidence: Sequence[SourceRef],
    limit: Optional[int] = None,
) -> ReasonItem:
    """
    If a reason has no evidence, attach fallback evidence (deduplicated).
    """
    if reason.evidence:
        return reason

    attached = list(dedupe_source_refs(fallback_evidence))
    if limit is not None and limit >= 0:
        attached = attached[:limit]

    return replace(reason, evidence=tuple(attached))


def evidence_coverage_ratio(reasons: Sequence[ReasonItem]) -> float:
    """
    Return fraction of reasons that include at least one evidence reference.
    """
    if not reasons:
        return 0.0
    covered = sum(1 for r in reasons if len(r.evidence) > 0)
    return covered / len(reasons)


__all__ = [
    "build_reasons_from_findings",
    "build_traceable_reasons_and_evidence",
    "dedupe_source_refs",
    "ensure_reason_has_evidence",
    "evidence_coverage_ratio",
    "finding_to_reason",
    "flatten_finding_evidence",
    "flatten_reason_evidence",
    "merge_evidence",
]
