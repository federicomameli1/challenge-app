"""
Approval readiness builder for Phase 6.

This module prepares structured inputs for the supplier/customer approval
workflow, including identifying missing approvals and drafting stakeholder
notifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import ApprovalItem, NotificationDraft, SourceRef
from .normalization import NormalizedPhase6Bundle, NormalizedApprovalItem


def build_approval_readiness(
    bundle: NormalizedPhase6Bundle,
) -> Tuple[NormalizedApprovalItem, ...]:
    """
    Build the complete approval readiness checklist.

    Returns all approval items with their current status.
    """
    return bundle.approval_items


def identify_missing_approvals(
    bundle: NormalizedPhase6Bundle,
) -> List[str]:
    """
    List roles that require sign-off but have not signed.
    """
    missing: List[str] = []
    for item in bundle.approval_items:
        if item.required and not item.signed:
            missing.append(item.role)
    return missing


def build_notification_drafts(
    bundle: NormalizedPhase6Bundle,
    decision: str,
) -> Tuple[NotificationDraft, ...]:
    """
    Draft structured notification messages for stakeholders.

    Notifications are produced for:
    - Release manager: GO/HOLD decision summary
    - Missing approvers: reminder to sign
    - Customer representative: production readiness (on GO)
    """
    drafts: List[NotificationDraft] = []
    rid = bundle.release_id
    sid = bundle.scenario_id

    if decision == "GO":
        drafts.append(NotificationDraft(
            recipient_role="release_manager",
            subject=f"[GO] Release {rid} approved for production deployment",
            body=(
                f"Release {rid} (scenario {sid}) has been assessed by Agent 6 "
                f"and is recommended for GO. All Phase 6 gates have passed. "
                f"Proceed with production deployment approval workflow."
            ),
            priority="high",
        ))

        # Notify customer representative
        drafts.append(NotificationDraft(
            recipient_role="customer_representative",
            subject=f"[ACTION REQUIRED] Production sign-off for release {rid}",
            body=(
                f"Release {rid} is ready for your production deployment authorization. "
                f"All technical gates (Phase 4, 5, 6) have passed. "
                f"Please review and provide your Nulla Osta sign-off."
            ),
            priority="high",
        ))

    elif decision == "HOLD":
        drafts.append(NotificationDraft(
            recipient_role="release_manager",
            subject=f"[HOLD] Release {rid} requires resolution before deployment",
            body=(
                f"Release {rid} (scenario {sid}) has been assessed by Agent 6 "
                f"and is recommended for HOLD. The following issues must be resolved "
                f"before production deployment can proceed:\n"
                + _format_hold_reasons(bundle)
            ),
            priority="high",
        ))

    # Draft reminders for missing approvers
    missing = identify_missing_approvals(bundle)
    for role in missing:
        drafts.append(NotificationDraft(
            recipient_role=role,
            subject=f"[REMINDER] Your approval is required for release {rid}",
            body=(
                f"Your sign-off is required before release {rid} can proceed to production. "
                f"Please review the release documentation and provide your approval."
            ),
            priority="normal",
        ))

    return tuple(drafts)


def _format_hold_reasons(bundle: NormalizedPhase6Bundle) -> str:
    reasons: List[str] = []
    if bundle.cross_phase_version_mismatch:
        reasons.append("- Cross-phase version mismatch detected between Phase 4 and Phase 5")
    if bundle.agent5_critical_defect_open:
        reasons.append("- Open critical/high defects remain unresolved")
    if bundle.agent4_blocker_unconfirmed:
        reasons.append("- Phase 4 unresolved blockers not confirmed closed")
    if bundle.requirements_coverage_gap:
        reasons.append("- Requirements coverage below 100%")
    if bundle.vdd_incomplete:
        reasons.append("- VDD draft is incomplete")
    if bundle.missing_approval_trigger:
        reasons.append("- Required approval sign-offs are missing")

    if not reasons:
        reasons.append("- See Agent 6 report for details")

    return "\n".join(reasons)


__all__ = [
    "build_approval_readiness",
    "identify_missing_approvals",
    "build_notification_drafts",
]
