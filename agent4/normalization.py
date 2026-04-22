"""
Agent 4 normalization layer.

This module converts heterogeneous Phase 4 evidence into canonical structures
used by the deterministic policy engine and explanation layer.

Supported evidence types:
- requirements rows (CSV-like dicts)
- module/version rows (CSV-like dicts)
- deployment logs (plain text)
- service health reports (JSON string or dict)
- blocker/clarification emails (plain text threads)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRef:
    source_type: str
    source_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    note: Optional[str] = None


@dataclass(frozen=True)
class NormalizedRequirement:
    requirement_id: str
    description: str
    priority: str
    module: str
    mandatory_for_phase4: bool
    source: Optional[SourceRef] = None


@dataclass(frozen=True)
class NormalizedModuleVersion:
    scenario_id: Optional[str]
    release_id: Optional[str]
    environment: str
    module: str
    planned_version: str
    deployed_version: str
    mandatory_for_phase4: bool
    version_match: bool
    source: Optional[SourceRef] = None


@dataclass(frozen=True)
class NormalizedLogEvent:
    timestamp: Optional[datetime]
    severity: str
    component: str
    message: str
    is_error_like: bool
    is_resolution_like: bool
    source: Optional[SourceRef] = None


@dataclass(frozen=True)
class NormalizedHealthService:
    service: str
    status: str
    critical: bool
    reason: str
    source: Optional[SourceRef] = None


@dataclass(frozen=True)
class NormalizedHealthReport:
    scenario_id: Optional[str]
    release_id: Optional[str]
    environment: str
    generated_at: Optional[datetime]
    overall_status: str
    services: List[NormalizedHealthService]
    source: Optional[SourceRef] = None


@dataclass(frozen=True)
class NormalizedEmailMessage:
    timestamp: Optional[datetime]
    sender: str
    recipients: str
    body: str
    status_hint: str
    has_blocker_language: bool
    has_resolution_language: bool
    has_conditional_language: bool
    source: Optional[SourceRef] = None


@dataclass(frozen=True)
class NormalizedEmailThread:
    subject: str
    messages: List[NormalizedEmailMessage]
    thread_status: str  # OPEN | RESOLVED | CONDITIONAL_UNMET | NONE | UNKNOWN
    open_blocker_detected: bool
    conditional_unmet_detected: bool
    source: Optional[SourceRef] = None


@dataclass(frozen=True)
class NormalizedEvidenceBundle:
    requirements: List[NormalizedRequirement] = field(default_factory=list)
    versions: List[NormalizedModuleVersion] = field(default_factory=list)
    deploy_logs: List[NormalizedLogEvent] = field(default_factory=list)
    health_report: Optional[NormalizedHealthReport] = None
    email_thread: Optional[NormalizedEmailThread] = None


# ---------------------------------------------------------------------------
# Normalization constants
# ---------------------------------------------------------------------------

SEVERITY_ORDER = ("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL")

MODULE_ALIASES: Dict[str, str] = {
    # Canonical names used by synthetic generator
    "ingestion-gateway": "ingestion-gateway",
    "event-router": "event-router",
    "monitoring-core": "monitoring-core",
    "analytics-api": "analytics-api",
    "alarm-engine": "alarm-engine",
    "ui-backend": "ui-backend",
    # Common alias variants
    "ingestiongateway": "ingestion-gateway",
    "ingestion_gateway": "ingestion-gateway",
    "eventrouter": "event-router",
    "event_router": "event-router",
    "monitoringcore": "monitoring-core",
    "monitoring core": "monitoring-core",
    "monitoring_core": "monitoring-core",
    "module-b": "monitoring-core",
    "analyticsapi": "analytics-api",
    "analytics_api": "analytics-api",
    "alarmengine": "alarm-engine",
    "alarm_engine": "alarm-engine",
    "uibackend": "ui-backend",
    "ui_backend": "ui-backend",
}

ENV_ALIASES: Dict[str, str] = {
    "dev": "DEV",
    "development": "DEV",
    "test": "TEST",
    "qa": "TEST",
    "prod": "PROD",
    "production": "PROD",
}

PRIORITY_ALIASES: Dict[str, str] = {
    "h": "HIGH",
    "high": "HIGH",
    "m": "MEDIUM",
    "med": "MEDIUM",
    "medium": "MEDIUM",
    "l": "LOW",
    "low": "LOW",
    "critical": "CRITICAL",
}

STATUS_ALIASES: Dict[str, str] = {
    "healthy": "healthy",
    "ok": "healthy",
    "up": "healthy",
    "degraded": "degraded",
    "warn": "degraded",
    "warning": "degraded",
    "unhealthy": "unhealthy",
    "down": "unhealthy",
    "failed": "unhealthy",
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _norm_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def parse_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n"}:
        return False
    return default


def normalize_priority(value: Any) -> str:
    if value is None:
        return "MEDIUM"
    text = str(value).strip().lower()
    return PRIORITY_ALIASES.get(text, str(value).strip().upper())


def normalize_environment(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    text = str(value).strip().lower()
    return ENV_ALIASES.get(text, str(value).strip().upper())


def normalize_module_name(value: Any) -> str:
    if value is None:
        return "unknown-module"
    text = str(value).strip().lower()
    direct = MODULE_ALIASES.get(text)
    if direct:
        return direct

    simplified = re.sub(r"[\s_]+", "-", text)
    simplified = re.sub(r"[^a-z0-9-]+", "", simplified).strip("-")
    alias = MODULE_ALIASES.get(simplified)
    if alias:
        return alias
    return simplified or "unknown-module"


_SEMVER_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)\s*$")


def normalize_semver(value: Any) -> str:
    if value is None:
        return "0.0.0"
    text = str(value).strip()
    m = _SEMVER_RE.match(text)
    if not m:
        return text
    major, minor, patch = m.groups()
    return f"{int(major)}.{int(minor)}.{int(patch)}"


def parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    # Supports ISO8601 and common forms.
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _line_source(source_path: str, line_idx_1based: int) -> SourceRef:
    return SourceRef(
        source_type="text",
        source_path=source_path,
        line_start=line_idx_1based,
        line_end=line_idx_1based,
    )


# ---------------------------------------------------------------------------
# Requirements normalization
# ---------------------------------------------------------------------------


def normalize_requirements(
    rows: Sequence[Dict[str, Any]],
    *,
    source_path: str = "requirements_master.csv",
) -> List[NormalizedRequirement]:
    normalized: List[NormalizedRequirement] = []
    for i, row in enumerate(rows, start=2):  # header is line 1 in csv
        req_id = _norm_whitespace(
            str(row.get("requirement_id", f"REQ-UNK-{i}"))
        ).upper()
        desc = _norm_whitespace(str(row.get("description", "")))
        priority = normalize_priority(row.get("priority"))
        module = normalize_module_name(row.get("module"))
        mandatory = parse_bool(row.get("mandatory_for_phase4"), default=True)

        normalized.append(
            NormalizedRequirement(
                requirement_id=req_id,
                description=desc,
                priority=priority,
                module=module,
                mandatory_for_phase4=mandatory,
                source=SourceRef(
                    source_type="csv",
                    source_path=source_path,
                    line_start=i,
                    line_end=i,
                ),
            )
        )
    return normalized


# ---------------------------------------------------------------------------
# Versions normalization
# ---------------------------------------------------------------------------


def normalize_module_versions(
    rows: Sequence[Dict[str, Any]],
    *,
    source_path: str = "phase4_modules_versions.csv",
) -> List[NormalizedModuleVersion]:
    normalized: List[NormalizedModuleVersion] = []
    for i, row in enumerate(rows, start=2):
        planned = normalize_semver(row.get("planned_version"))
        deployed = normalize_semver(row.get("deployed_version"))
        explicit_match = row.get("version_match")
        version_match = (
            parse_bool(explicit_match, default=(planned == deployed))
            if explicit_match is not None
            else (planned == deployed)
        )

        normalized.append(
            NormalizedModuleVersion(
                scenario_id=_clean_optional(row.get("scenario_id")),
                release_id=_clean_optional(row.get("release_id")),
                environment=normalize_environment(row.get("environment")),
                module=normalize_module_name(row.get("module")),
                planned_version=planned,
                deployed_version=deployed,
                mandatory_for_phase4=parse_bool(
                    row.get("mandatory_for_phase4"), default=True
                ),
                version_match=version_match,
                source=SourceRef(
                    source_type="csv",
                    source_path=source_path,
                    line_start=i,
                    line_end=i,
                ),
            )
        )
    return normalized


def _clean_optional(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------------------
# Deployment log normalization
# ---------------------------------------------------------------------------

_LOG_RE = re.compile(
    r"^\s*(?P<ts>\S+)\s+(?P<sev>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\s+\[(?P<component>[^\]]+)\]\s+(?P<msg>.*)$",
    re.IGNORECASE,
)

_ERROR_LIKE_RE = re.compile(
    r"\b(error|critical|failed|failure|panic|exception|unstable)\b", re.IGNORECASE
)
_RESOLUTION_LIKE_RE = re.compile(
    r"\b(resolved|recovered|completed successfully|healthy|ok)\b", re.IGNORECASE
)


def normalize_deploy_log(
    log_text: str,
    *,
    source_path: str = "dev_deploy_logs/unknown.log",
) -> List[NormalizedLogEvent]:
    events: List[NormalizedLogEvent] = []
    for idx, raw_line in enumerate(log_text.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line:
            continue

        m = _LOG_RE.match(line)
        if m:
            ts = parse_timestamp(m.group("ts"))
            sev = m.group("sev").upper()
            if sev == "WARNING":
                sev = "WARN"
            component = normalize_module_name(m.group("component"))
            msg = m.group("msg").strip()
        else:
            # Fallback parser for unstructured lines
            ts = None
            sev = "INFO"
            component = "orchestrator"
            msg = line

        is_error_like = sev in {"ERROR", "CRITICAL"} or bool(_ERROR_LIKE_RE.search(msg))
        is_resolution_like = bool(_RESOLUTION_LIKE_RE.search(msg))

        events.append(
            NormalizedLogEvent(
                timestamp=ts,
                severity=sev,
                component=component,
                message=msg,
                is_error_like=is_error_like,
                is_resolution_like=is_resolution_like,
                source=_line_source(source_path, idx),
            )
        )
    return events


# ---------------------------------------------------------------------------
# Health report normalization
# ---------------------------------------------------------------------------


def normalize_health_report(
    report: Any,
    *,
    source_path: str = "service_health_reports/unknown.json",
) -> NormalizedHealthReport:
    data: Dict[str, Any]
    if isinstance(report, str):
        data = json.loads(report)
    elif isinstance(report, dict):
        data = report
    else:
        raise TypeError("health report must be dict or JSON string")

    services_raw = data.get("services") or []
    services: List[NormalizedHealthService] = []

    for svc in services_raw:
        service_name = normalize_module_name(svc.get("service"))
        status = STATUS_ALIASES.get(
            str(svc.get("status", "")).strip().lower(), "unknown"
        )
        reason = _norm_whitespace(str(svc.get("reason", "")))
        critical = parse_bool(svc.get("critical"), default=False)

        services.append(
            NormalizedHealthService(
                service=service_name,
                status=status,
                critical=critical,
                reason=reason,
                source=SourceRef(source_type="json", source_path=source_path),
            )
        )

    overall_raw = str(data.get("overall_status", "")).strip().lower()
    overall_status = STATUS_ALIASES.get(overall_raw, overall_raw or "unknown")

    return NormalizedHealthReport(
        scenario_id=_clean_optional(data.get("scenario_id")),
        release_id=_clean_optional(data.get("release_id")),
        environment=normalize_environment(data.get("environment")),
        generated_at=parse_timestamp(data.get("generated_at")),
        overall_status=overall_status,
        services=services,
        source=SourceRef(source_type="json", source_path=source_path),
    )


# ---------------------------------------------------------------------------
# Email thread normalization
# ---------------------------------------------------------------------------

_EMAIL_TIME_RE = re.compile(r"^Time:\s*(.+)$", re.IGNORECASE)
_EMAIL_FROM_RE = re.compile(r"^From:\s*(.+)$", re.IGNORECASE)
_EMAIL_TO_RE = re.compile(r"^To:\s*(.+)$", re.IGNORECASE)
_EMAIL_SUBJECT_RE = re.compile(r"^Subject:\s*(.+)$", re.IGNORECASE)

_BLOCKER_RE = re.compile(
    r"\b(blocker|blocking|hold|cannot promote|do not promote)\b", re.IGNORECASE
)
_RESOLVED_RE = re.compile(
    r"\b(resolved|closed|no blocker|no open blockers|verified)\b", re.IGNORECASE
)
_CONDITIONAL_RE = re.compile(
    r"\b(conditional|retest required|required retest|evidence missing)\b", re.IGNORECASE
)
_OPEN_RE = re.compile(r"\b(open|unresolved|pending)\b", re.IGNORECASE)
_STATUS_LINE_RE = re.compile(r"\bstatus:\s*([A-Z _-]+)\b", re.IGNORECASE)


def normalize_email_thread(
    thread_text: str,
    *,
    source_path: str = "dev_blockers_emails/unknown.txt",
) -> NormalizedEmailThread:
    lines = thread_text.splitlines()
    subject = _extract_subject(lines) or "(no subject)"
    messages = _extract_messages(thread_text, source_path=source_path)

    open_blocker = False
    conditional_unmet = False
    resolved_any = False

    for m in messages:
        body_l = m.body.lower()
        if m.has_conditional_language:
            conditional_unmet = True
        if m.has_blocker_language and not m.has_resolution_language:
            open_blocker = True
        if m.has_resolution_language:
            resolved_any = True

        if m.status_hint in {"OPEN", "OPEN_BLOCKER"}:
            open_blocker = True
        elif m.status_hint in {"RESOLVED", "NONE"}:
            resolved_any = True
        elif m.status_hint == "CONDITIONAL_UNMET":
            conditional_unmet = True

        if _OPEN_RE.search(body_l) and _BLOCKER_RE.search(body_l):
            open_blocker = True

    # Thread-level resolution precedence:
    # CONDITIONAL_UNMET > OPEN > RESOLVED > NONE > UNKNOWN
    if conditional_unmet:
        status = "CONDITIONAL_UNMET"
    elif open_blocker and not resolved_any:
        status = "OPEN"
    elif resolved_any and not open_blocker:
        status = "RESOLVED"
    elif not messages:
        status = "NONE"
    else:
        status = "UNKNOWN"

    return NormalizedEmailThread(
        subject=subject,
        messages=messages,
        thread_status=status,
        open_blocker_detected=(status == "OPEN"),
        conditional_unmet_detected=(status == "CONDITIONAL_UNMET"),
        source=SourceRef(source_type="text", source_path=source_path),
    )


def _extract_subject(lines: Sequence[str]) -> Optional[str]:
    for line in lines:
        m = _EMAIL_SUBJECT_RE.match(line.strip())
        if m:
            return _norm_whitespace(m.group(1))
    return None


def _extract_messages(
    thread_text: str, *, source_path: str
) -> List[NormalizedEmailMessage]:
    chunks = [c.strip() for c in re.split(r"\n\s*\n", thread_text) if c.strip()]
    messages: List[NormalizedEmailMessage] = []

    # Merge metadata lines with following body chunks.
    pending_meta: Dict[str, str] = {"time": "", "from": "", "to": ""}
    body_buffer: List[str] = []

    def flush_message() -> None:
        if not any(
            [
                pending_meta["time"],
                pending_meta["from"],
                pending_meta["to"],
                body_buffer,
            ]
        ):
            return
        body = _norm_whitespace(" ".join(body_buffer))
        status_hint = _status_from_text(body)
        msg = NormalizedEmailMessage(
            timestamp=parse_timestamp(pending_meta["time"])
            if pending_meta["time"]
            else None,
            sender=pending_meta["from"] or "unknown",
            recipients=pending_meta["to"] or "unknown",
            body=body,
            status_hint=status_hint,
            has_blocker_language=bool(_BLOCKER_RE.search(body)),
            has_resolution_language=bool(_RESOLVED_RE.search(body)),
            has_conditional_language=bool(_CONDITIONAL_RE.search(body)),
            source=SourceRef(source_type="text", source_path=source_path),
        )
        messages.append(msg)
        pending_meta["time"] = ""
        pending_meta["from"] = ""
        pending_meta["to"] = ""
        body_buffer.clear()

    for chunk in chunks:
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            continue

        matched_meta = False
        for ln in lines:
            t = _EMAIL_TIME_RE.match(ln)
            f = _EMAIL_FROM_RE.match(ln)
            to = _EMAIL_TO_RE.match(ln)
            if t:
                if body_buffer:
                    flush_message()
                pending_meta["time"] = t.group(1).strip()
                matched_meta = True
                continue
            if f:
                pending_meta["from"] = f.group(1).strip()
                matched_meta = True
                continue
            if to:
                pending_meta["to"] = to.group(1).strip()
                matched_meta = True
                continue

            # Subject is thread-level, ignore in per-message body.
            if _EMAIL_SUBJECT_RE.match(ln):
                matched_meta = True
                continue

            body_buffer.append(ln)

        if not matched_meta and body_buffer:
            # Keep accumulating body lines.
            continue

    flush_message()
    return messages


def _status_from_text(body: str) -> str:
    status_line = _STATUS_LINE_RE.search(body)
    if status_line:
        raw = status_line.group(1).strip().replace("-", "_").replace(" ", "_").upper()
        if raw in {"OPEN", "OPEN_BLOCKER"}:
            return "OPEN_BLOCKER"
        if raw in {"RESOLVED", "CLOSED"}:
            return "RESOLVED"
        if raw in {"NONE", "NO_BLOCKER"}:
            return "NONE"
        if raw in {"CONDITIONAL_UNMET", "UNMET_CONDITIONAL"}:
            return "CONDITIONAL_UNMET"

    low = body.lower()
    if _CONDITIONAL_RE.search(low):
        return "CONDITIONAL_UNMET"
    if _BLOCKER_RE.search(low) and _OPEN_RE.search(low):
        return "OPEN_BLOCKER"
    if _RESOLVED_RE.search(low):
        return "RESOLVED"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Bundle-level normalization entrypoint
# ---------------------------------------------------------------------------


def normalize_evidence_bundle(
    *,
    requirements_rows: Sequence[Dict[str, Any]],
    version_rows: Sequence[Dict[str, Any]],
    deploy_log_text: str,
    health_report: Any,
    email_thread_text: str,
    requirements_source: str = "requirements_master.csv",
    versions_source: str = "phase4_modules_versions.csv",
    deploy_log_source: str = "dev_deploy_logs/unknown.log",
    health_source: str = "service_health_reports/unknown.json",
    email_source: str = "dev_blockers_emails/unknown.txt",
) -> NormalizedEvidenceBundle:
    return NormalizedEvidenceBundle(
        requirements=normalize_requirements(
            requirements_rows, source_path=requirements_source
        ),
        versions=normalize_module_versions(version_rows, source_path=versions_source),
        deploy_logs=normalize_deploy_log(
            deploy_log_text, source_path=deploy_log_source
        ),
        health_report=normalize_health_report(health_report, source_path=health_source),
        email_thread=normalize_email_thread(
            email_thread_text, source_path=email_source
        ),
    )


__all__ = [
    "SourceRef",
    "NormalizedRequirement",
    "NormalizedModuleVersion",
    "NormalizedLogEvent",
    "NormalizedHealthService",
    "NormalizedHealthReport",
    "NormalizedEmailMessage",
    "NormalizedEmailThread",
    "NormalizedEvidenceBundle",
    "normalize_requirements",
    "normalize_module_versions",
    "normalize_deploy_log",
    "normalize_health_report",
    "normalize_email_thread",
    "normalize_evidence_bundle",
    "normalize_module_name",
    "normalize_environment",
    "normalize_semver",
    "parse_bool",
    "parse_timestamp",
]
