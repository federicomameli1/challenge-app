"""
Agent 6 — Phase 6: Release Documentation & Approvals.

This agent bridges completed testing and formal production authorization,
consuming outputs from both Agent 4 (DEV→TEST readiness) and Agent 5
(TEST analysis) to produce VDD drafts, cross-phase consistency audits,
and approval readiness artifacts.
"""

from .models import (
    Agent6Output,
    ApprovalItem,
    Confidence,
    ConsistencyAudit,
    Decision,
    DecisionType,
    NotificationDraft,
    RuleCode,
    RuleFinding,
    RuleFindings,
    SourceRef,
    VDDSection,
    VDDDraft,
    build_agent6_output,
    validate_output_schema,
)

__all__ = [
    "Agent6Output",
    "ApprovalItem",
    "Confidence",
    "ConsistencyAudit",
    "Decision",
    "DecisionType",
    "NotificationDraft",
    "RuleCode",
    "RuleFinding",
    "RuleFindings",
    "SourceRef",
    "VDDSection",
    "VDDDraft",
    "build_agent6_output",
    "validate_output_schema",
]