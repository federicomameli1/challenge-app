"""
Deterministic Phase 4 readiness rule engine.

Policy objective:
- Recommend HOLD if any hard gate is violated.
- Recommend GO only when all hard gates pass.

Hard HOLD conditions:
1) Critical service unhealthy in DEV
2) Unresolved ERROR/CRITICAL runtime issue in deploy logs
3) Open blocker in email thread
4) Mandatory module version mismatch
5) Unmet conditional requirement (e.g., retest required before promotion)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from . import normalization
from .models import (
    Decision,
    RuleCode,
    RuleFinding,
    RuleFindings,
)
from .models import (
    SourceRef as ModelSourceRef,
)


@dataclass(frozen=True)
class PolicyConfig:
    """
    Configuration for deterministic Phase 4 policy checks.
    """

    target_environment: str = "DEV"


class Phase4PolicyEngine:
    """
    Deterministic rule engine for Phase 4 DEV -> TEST readiness.

    This engine evaluates normalized evidence and returns structured findings
    that are auditable and stable across runs.
    """

    def __init__(self, config: Optional[PolicyConfig] = None) -> None:
        self.config = config or PolicyConfig()

    def evaluate(
        self,
        bundle: normalization.NormalizedEvidenceBundle,
        *,
        environment: Optional[str] = None,
    ) -> RuleFindings:
        """
        Evaluate deterministic policy checks and return RuleFindings.

        Args:
            bundle: Normalized evidence bundle.
            environment: Optional explicit environment override (e.g., "DEV").

        Returns:
            RuleFindings with triggered flags, rule-level evidence, and decision.
        """
        env = (environment or self._infer_environment(bundle) or "DEV").upper()

        unhealthy_triggered, unhealthy_reason, unhealthy_evidence = (
            self._check_critical_service_unhealthy(bundle, env)
        )
        log_triggered, log_reason, log_evidence = self._check_unresolved_log_errors(
            bundle
        )
        email_triggered, email_reason, email_evidence = self._check_open_blocker_email(
            bundle
        )
        version_triggered, version_reason, version_evidence = (
            self._check_mandatory_version_mismatch(bundle)
        )
        cond_triggered, cond_reason, cond_evidence = self._check_unmet_conditional(
            bundle
        )

        findings: Tuple[RuleFinding, ...] = (
            RuleFinding(
                code=RuleCode.CRITICAL_SERVICE_UNHEALTHY,
                triggered=unhealthy_triggered,
                reason=unhealthy_reason,
                evidence=tuple(unhealthy_evidence),
            ),
            RuleFinding(
                code=RuleCode.UNRESOLVED_ERROR_OR_CRITICAL_LOG,
                triggered=log_triggered,
                reason=log_reason,
                evidence=tuple(log_evidence),
            ),
            RuleFinding(
                code=RuleCode.OPEN_BLOCKER_EMAIL,
                triggered=email_triggered,
                reason=email_reason,
                evidence=tuple(email_evidence),
            ),
            RuleFinding(
                code=RuleCode.MANDATORY_VERSION_MISMATCH,
                triggered=version_triggered,
                reason=version_reason,
                evidence=tuple(version_evidence),
            ),
            RuleFinding(
                code=RuleCode.UNMET_CONDITIONAL_REQUIREMENT,
                triggered=cond_triggered,
                reason=cond_reason,
                evidence=tuple(cond_evidence),
            ),
        )

        return RuleFindings(
            has_unhealthy_service=unhealthy_triggered,
            has_critical_log_error=log_triggered,
            has_open_blocker_email=email_triggered,
            has_version_mismatch=version_triggered,
            has_unmet_condition=cond_triggered,
            findings=findings,
        )

    def decide(
        self,
        bundle: normalization.NormalizedEvidenceBundle,
        *,
        environment: Optional[str] = None,
    ) -> Decision:
        """
        Convenience wrapper returning only GO/HOLD decision.
        """
        return self.evaluate(bundle, environment=environment).decision

    # ---------------------------------------------------------------------
    # Rule checks
    # ---------------------------------------------------------------------

    def _check_critical_service_unhealthy(
        self,
        bundle: normalization.NormalizedEvidenceBundle,
        environment: str,
    ) -> Tuple[bool, str, List[ModelSourceRef]]:
        report = bundle.health_report
        if report is None:
            return (
                True,
                "Health report missing; cannot confirm critical service readiness in DEV.",
                [],
            )

        if environment != self.config.target_environment.upper():
            return (
                False,
                f"Critical service health gate applies to {self.config.target_environment}; current environment is {environment}.",
                [self._to_model_ref(report.source)] if report.source else [],
            )

        violating_services = [
            svc
            for svc in report.services
            if svc.critical and svc.status.strip().lower() != "healthy"
        ]

        if not violating_services:
            return (
                False,
                "All critical services are healthy in DEV.",
                [self._to_model_ref(report.source)] if report.source else [],
            )

        refs: List[ModelSourceRef] = []
        if report.source:
            refs.append(self._to_model_ref(report.source))
        for svc in violating_services:
            if svc.source:
                refs.append(self._to_model_ref(svc.source))

        names = ", ".join(sorted({s.service for s in violating_services}))
        return (
            True,
            f"Critical service unhealthy in DEV: {names}.",
            refs,
        )

    def _check_unresolved_log_errors(
        self,
        bundle: normalization.NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[ModelSourceRef]]:
        events = bundle.deploy_logs
        if not events:
            return (
                True,
                "Deploy log missing or empty; cannot rule out unresolved runtime errors.",
                [],
            )

        unresolved = self._find_unresolved_error_events(events)
        if not unresolved:
            return (
                False,
                "No unresolved ERROR/CRITICAL runtime issue found in deployment logs.",
                [],
            )

        refs = [self._to_model_ref(evt.source) for evt in unresolved if evt.source]
        top_components = ", ".join(sorted({e.component for e in unresolved}))
        return (
            True,
            f"Unresolved ERROR/CRITICAL runtime issue detected in components: {top_components}.",
            refs,
        )

    def _check_open_blocker_email(
        self,
        bundle: normalization.NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[ModelSourceRef]]:
        thread = bundle.email_thread
        if thread is None:
            return (
                True,
                "Blocker email thread missing; cannot confirm absence of open blockers.",
                [],
            )

        refs: List[ModelSourceRef] = []
        if thread.source:
            refs.append(self._to_model_ref(thread.source))
        for msg in thread.messages:
            if msg.source:
                refs.append(self._to_model_ref(msg.source))

        status = (thread.thread_status or "UNKNOWN").upper()
        if thread.open_blocker_detected or status == "OPEN":
            return (
                True,
                "Open blocker exists in email thread.",
                refs,
            )

        return (
            False,
            f"No open blocker detected in email thread (status={status}).",
            refs,
        )

    def _check_mandatory_version_mismatch(
        self,
        bundle: normalization.NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[ModelSourceRef]]:
        mismatches = [
            v
            for v in bundle.versions
            if v.mandatory_for_phase4
            and (not v.version_match or v.planned_version != v.deployed_version)
        ]

        if not mismatches:
            return (
                False,
                "No mandatory module version mismatch detected.",
                [],
            )

        refs = [self._to_model_ref(v.source) for v in mismatches if v.source]
        detail = ", ".join(
            f"{m.module} ({m.planned_version} != {m.deployed_version})"
            for m in mismatches
        )
        return (
            True,
            f"Mandatory module version mismatch detected: {detail}.",
            refs,
        )

    def _check_unmet_conditional(
        self,
        bundle: normalization.NormalizedEvidenceBundle,
    ) -> Tuple[bool, str, List[ModelSourceRef]]:
        thread = bundle.email_thread
        if thread is None:
            return (
                False,
                "No email thread available to detect conditional unmet status.",
                [],
            )

        refs: List[ModelSourceRef] = []
        if thread.source:
            refs.append(self._to_model_ref(thread.source))
        for msg in thread.messages:
            if msg.has_conditional_language and msg.source:
                refs.append(self._to_model_ref(msg.source))

        if (
            thread.conditional_unmet_detected
            or thread.thread_status == "CONDITIONAL_UNMET"
        ):
            return (
                True,
                "Conditional release requirement is unmet (e.g., retest required).",
                refs,
            )

        return (
            False,
            "No unmet conditional release requirement detected.",
            refs,
        )

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def _infer_environment(
        self,
        bundle: normalization.NormalizedEvidenceBundle,
    ) -> Optional[str]:
        if bundle.health_report and bundle.health_report.environment:
            return bundle.health_report.environment.upper()
        if bundle.versions:
            first_env = bundle.versions[0].environment
            if first_env:
                return first_env.upper()
        return None

    def _find_unresolved_error_events(
        self,
        events: Sequence[normalization.NormalizedLogEvent],
    ) -> List[normalization.NormalizedLogEvent]:
        """
        Identify ERROR/CRITICAL events that are not subsequently resolved.

        Resolution heuristic:
        - A later event is considered a resolution if it is flagged as
          resolution-like and either:
            a) component matches the errored component, or
            b) component is orchestrator and message indicates successful completion.
        """
        unresolved: List[normalization.NormalizedLogEvent] = []

        for idx, evt in enumerate(events):
            if not evt.is_error_like and evt.severity not in {"ERROR", "CRITICAL"}:
                continue

            resolved = False
            for later in events[idx + 1 :]:
                if not later.is_resolution_like:
                    continue
                same_component = later.component == evt.component
                orchestrator_success = (
                    later.component == "orchestrator"
                    and "success" in later.message.lower()
                )
                if same_component or orchestrator_success:
                    resolved = True
                    break

            if not resolved:
                unresolved.append(evt)

        return unresolved

    def _to_model_ref(
        self,
        ref: Optional[normalization.SourceRef],
    ) -> ModelSourceRef:
        if ref is None:
            return ModelSourceRef(file_path="unknown")
        snippet = ref.note if hasattr(ref, "note") else None
        return ModelSourceRef(
            file_path=ref.source_path,
            line_start=ref.line_start,
            line_end=ref.line_end,
            snippet=snippet,
        )


def evaluate_phase4_readiness(
    bundle: normalization.NormalizedEvidenceBundle,
    *,
    environment: Optional[str] = None,
    config: Optional[PolicyConfig] = None,
) -> RuleFindings:
    """
    Functional API for one-shot policy evaluation.
    """
    engine = Phase4PolicyEngine(config=config)
    return engine.evaluate(bundle, environment=environment)
