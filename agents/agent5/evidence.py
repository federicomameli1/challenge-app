"""
Agent 5 evidence mapping utilities.

This module transforms deterministic rule findings into:
- human-readable reason items
- deduplicated evidence references
- simple evidence coverage diagnostics

Design goals:
- deterministic, auditable reason/evidence mapping
- stable ordering and deduplication
- lightweight, dependency-free utilities
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import ReasonItem, RuleFinding, RuleFindings, SourceRef


def _source_key(
    ref: SourceRef,
) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[str]]:
    return (ref.file_path, ref.line_start, ref.line_end, ref.snippet)


def dedupe_source_refs(refs: Iterable[SourceRef]) -> Tuple[SourceRef, ...]:
    """
    Remove duplicate source references while preserving first-seen order.
    """
    out: List[SourceRef] = []
    seen = set()

    for ref in refs:
        key = _source_key(ref)
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)

    return tuple(out)


def flatten_finding_evidence(findings: Sequence[RuleFinding]) -> Tuple[SourceRef, ...]:
    """
    Flatten and deduplicate evidence from a list of rule findings.
    """
    refs: List[SourceRef] = []
    for finding in findings:
        refs.extend(list(finding.evidence))
    return dedupe_source_refs(refs)


def flatten_reason_evidence(reasons: Sequence[ReasonItem]) -> Tuple[SourceRef, ...]:
    """
    Flatten and deduplicate evidence from reason items.
    """
    refs: List[SourceRef] = []
    for reason in reasons:
        refs.extend(list(reason.evidence))
    return dedupe_source_refs(refs)


def merge_evidence(
    *groups: Sequence[SourceRef],
    total_limit: Optional[int] = None,
) -> Tuple[SourceRef, ...]:
    """
    Merge multiple evidence groups and deduplicate.

    Args:
        groups: One or more evidence sequences.
        total_limit: Optional cap on final evidence count.
    """
    refs: List[SourceRef] = []
    for group in groups:
        refs.extend(list(group))

    merged = list(dedupe_source_refs(refs))
    if total_limit is not None and total_limit >= 0:
        merged = merged[:total_limit]
    return tuple(merged)


def _title_from_rule_code(code_value: str) -> str:
    return code_value.replace("_", " ").strip().title()


def finding_to_reason(
    finding: RuleFinding,
    *,
    evidence_limit: Optional[int] = None,
) -> ReasonItem:
    """
    Convert one RuleFinding into a ReasonItem.
    """
    evidence = list(dedupe_source_refs(finding.evidence))
    if evidence_limit is not None and evidence_limit >= 0:
        evidence = evidence[:evidence_limit]

    return ReasonItem(
        title=_title_from_rule_code(finding.code.value),
        detail=finding.reason,
        rule_code=finding.code.value,
        evidence=tuple(evidence),
    )


def build_reasons_from_findings(
    findings: RuleFindings,
    *,
    include_non_triggered: bool = False,
    evidence_limit_per_reason: int = 5,
) -> Tuple[ReasonItem, ...]:
    """
    Build reason items from deterministic rule findings.

    Default behavior:
    - include triggered findings only
    - if none triggered, return one "all gates passed" reason
    """
    out: List[ReasonItem] = []

    for finding in findings.findings:
        if finding.triggered or include_non_triggered:
            out.append(
                finding_to_reason(
                    finding,
                    evidence_limit=evidence_limit_per_reason,
                )
            )

    if out:
        return tuple(out)

    # No triggered findings -> GO summary reason
    return (
        ReasonItem(
            title="All hard release gates passed",
            detail=(
                "No hard Phase 5 gate was triggered. Mandatory coverage, execution outcomes, "
                "defect severity/status, conditional retest checks, and Agent 4 continuity checks "
                "did not indicate blocking risk."
            ),
            rule_code=None,
            evidence=tuple(),
        ),
    )


def ensure_reason_has_evidence(
    reason: ReasonItem,
    fallback: Sequence[SourceRef],
    *,
    evidence_limit: int = 5,
) -> ReasonItem:
    """
    Ensure a reason has evidence by applying fallback refs when needed.
    """
    if reason.evidence:
        return reason

    fallback_refs = list(dedupe_source_refs(fallback))[: max(0, evidence_limit)]
    return ReasonItem(
        title=reason.title,
        detail=reason.detail,
        rule_code=reason.rule_code,
        evidence=tuple(fallback_refs),
    )


def build_traceable_reasons_and_evidence(
    findings: RuleFindings,
    *,
    evidence_limit_per_reason: int = 5,
    total_evidence_limit: int = 20,
    include_non_triggered: bool = False,
) -> Tuple[Tuple[ReasonItem, ...], Tuple[SourceRef, ...]]:
    """
    Build reason items plus merged evidence with configurable limits.
    """
    reasons = list(
        build_reasons_from_findings(
            findings,
            include_non_triggered=include_non_triggered,
            evidence_limit_per_reason=evidence_limit_per_reason,
        )
    )

    # Fallback pool from full finding evidence set.
    fallback_pool = flatten_finding_evidence(findings.findings)

    # Ensure each reason has at least one evidence ref when possible.
    fixed_reasons: List[ReasonItem] = []
    for reason in reasons:
        fixed_reasons.append(
            ensure_reason_has_evidence(
                reason,
                fallback_pool,
                evidence_limit=evidence_limit_per_reason,
            )
        )

    merged_evidence = merge_evidence(
        flatten_reason_evidence(fixed_reasons),
        total_limit=total_evidence_limit,
    )

    return tuple(fixed_reasons), merged_evidence


def evidence_coverage_ratio(reasons: Sequence[ReasonItem]) -> float:
    """
    Compute ratio of reasons that include at least one evidence reference.
    """
    if not reasons:
        return 1.0
    covered = sum(1 for reason in reasons if len(reason.evidence) > 0)
    return covered / len(reasons)


def reason_evidence_coverage_report(reasons: Sequence[ReasonItem]) -> Dict[str, float]:
    """
    Small helper for diagnostics payloads.
    """
    ratio = evidence_coverage_ratio(reasons)
    return {"reason_evidence_coverage": round(ratio, 4)}


__all__ = [
    "dedupe_source_refs",
    "flatten_finding_evidence",
    "flatten_reason_evidence",
    "merge_evidence",
    "finding_to_reason",
    "build_reasons_from_findings",
    "ensure_reason_has_evidence",
    "build_traceable_reasons_and_evidence",
    "evidence_coverage_ratio",
    "reason_evidence_coverage_report",
]
