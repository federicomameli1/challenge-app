#!/usr/bin/env python3
"""
CI analysis runner for the Hitachi workflow integration.

This script now performs real agent calls during CI by:
- collecting CI-native repository evidence,
- synthesizing a temporary structured dataset for Agent 4 or Agent 5,
- invoking the existing deterministic + optional LLM agent pipeline,
- emitting JSON/Markdown artifacts for human approval.

Important design note:
- the final promotion decision remains human-controlled,
- the agents provide a structured GO/HOLD recommendation only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".docx",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
}

MARKER_SCAN_EXTENSIONS = {
    ".md",
    ".txt",
    ".csv",
    ".yaml",
    ".yml",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
}

MARKER_SCAN_IGNORE_PREFIXES = (
    "Dataset/Test_Sets/",
    "synthetic_data/",
    "tests/",
    "artifacts/",
    ".github/workflows/drafts/",
)

MARKER_SCAN_IGNORE_SUFFIXES = (
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
)

MARKER_SCAN_IGNORE_PATHS = {
    "scripts/run_ci_analysis.py",
}

CORE_DOCUMENTS = [
    ".github/workflows/ci.yml",
    "README.md",
    "WORKLOG_SUMMARY.md",
    "Dockerfile",
    "package.json",
    "backend/requirements.txt",
]

PHASE_DOCUMENTS = {
    "pre-test": [
        "chart/Chart.yaml",
        "chart/values.yaml",
        "chart/templates/deployment.yaml",
        "chart/templates/service.yaml",
        "chart/templates/namespace.yaml",
    ],
    "pre-prod": [
        "chart/Chart.yaml",
        "chart/values.yaml",
        "chart/templates/deployment.yaml",
        "chart/templates/service.yaml",
        "chart/templates/namespace.yaml",
        "Dataset/Test_Sets/README_TEST_SETS.md",
    ],
}

PHASE_METADATA = {
    "pre-test": {
        "agent": "agent4",
        "stage_label": "Phase 4",
        "purpose": "Readiness check before entering the TEST stage.",
        "human_gate": "Operator approval required before TEST promotion.",
        "scenario_id": "CI-S4-001",
        "environment": "DEV",
    },
    "pre-prod": {
        "agent": "agent5",
        "stage_label": "Phase 5",
        "purpose": "Verification check after tests/build and before PROD.",
        "human_gate": "Operator approval required before PROD promotion.",
        "scenario_id": "CI-P5-001",
        "environment": "TEST",
    },
}

BLOCKER_MARKERS = {
    "BLOCKER": re.compile(r"\bblocker\b", re.IGNORECASE),
    "FIXME": re.compile(r"\bfixme\b", re.IGNORECASE),
    "TODO": re.compile(r"\btodo\b", re.IGNORECASE),
    "UNRESOLVED": re.compile(r"\bunresolved\b", re.IGNORECASE),
    "WIP": re.compile(r"\bwip\b", re.IGNORECASE),
    "DO_NOT_PROMOTE": re.compile(r"do not promote", re.IGNORECASE),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect CI evidence, synthesize a CI dataset, and run the matching agent."
    )
    parser.add_argument(
        "--phase",
        choices=sorted(PHASE_METADATA.keys()),
        required=True,
        help="Pipeline gate to analyze.",
    )
    parser.add_argument(
        "--event-name",
        default=os.environ.get("GITHUB_EVENT_NAME", "manual"),
        help="GitHub event name or equivalent CI event label.",
    )
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("CI_ANALYSIS_BASE_REF", "").strip() or None,
        help="Base git ref for diff collection. Defaults to HEAD~1 when omitted.",
    )
    parser.add_argument(
        "--head-ref",
        default=os.environ.get("CI_ANALYSIS_HEAD_REF", "").strip() or "HEAD",
        help="Head git ref for diff collection.",
    )
    parser.add_argument(
        "--pr-number",
        default=os.environ.get("PR_NUMBER", "").strip() or None,
        help="Optional pull request number for metadata.",
    )
    parser.add_argument(
        "--event-payload",
        default=os.environ.get("GITHUB_EVENT_PATH", "").strip() or None,
        help="Optional GitHub event payload path used to enrich CI evidence.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/ci-analysis",
        help="Directory where JSON/Markdown artifacts will be written.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable the optional LLM summary layer for the agent call.",
    )
    parser.add_argument(
        "--write-step-summary",
        action="store_true",
        help="Append the Markdown report to GITHUB_STEP_SUMMARY when available.",
    )
    parser.add_argument(
        "--previous-report",
        default=None,
        help="Optional previous-stage ci_report.json path, used by pre-prod Agent 5 continuity checks.",
    )
    parser.add_argument(
        "--stage-results-json",
        default=None,
        help="Optional JSON file containing test/build stage results for pre-prod.",
    )
    parser.add_argument(
        "--test-status",
        default=os.environ.get("CI_TEST_STATUS", "PASS"),
        help="Fallback test status when no stage-results JSON is provided.",
    )
    parser.add_argument(
        "--build-status",
        default=os.environ.get("CI_BUILD_STATUS", "PASS"),
        help="Fallback build status when no stage-results JSON is provided.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_command(
    command: Sequence[str],
    *,
    allow_failure: bool = False,
) -> str:
    completed = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        check=not allow_failure,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0 and allow_failure:
        return ""
    return completed.stdout.strip()


def repo_file_exists(path: str) -> bool:
    return (PROJECT_ROOT / path).exists()


def normalize_relpath(path: str) -> str:
    return str(Path(path)).replace("\\", "/")


def normalize_status(value: Any, default: str = "PASS") -> str:
    text = str(value or "").strip().upper()
    if text in {"PASS", "PASSED", "SUCCESS", "SUCCEEDED", "OK"}:
        return "PASS"
    if text in {"FAIL", "FAILED", "ERROR"}:
        return "FAIL"
    if text in {"BLOCKED", "CANCELLED"}:
        return "BLOCKED"
    if text in {"CONDITIONAL_UNMET", "RETEST_UNMET"}:
        return "CONDITIONAL_UNMET"
    if text in {"NOT_RUN", "SKIPPED", "PENDING", "UNKNOWN"}:
        return "NOT_RUN"
    return default


def resolve_changed_files(base_ref: Optional[str], head_ref: str) -> List[str]:
    base = (base_ref or "").strip() or "HEAD~1"
    diff_output = run_command(
        ["git", "diff", "--name-only", f"{base}...{head_ref}"],
        allow_failure=True,
    )
    if not diff_output:
        diff_output = run_command(
            ["git", "diff", "--name-only", f"{base}", f"{head_ref}"],
            allow_failure=True,
        )
    if not diff_output:
        diff_output = run_command(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", head_ref],
            allow_failure=True,
        )
    paths = [normalize_relpath(line.strip()) for line in diff_output.splitlines() if line.strip()]
    return sorted(dict.fromkeys(paths))


def resolve_diff_stat(base_ref: Optional[str], head_ref: str) -> str:
    base = (base_ref or "").strip() or "HEAD~1"
    return run_command(
        ["git", "diff", "--stat=120,160", f"{base}", f"{head_ref}"],
        allow_failure=True,
    )


def classify_path(path: str) -> str:
    normalized = normalize_relpath(path)
    if normalized.startswith(".github/workflows/"):
        return "workflow"
    if normalized.startswith("chart/"):
        return "deployment"
    if normalized.startswith("src/") or normalized.startswith("backend/"):
        return "application"
    if normalized.startswith("tests/"):
        return "tests"
    if normalized.startswith("Dataset/") or normalized.startswith("synthetic_data/"):
        return "reference_data"
    if Path(normalized).suffix.lower() in TEXT_EXTENSIONS:
        return "document"
    return "other"


def select_relevant_documents(phase: str, changed_files: Sequence[str]) -> List[str]:
    selected: List[str] = []

    for candidate in CORE_DOCUMENTS + PHASE_DOCUMENTS.get(phase, []):
        if repo_file_exists(candidate):
            selected.append(normalize_relpath(candidate))

    for path in changed_files:
        suffix = Path(path).suffix.lower()
        if path.startswith(".github/workflows/drafts/"):
            continue
        if suffix in TEXT_EXTENSIONS or path.startswith(".github/workflows/") or path.startswith("chart/"):
            if repo_file_exists(path):
                selected.append(normalize_relpath(path))

    return sorted(dict.fromkeys(selected))


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def should_scan_marker_file(rel_path: str) -> bool:
    normalized = normalize_relpath(rel_path)
    if normalized in MARKER_SCAN_IGNORE_PATHS:
        return False
    if normalized.startswith(MARKER_SCAN_IGNORE_PREFIXES):
        return False
    if normalized.endswith(MARKER_SCAN_IGNORE_SUFFIXES):
        return False
    return Path(normalized).suffix.lower() in MARKER_SCAN_EXTENSIONS


def marker_line_is_relevant(rel_path: str, line: str) -> bool:
    normalized = normalize_relpath(rel_path)
    suffix = Path(normalized).suffix.lower()
    stripped = line.strip()
    if not stripped:
        return False

    if suffix in {".py"}:
        return stripped.startswith("#")
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return stripped.startswith(("//", "/*", "*", "{/*"))
    if suffix in {".yaml", ".yml"}:
        return stripped.startswith("#")
    if suffix in {".json"}:
        return False
    return True


def scan_blocker_markers(changed_files: Sequence[str]) -> List[Dict[str, Any]]:
    observations: List[Dict[str, Any]] = []
    for rel_path in changed_files:
        path = PROJECT_ROOT / rel_path
        if not path.exists() or not path.is_file():
            continue
        if not should_scan_marker_file(rel_path):
            continue
        try:
            lines = read_text_file(path).splitlines()
        except Exception:
            continue

        for idx, line in enumerate(lines[:400], start=1):
            if not marker_line_is_relevant(rel_path, line):
                continue
            for marker, pattern in BLOCKER_MARKERS.items():
                if not pattern.search(line):
                    continue
                observations.append(
                    {
                        "path": normalize_relpath(rel_path),
                        "line": idx,
                        "marker": marker,
                        "snippet": line.strip()[:240],
                    }
                )
                if len(observations) >= 20:
                    return observations
    return observations


def detect_workflow_test_step() -> bool:
    workflow_path = PROJECT_ROOT / ".github/workflows/ci.yml"
    if not workflow_path.exists():
        return False
    text = read_text_file(workflow_path).lower()
    return (
        "npm test" in text
        or "vitest" in text
        or "run tests" in text
        or "pytest" in text
    )


def load_stage_results(args: argparse.Namespace) -> Dict[str, Any]:
    base = {
        "tests": {"status": normalize_status(args.test_status)},
        "build": {"status": normalize_status(args.build_status)},
    }

    if not args.stage_results_json:
        return base

    path = Path(args.stage_results_json)
    if not path.exists():
        raise FileNotFoundError(f"Stage results JSON not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Stage results JSON must contain an object.")

    tests = payload.get("tests", {})
    build = payload.get("build", {})
    if isinstance(tests, dict):
        base["tests"].update(tests)
    if isinstance(build, dict):
        base["build"].update(build)

    base["tests"]["status"] = normalize_status(base["tests"].get("status"))
    base["build"]["status"] = normalize_status(base["build"].get("status"))
    return base


def load_previous_report(path_value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Previous report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Previous report JSON must contain an object.")
    return payload


def load_event_payload(path_value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def maybe_get_llm_generate() -> Optional[Callable[[str], str]]:
    try:
        from backend.app import LLM_GENERATE  # type: ignore
    except Exception:
        return None
    return LLM_GENERATE


def truncate_text(value: Any, limit: int = 400) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def make_llm_diagnostics_wrapper(
    llm_generate: Optional[Callable[[str], str]],
) -> Tuple[Optional[Callable[[str], str]], Dict[str, Any]]:
    diagnostics: Dict[str, Any] = {
        "configured": llm_generate is not None,
        "called": False,
        "error": None,
        "raw_response_preview": None,
        "model": os.environ.get("OPENROUTER_MODEL", "").strip() or "openai/gpt-oss-20b:free",
    }

    if llm_generate is None:
        return None, diagnostics

    def wrapped(prompt: str) -> str:
        diagnostics["called"] = True
        try:
            raw = llm_generate(prompt)
            diagnostics["raw_response_preview"] = truncate_text(raw, 500)
            return raw
        except Exception as exc:
            diagnostics["error"] = truncate_text(f"{type(exc).__name__}: {exc}", 500)
            raise

    return wrapped, diagnostics


def scan_marker_text(
    text: str,
    *,
    source_path: str,
    source_label: str,
    start_line: int = 1,
) -> List[Dict[str, Any]]:
    observations: List[Dict[str, Any]] = []
    for idx, line in enumerate(text.splitlines(), start=start_line):
        for marker, pattern in BLOCKER_MARKERS.items():
            if not pattern.search(line):
                continue
            observations.append(
                {
                    "path": source_path,
                    "line": idx,
                    "marker": marker,
                    "snippet": line.strip()[:240],
                    "source": source_label,
                }
            )
    return observations


def collect_commit_messages(base_ref: Optional[str], head_ref: str) -> List[Dict[str, str]]:
    base = (base_ref or "").strip() or "HEAD~1"
    log_output = run_command(
        ["git", "log", "--format=%H%x09%s", f"{base}..{head_ref}"],
        allow_failure=True,
    )
    if not log_output:
        log_output = run_command(
            ["git", "log", "--format=%H%x09%s", "-n", "8", head_ref],
            allow_failure=True,
        )

    messages: List[Dict[str, str]] = []
    for line in log_output.splitlines():
        if not line.strip():
            continue
        sha, _, subject = line.partition("\t")
        messages.append(
            {
                "sha": sha.strip(),
                "subject": truncate_text(subject, 180),
            }
        )
        if len(messages) >= 8:
            break
    return messages


def build_event_context(
    args: argparse.Namespace,
    event_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    payload = event_payload or {}
    pr_payload = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
    release_payload = payload.get("release") if isinstance(payload.get("release"), dict) else {}
    head_commit = payload.get("head_commit") if isinstance(payload.get("head_commit"), dict) else {}

    title = (
        pr_payload.get("title")
        or release_payload.get("name")
        or release_payload.get("tag_name")
        or head_commit.get("message")
        or ""
    )
    body = pr_payload.get("body") or release_payload.get("body") or ""
    commit_messages = collect_commit_messages(args.base_ref, args.head_ref)

    metadata_markers: List[Dict[str, Any]] = []
    if title:
        metadata_markers.extend(
            scan_marker_text(
                str(title),
                source_path="event/title",
                source_label="event_metadata",
            )
        )
    if body:
        metadata_markers.extend(
            scan_marker_text(
                str(body),
                source_path="event/body",
                source_label="event_metadata",
            )
        )
    for idx, item in enumerate(commit_messages, start=1):
        subject = item.get("subject", "")
        if not subject:
            continue
        metadata_markers.extend(
            scan_marker_text(
                subject,
                source_path=f"event/commit_messages/{idx}",
                source_label="commit_message",
            )
        )

    target_branch = None
    if isinstance(pr_payload.get("base"), dict):
        target_branch = pr_payload["base"].get("ref")
    if not target_branch:
        target_branch = payload.get("ref")

    return {
        "title": truncate_text(title, 180),
        "body_preview": truncate_text(body, 400),
        "commit_messages": commit_messages,
        "metadata_markers": metadata_markers,
        "is_fork_pr": bool(
            pr_payload.get("head", {}).get("repo", {}).get("fork")
            if isinstance(pr_payload.get("head"), dict)
            else False
        ),
        "target_branch": target_branch,
    }


def build_evidence_bundle(args: argparse.Namespace) -> Dict[str, Any]:
    changed_files = resolve_changed_files(args.base_ref, args.head_ref)
    relevant_documents = select_relevant_documents(args.phase, changed_files)
    diff_stat = resolve_diff_stat(args.base_ref, args.head_ref)
    file_blocker_markers = scan_blocker_markers(changed_files)
    event_payload = load_event_payload(args.event_payload)
    event_context = build_event_context(args, event_payload)
    blocker_markers = file_blocker_markers + list(event_context["metadata_markers"])

    changed_file_details = [
        {"path": path, "category": classify_path(path)} for path in changed_files
    ]
    category_counts: Dict[str, int] = {}
    for item in changed_file_details:
        category = item["category"]
        category_counts[category] = category_counts.get(category, 0) + 1

    workflow_files_changed = any(
        path.startswith(".github/workflows/") for path in changed_files
    )
    deployment_files_changed = any(path.startswith("chart/") for path in changed_files)
    application_files_changed = any(
        path.startswith("src/") or path.startswith("backend/") for path in changed_files
    )
    runtime_files_changed = any(
        path in {"package.json", "package-lock.json", "backend/requirements.txt", "Dockerfile"}
        for path in changed_files
    )
    tests_changed = any(
        path.startswith("tests/")
        or ".test." in path
        or ".spec." in path
        or path.endswith("App.test.jsx")
        for path in changed_files
    )

    missing_core_documents = [
        path for path in CORE_DOCUMENTS if not repo_file_exists(path)
    ]
    chart_required = [
        "chart/Chart.yaml",
        "chart/templates/deployment.yaml",
        "chart/templates/service.yaml",
    ]
    missing_chart_documents = [
        path for path in chart_required if not repo_file_exists(path)
    ]
    workflow_has_test_step = detect_workflow_test_step()
    delivery_changed = application_files_changed or deployment_files_changed or runtime_files_changed

    heuristics = {
        "workflow_files_changed": workflow_files_changed,
        "deployment_files_changed": deployment_files_changed,
        "application_files_changed": application_files_changed,
        "runtime_files_changed": runtime_files_changed,
        "tests_changed": tests_changed,
        "delivery_changed": delivery_changed,
        "workflow_has_test_step": workflow_has_test_step,
        "missing_core_documents": missing_core_documents,
        "missing_chart_documents": missing_chart_documents,
        "blocker_markers": blocker_markers,
        "file_blocker_markers": file_blocker_markers,
        "metadata_blocker_markers": event_context["metadata_markers"],
        "conditional_retest_needed": bool(delivery_changed and not tests_changed),
    }

    return {
        "event_context": event_context,
        "changed_files": changed_files,
        "changed_file_details": changed_file_details,
        "relevant_documents": relevant_documents,
        "counts": {
            "changed_files": len(changed_files),
            "relevant_documents": len(relevant_documents),
            "categories": category_counts,
        },
        "heuristics": heuristics,
        "diff_stat": diff_stat,
    }


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    write_text(path, json.dumps(payload, indent=2) + "\n")


def write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def short_sha(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "local-build"
    return text[:12]


def build_agent4_email_text(evidence: Dict[str, Any]) -> str:
    heuristics = evidence["heuristics"]
    marker_lines = heuristics["blocker_markers"]
    event_context = evidence.get("event_context", {})

    header = [
        "Subject: CI Release Readiness Review",
        f"Time: {utc_now()}",
        "From: ci-analysis@challenge.local",
        "To: release.manager@challenge.local",
        "",
    ]

    if event_context.get("title"):
        header.append(f"Change request: {event_context['title']}")
    if event_context.get("target_branch"):
        header.append(f"Target branch: {event_context['target_branch']}")
    header.append("")

    if marker_lines:
        marker_summary = "; ".join(
            f"{item['marker']} in {item['path']}:{item['line']}" for item in marker_lines[:4]
        )
        body = [
            "Status: OPEN",
            "A blocking review marker is present in the current change set.",
            f"Detected markers: {marker_summary}.",
            "Do not promote until the blocker is explicitly resolved.",
        ]
    elif heuristics["conditional_retest_needed"]:
        body = [
            "Status: CONDITIONAL_UNMET",
            "Application or deployment-relevant files changed without corresponding automated test updates.",
            "Retest required before promotion to the next stage.",
        ]
    else:
        body = [
            "Status: RESOLVED",
            "No open blockers remain in the reviewed CI evidence.",
            "Ready for test promotion.",
        ]

    commit_messages = event_context.get("commit_messages") or []
    if commit_messages:
        body.append(
            "Recent commits: "
            + "; ".join(item["subject"] for item in commit_messages[:3] if item.get("subject"))
        )

    return "\n".join(header + body) + "\n"


def build_agent4_log_text(evidence: Dict[str, Any]) -> str:
    heuristics = evidence["heuristics"]
    event_context = evidence.get("event_context", {})
    lines = [
        f"{utc_now()} INFO [ci-workflow] CI evidence bundle collected successfully",
    ]

    if event_context.get("title"):
        lines.append(
            f"{utc_now()} INFO [change-request] Reviewing change request: {event_context['title']}"
        )
    if event_context.get("target_branch"):
        lines.append(
            f"{utc_now()} INFO [change-request] Target branch/environment reference: {event_context['target_branch']}"
        )

    if not heuristics["workflow_has_test_step"]:
        lines.append(
            f"{utc_now()} ERROR [ci-workflow] Required automated test step is missing from .github/workflows/ci.yml"
        )

    if heuristics["missing_chart_documents"]:
        lines.append(
            f"{utc_now()} ERROR [deployment-chart] Required chart files are missing: "
            + ", ".join(heuristics["missing_chart_documents"])
        )

    if heuristics["missing_core_documents"]:
        lines.append(
            f"{utc_now()} WARN [release-docs] Missing supporting documentation: "
            + ", ".join(heuristics["missing_core_documents"])
        )

    if not heuristics["missing_chart_documents"] and heuristics["workflow_has_test_step"]:
        lines.append(
            f"{utc_now()} INFO [orchestrator] readiness checks completed successfully"
        )

    metadata_markers = heuristics.get("metadata_blocker_markers") or []
    if metadata_markers:
        lines.append(
            f"{utc_now()} WARN [change-request] Review markers found in PR/release metadata or commit messages"
        )

    return "\n".join(lines) + "\n"


def build_agent4_health_report(
    *,
    scenario_id: str,
    release_id: str,
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    heuristics = evidence["heuristics"]
    ci_workflow_healthy = heuristics["workflow_has_test_step"]
    deployment_chart_healthy = not heuristics["missing_chart_documents"]
    critical_ok = ci_workflow_healthy and deployment_chart_healthy

    return {
        "scenario_id": scenario_id,
        "release_id": release_id,
        "environment": "DEV",
        "generated_at": utc_now(),
        "overall_status": "healthy" if critical_ok else "unhealthy",
        "services": [
            {
                "service": "ci-workflow",
                "status": "healthy" if ci_workflow_healthy else "unhealthy",
                "critical": True,
                "reason": (
                    "Workflow contains an explicit automated test step."
                    if ci_workflow_healthy
                    else "Workflow is missing an explicit automated test step."
                ),
            },
            {
                "service": "deployment-chart",
                "status": "healthy" if deployment_chart_healthy else "unhealthy",
                "critical": True,
                "reason": (
                    "Chart files required for deployment packaging are present."
                    if deployment_chart_healthy
                    else "One or more required chart files are missing."
                ),
            },
            {
                "service": "release-docs",
                "status": "healthy" if not heuristics["missing_core_documents"] else "degraded",
                "critical": False,
                "reason": (
                    "Core release-supporting documents are available."
                    if not heuristics["missing_core_documents"]
                    else "Some supporting documents are missing."
                ),
            },
        ],
    }


def build_agent4_dataset(
    *,
    dataset_root: Path,
    scenario_id: str,
    release_id: str,
    evidence: Dict[str, Any],
) -> None:
    requirements_rows = [
        {
            "requirement_id": "CI-REQ-WORKFLOW",
            "description": "The CI workflow must include an explicit automated test stage.",
            "priority": "HIGH",
            "module": "ci-workflow",
            "mandatory_for_phase4": "true",
        },
        {
            "requirement_id": "CI-REQ-DEPLOYMENT",
            "description": "Deployment packaging files must remain structurally available.",
            "priority": "HIGH",
            "module": "deployment-chart",
            "mandatory_for_phase4": "true",
        },
        {
            "requirement_id": "CI-REQ-REVIEW",
            "description": "The current change set must not contain unresolved blockers before TEST promotion.",
            "priority": "MEDIUM",
            "module": "release-review",
            "mandatory_for_phase4": "true",
        },
    ]

    version_rows = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "environment": "DEV",
            "module": "ci-workflow",
            "planned_version": short_sha(release_id),
            "deployed_version": short_sha(release_id),
            "mandatory_for_phase4": "true",
            "version_match": "true",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "environment": "DEV",
            "module": "deployment-chart",
            "planned_version": short_sha(release_id),
            "deployed_version": short_sha(release_id),
            "mandatory_for_phase4": "true",
            "version_match": "true",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "environment": "DEV",
            "module": "release-review",
            "planned_version": short_sha(release_id),
            "deployed_version": short_sha(release_id),
            "mandatory_for_phase4": "true",
            "version_match": "true",
        },
    ]

    release_calendar_rows = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "environment": "DEV",
            "dev_window_start": utc_now(),
            "dev_window_end": utc_now(),
            "target_test_promotion": "pending-human-approval",
        }
    ]

    write_csv(
        dataset_root / "requirements_master.csv",
        ["requirement_id", "description", "priority", "module", "mandatory_for_phase4"],
        requirements_rows,
    )
    write_csv(
        dataset_root / "phase4_modules_versions.csv",
        [
            "scenario_id",
            "release_id",
            "environment",
            "module",
            "planned_version",
            "deployed_version",
            "mandatory_for_phase4",
            "version_match",
        ],
        version_rows,
    )
    write_csv(
        dataset_root / "release_calendar.csv",
        [
            "scenario_id",
            "release_id",
            "environment",
            "dev_window_start",
            "dev_window_end",
            "target_test_promotion",
        ],
        release_calendar_rows,
    )
    write_text(
        dataset_root / "dev_deploy_logs" / f"{scenario_id}.log",
        build_agent4_log_text(evidence),
    )
    write_json(
        dataset_root / "service_health_reports" / f"{scenario_id}.json",
        build_agent4_health_report(
            scenario_id=scenario_id,
            release_id=release_id,
            evidence=evidence,
        ),
    )
    write_text(
        dataset_root / "dev_blockers_emails" / f"{scenario_id}.txt",
        build_agent4_email_text(evidence),
    )


def tests_and_build_green(stage_results: Dict[str, Any]) -> bool:
    return (
        normalize_status(stage_results.get("tests", {}).get("status")) == "PASS"
        and normalize_status(stage_results.get("build", {}).get("status")) == "PASS"
    )


def derive_agent4_context(
    previous_report: Optional[Dict[str, Any]],
    stage_results: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not previous_report:
        return None

    payload = (
        previous_report.get("agent_output", {}).get("payload")
        if isinstance(previous_report.get("agent_output"), dict)
        else None
    )
    if not isinstance(payload, dict):
        return None

    decision = str(payload.get("decision", "")).strip().upper() or "UNKNOWN"
    rule_findings = payload.get("rule_findings", {})
    if isinstance(rule_findings, dict):
        triggered_rules = rule_findings.get("triggered_rule_codes", [])
    else:
        triggered_rules = []

    normalized_rules = [
        str(item).strip()
        for item in triggered_rules
        if str(item).strip()
    ]

    closure_confirmed = False
    if decision == "GO":
        closure_confirmed = True
    elif tests_and_build_green(stage_results):
        auto_closable = {"unmet_conditional_requirement"}
        closure_confirmed = bool(normalized_rules) and all(
            item in auto_closable for item in normalized_rules
        )

    return {
        "decision": decision,
        "triggered_rules": normalized_rules,
        "unresolved_conditions": normalized_rules,
        "closure_confirmed": closure_confirmed,
    }


def build_agent5_email_text(
    *,
    previous_context: Optional[Dict[str, Any]],
    stage_results: Dict[str, Any],
) -> str:
    header = [
        "Subject: CI Test Verification Review",
        f"Time: {utc_now()}",
        "From: ci-analysis@challenge.local",
        "To: release.manager@challenge.local",
        "",
    ]

    tests_status = normalize_status(stage_results.get("tests", {}).get("status"))
    build_status = normalize_status(stage_results.get("build", {}).get("status"))
    all_green = tests_and_build_green(stage_results)
    tests_command = str(stage_results.get("tests", {}).get("command", "n/a")).strip() or "n/a"
    build_command = str(stage_results.get("build", {}).get("command", "n/a")).strip() or "n/a"

    if previous_context and previous_context.get("decision") == "HOLD":
        if previous_context.get("closure_confirmed"):
            body = [
                "Status: RESOLVED",
                "All re-tests pass and the prior Phase 4 conditional requirement is now closed.",
                "Ready for human review before production promotion.",
            ]
        else:
            body = [
                "Status: OPEN",
                "A prior Phase 4 HOLD remains unresolved in the available Phase 5 evidence.",
                "Do not proceed to production until continuity is explicitly closed.",
            ]
    elif all_green:
        body = [
            "Status: RESOLVED",
            f"Automated verification completed successfully (tests={tests_status}, build={build_status}).",
            "Ready for human review before production promotion.",
        ]
    else:
        body = [
            "Status: OPEN",
            f"Verification is incomplete or failed (tests={tests_status}, build={build_status}).",
            "Do not proceed to production.",
        ]

    body.append(f"Test command: {tests_command}.")
    body.append(f"Build command: {build_command}.")

    return "\n".join(header + body) + "\n"


def build_agent5_dataset(
    *,
    dataset_root: Path,
    scenario_id: str,
    release_id: str,
    evidence: Dict[str, Any],
    stage_results: Dict[str, Any],
    previous_report: Optional[Dict[str, Any]],
) -> None:
    heuristics = evidence["heuristics"]
    previous_context = derive_agent4_context(previous_report, stage_results)

    requirement_ids = ["CI-REQ-AUTOMATED-TESTS", "CI-REQ-CONTAINER-BUILD"]
    if heuristics["deployment_files_changed"]:
        requirement_ids.append("CI-REQ-DEPLOYMENT-PACKAGE")
    if heuristics["application_files_changed"]:
        requirement_ids.append("CI-REQ-APPLICATION-CHANGES")
    if heuristics["workflow_files_changed"]:
        requirement_ids.append("CI-REQ-PIPELINE-CHANGES")

    requirements_rows = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "requirement_id": req_id,
            "description": req_id.replace("CI-REQ-", "").replace("-", " ").title(),
            "priority": "HIGH",
            "mandatory_for_phase5": "true",
        }
        for req_id in requirement_ids
    ]

    mapped_reqs = ",".join(requirement_ids)
    test_cases_rows = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": "TC-CI-TEST",
            "mapped_requirement_ids": mapped_reqs,
            "criticality": "HIGH",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": "TC-CONTAINER-BUILD",
            "mapped_requirement_ids": mapped_reqs,
            "criticality": "HIGH",
        },
    ]

    traceability_rows = []
    for req_id in requirement_ids:
        traceability_rows.append(
            {
                "scenario_id": scenario_id,
                "release_id": release_id,
                "requirement_id": req_id,
                "test_case_id": "TC-CI-TEST",
            }
        )
        traceability_rows.append(
            {
                "scenario_id": scenario_id,
                "release_id": release_id,
                "requirement_id": req_id,
                "test_case_id": "TC-CONTAINER-BUILD",
            }
        )

    tests_status = normalize_status(stage_results.get("tests", {}).get("status"))
    build_status = normalize_status(stage_results.get("build", {}).get("status"))

    execution_rows = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": "TC-CI-TEST",
            "status": tests_status,
            "executed": "true" if tests_status != "NOT_RUN" else "false",
            "retest_required": "false",
            "retest_completed": "true" if tests_status == "PASS" else "false",
        },
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "test_case_id": "TC-CONTAINER-BUILD",
            "status": build_status,
            "executed": "true" if build_status != "NOT_RUN" else "false",
            "retest_required": "false",
            "retest_completed": "true" if build_status == "PASS" else "false",
        },
    ]

    all_green = tests_and_build_green(stage_results)
    defect_rows = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "defect_id": "CI-DEF-001",
            "severity": "low" if all_green else "high",
            "status": "closed" if all_green else "open",
        }
    ]

    release_calendar_rows = [
        {
            "scenario_id": scenario_id,
            "release_id": release_id,
            "environment": "TEST",
            "phase5_window_start": utc_now(),
            "phase5_window_end": utc_now(),
            "target_phase5_gate": "pending-human-approval",
        }
    ]

    write_csv(
        dataset_root / "requirements_master.csv",
        [
            "scenario_id",
            "release_id",
            "requirement_id",
            "description",
            "priority",
            "mandatory_for_phase5",
        ],
        requirements_rows,
    )
    write_csv(
        dataset_root / "test_cases_master.csv",
        [
            "scenario_id",
            "release_id",
            "test_case_id",
            "mapped_requirement_ids",
            "criticality",
        ],
        test_cases_rows,
    )
    write_csv(
        dataset_root / "traceability_matrix.csv",
        ["scenario_id", "release_id", "requirement_id", "test_case_id"],
        traceability_rows,
    )
    write_csv(
        dataset_root / "test_execution_results.csv",
        [
            "scenario_id",
            "release_id",
            "test_case_id",
            "status",
            "executed",
            "retest_required",
            "retest_completed",
        ],
        execution_rows,
    )
    write_csv(
        dataset_root / "defect_register.csv",
        ["scenario_id", "release_id", "defect_id", "severity", "status"],
        defect_rows,
    )
    write_csv(
        dataset_root / "phase5_release_calendar.csv",
        [
            "scenario_id",
            "release_id",
            "environment",
            "phase5_window_start",
            "phase5_window_end",
            "target_phase5_gate",
        ],
        release_calendar_rows,
    )
    write_text(
        dataset_root / "test_analysis_emails" / f"{scenario_id}.txt",
        build_agent5_email_text(
            previous_context=previous_context,
            stage_results=stage_results,
        ),
    )
    if previous_context is not None:
        write_json(
            dataset_root / "agent4_context" / f"{scenario_id}.json",
            previous_context,
        )


def run_agent4_analysis(
    *,
    dataset_root: Path,
    scenario_id: str,
    release_id: str,
    use_llm: bool,
) -> Dict[str, Any]:
    from agent4.lc_pipeline import LangChainAgent4Pipeline, LCPipelineConfig

    base_llm_generate = maybe_get_llm_generate() if use_llm else None
    llm_generate, llm_diagnostics = make_llm_diagnostics_wrapper(base_llm_generate)
    pipeline = LangChainAgent4Pipeline(
        config=LCPipelineConfig(
            dataset_root=str(dataset_root),
            source_adapter_kind="structured_dataset",
            use_llm_summary=use_llm,
            strict_schema=True,
        ),
        llm_generate=llm_generate,
    )
    validation = pipeline.validate_dataset()
    payload = pipeline.assess_scenario(scenario_id=scenario_id, release_id=release_id)
    llm_diagnostics["decision_type"] = payload.get("decision_type")
    llm_diagnostics["fallback_suspected"] = bool(
        use_llm
        and llm_diagnostics["configured"]
        and llm_diagnostics["called"]
        and payload.get("decision_type") != "deterministic_with_llm_summary"
    )
    return {
        "agent": "agent4",
        "dataset_root": str(dataset_root),
        "scenario_id": scenario_id,
        "release_id": release_id,
        "validation": validation,
        "llm_diagnostics": llm_diagnostics,
        "payload": payload,
    }


def run_agent5_analysis(
    *,
    dataset_root: Path,
    scenario_id: str,
    release_id: str,
    use_llm: bool,
) -> Dict[str, Any]:
    from agent5.lc_pipeline import LangChainAgent5Pipeline, LCPipelineConfig

    base_llm_generate = maybe_get_llm_generate() if use_llm else None
    llm_generate, llm_diagnostics = make_llm_diagnostics_wrapper(base_llm_generate)
    pipeline = LangChainAgent5Pipeline(
        config=LCPipelineConfig(
            dataset_root=str(dataset_root),
            use_llm_summary=use_llm,
            strict_schema=True,
        ),
        llm_generate=llm_generate,
    )
    validation = pipeline.validate_dataset()
    payload = pipeline.assess_scenario(scenario_id=scenario_id, release_id=release_id)
    llm_diagnostics["decision_type"] = payload.get("decision_type")
    llm_diagnostics["fallback_suspected"] = bool(
        use_llm
        and llm_diagnostics["configured"]
        and llm_diagnostics["called"]
        and payload.get("decision_type") != "deterministic_with_llm_summary"
    )
    return {
        "agent": "agent5",
        "dataset_root": str(dataset_root),
        "scenario_id": scenario_id,
        "release_id": release_id,
        "validation": validation,
        "llm_diagnostics": llm_diagnostics,
        "payload": payload,
    }


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    phase_meta = PHASE_METADATA[args.phase]
    head_sha = run_command(["git", "rev-parse", args.head_ref], allow_failure=True)
    release_id = short_sha(head_sha or "local-build")
    evidence = build_evidence_bundle(args)
    stage_results = load_stage_results(args)
    previous_report = load_previous_report(args.previous_report)

    phase_dir = Path(args.output_dir) / args.phase
    dataset_root = phase_dir / f"{phase_meta['agent']}_ci_dataset"
    scenario_id = phase_meta["scenario_id"]

    if args.phase == "pre-test":
        build_agent4_dataset(
            dataset_root=dataset_root,
            scenario_id=scenario_id,
            release_id=release_id,
            evidence=evidence,
        )
        agent_output = run_agent4_analysis(
            dataset_root=dataset_root,
            scenario_id=scenario_id,
            release_id=release_id,
            use_llm=args.use_llm,
        )
    else:
        build_agent5_dataset(
            dataset_root=dataset_root,
            scenario_id=scenario_id,
            release_id=release_id,
            evidence=evidence,
            stage_results=stage_results,
            previous_report=previous_report,
        )
        agent_output = run_agent5_analysis(
            dataset_root=dataset_root,
            scenario_id=scenario_id,
            release_id=release_id,
            use_llm=args.use_llm,
        )

    payload = agent_output["payload"]
    rule_findings = payload.get("rule_findings", {})
    triggered_rules = (
        rule_findings.get("triggered_rule_codes", [])
        if isinstance(rule_findings, dict)
        else []
    )

    recommendation = {
        "decision": payload.get("decision", "HOLD"),
        "decision_type": payload.get("decision_type", "unknown"),
        "summary": payload.get("summary", "No summary returned by agent."),
        "agent_human_action": payload.get("human_action"),
        "human_gate": phase_meta["human_gate"],
        "final_gate_mode": "human_approval_required",
        "triggered_rules": triggered_rules,
        "confidence": payload.get("confidence"),
        "policy_version": payload.get("policy_version"),
    }

    previous_decision = None
    if previous_report:
        previous_payload = previous_report.get("agent_output", {}).get("payload")
        if isinstance(previous_payload, dict):
            previous_decision = previous_payload.get("decision")

    llm_diagnostics = agent_output.get("llm_diagnostics", {})

    return {
        "draft": False,
        "generated_at_utc": utc_now(),
        "phase": args.phase,
        "phase_metadata": phase_meta,
        "event_name": args.event_name,
        "pr_number": args.pr_number,
        "git": {
            "base_ref": args.base_ref or "HEAD~1",
            "head_ref": args.head_ref,
            "head_sha": head_sha,
            "diff_stat": evidence["diff_stat"],
        },
        "evidence": evidence,
        "stage_results": stage_results,
        "previous_stage": {
            "available": previous_report is not None,
            "decision": previous_decision,
            "path": args.previous_report,
        },
        "ci_dataset": {
            "path": str(dataset_root),
            "scenario_id": scenario_id,
            "release_id": release_id,
        },
        "agent_output": agent_output,
        "recommendation": recommendation,
        "llm": {
            "requested": args.use_llm,
            "configured": bool(os.environ.get("OPENROUTER_API_KEY")),
            "model": llm_diagnostics.get("model") or os.environ.get("OPENROUTER_MODEL", "").strip() or "openai/gpt-oss-20b:free",
            "called": bool(llm_diagnostics.get("called")),
            "fallback_suspected": bool(llm_diagnostics.get("fallback_suspected")),
            "error": llm_diagnostics.get("error"),
            "raw_response_preview": llm_diagnostics.get("raw_response_preview"),
            "agent_decision_type": payload.get("decision_type"),
        },
        "implementation_status": {
            "ci_evidence_collection": "ready",
            "ci_dataset_synthesis": "ready",
            "agent_invocation": "ready",
            "hard_gating": "pending_human_policy",
        },
    }


def render_markdown(report: Dict[str, Any]) -> str:
    recommendation = report["recommendation"]
    evidence = report["evidence"]
    payload = report["agent_output"]["payload"]
    event_context = evidence.get("event_context", {})

    lines = [
        f"# Hitachi CI Gate Report: {report['phase']}",
        "",
        f"- Agent called: `{report['phase_metadata']['agent']}`",
        f"- Purpose: {report['phase_metadata']['purpose']}",
        f"- Event: `{report['event_name']}`",
        f"- Recommendation: `{recommendation['decision']}`",
        f"- Decision type: `{recommendation['decision_type']}`",
        f"- Confidence: `{recommendation['confidence'] or 'n/a'}`",
        f"- Policy version: `{recommendation['policy_version'] or 'n/a'}`",
        f"- Human gate: {recommendation['human_gate']}",
        f"- Changed files: `{evidence['counts']['changed_files']}`",
        f"- Relevant documents: `{evidence['counts']['relevant_documents']}`",
        "",
    ]

    if event_context.get("title"):
        lines.extend(
            [
                "## Change Request Context",
                "",
                f"- Title: {event_context['title']}",
            ]
        )
        if event_context.get("target_branch"):
            lines.append(f"- Target branch: `{event_context['target_branch']}`")
        commit_messages = event_context.get("commit_messages") or []
        if commit_messages:
            lines.append("Recent commits:")
            for item in commit_messages[:4]:
                subject = item.get("subject")
                sha = short_sha(item.get("sha", ""))
                if subject:
                    lines.append(f"- `{sha}` {subject}")
        lines.append("")

    lines.extend(
        [
            "## Agent Summary",
            "",
            str(recommendation["summary"]),
            "",
        ]
    )

    if recommendation.get("agent_human_action"):
        lines.append(f"Agent next action: {recommendation['agent_human_action']}")
        lines.append("")

    triggered_rules = recommendation.get("triggered_rules") or []
    lines.append("Triggered rules:")
    if triggered_rules:
        for item in triggered_rules:
            lines.append(f"- `{item}`")
    else:
        lines.append("- none")
    lines.append("")

    if report["phase"] == "pre-prod":
        lines.extend(
            [
                "## Verification Inputs",
                "",
                f"- Tests status: `{report['stage_results']['tests']['status']}`",
                f"- Build status: `{report['stage_results']['build']['status']}`",
            ]
        )
        if report["previous_stage"]["available"]:
            lines.append(
                f"- Previous stage decision: `{report['previous_stage']['decision'] or 'unknown'}`"
            )
        lines.append("")

    lines.extend(
        [
            "## Dataset + Output",
            "",
            f"- Temporary CI dataset: `{report['ci_dataset']['path']}`",
            f"- Scenario id: `{report['ci_dataset']['scenario_id']}`",
            f"- Release id: `{report['ci_dataset']['release_id']}`",
            "",
            "## Evidence Bundle",
            "",
            "Relevant documents:",
        ]
    )

    for path in evidence["relevant_documents"][:20]:
        lines.append(f"- `{path}`")
    if len(evidence["relevant_documents"]) > 20:
        lines.append(
            f"- ... and {len(evidence['relevant_documents']) - 20} more document(s)"
        )
    lines.append("")

    lines.append("Changed files:")
    for path in evidence["changed_files"][:20]:
        lines.append(f"- `{path}`")
    if len(evidence["changed_files"]) > 20:
        lines.append(f"- ... and {len(evidence['changed_files']) - 20} more changed file(s)")
    lines.append("")

    blocker_markers = evidence["heuristics"]["blocker_markers"]
    if blocker_markers:
        lines.append("Detected review markers:")
        for item in blocker_markers[:8]:
            lines.append(
                f"- `{item['marker']}` in `{item['path']}` line `{item['line']}`: {item['snippet']}"
            )
        lines.append("")

    if report["llm"]["requested"]:
        lines.extend(
            [
                "## LLM Layer",
                "",
                f"- Requested: `{report['llm']['requested']}`",
                f"- Configured: `{report['llm']['configured']}`",
                f"- Model: `{report['llm']['model'] or 'n/a'}`",
                f"- Called: `{report['llm']['called']}`",
                f"- Agent decision type: `{report['llm']['agent_decision_type'] or 'n/a'}`",
            ]
        )
        if report["llm"].get("fallback_suspected"):
            lines.append(f"- Fallback suspected: `{report['llm']['fallback_suspected']}`")
        if report["llm"].get("error"):
            lines.append(f"- Error: `{report['llm']['error']}`")
        raw_preview = report["llm"].get("raw_response_preview")
        if raw_preview and report["llm"].get("fallback_suspected"):
            lines.append("- Raw response preview:")
            lines.append("")
            lines.append("```text")
            lines.append(str(raw_preview))
            lines.append("```")
        lines.append("")

    reasons = payload.get("reasons", [])
    if isinstance(reasons, list) and reasons:
        lines.append("## Reasons")
        lines.append("")
        for reason in reasons[:6]:
            if not isinstance(reason, dict):
                continue
            title = reason.get("title") or "Untitled reason"
            detail = reason.get("detail") or ""
            code = reason.get("rule_code")
            if code:
                lines.append(f"- {title} (`{code}`): {detail}")
            else:
                lines.append(f"- {title}: {detail}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def maybe_append_step_summary(markdown: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as handle:
        handle.write(markdown)
        if not markdown.endswith("\n"):
            handle.write("\n")


def main() -> None:
    args = parse_args()
    report = build_report(args)
    markdown = render_markdown(report)

    phase_dir = Path(args.output_dir) / args.phase
    phase_dir.mkdir(parents=True, exist_ok=True)

    write_json(phase_dir / "ci_report.json", report)
    write_text(phase_dir / "ci_report.md", markdown)
    write_text(
        phase_dir / "changed_files.txt",
        "\n".join(report["evidence"]["changed_files"]) + "\n",
    )
    write_text(
        phase_dir / "diff_stat.txt",
        str(report["git"]["diff_stat"]).rstrip() + "\n",
    )
    write_json(
        phase_dir / "agent_payload.json",
        report["agent_output"]["payload"],
    )
    write_json(
        phase_dir / "evidence_bundle.json",
        {
            "git": report["git"],
            "evidence": report["evidence"],
            "stage_results": report["stage_results"],
            "previous_stage": report["previous_stage"],
        },
    )

    if args.write_step_summary:
        maybe_append_step_summary(markdown)

    print(json.dumps(report["recommendation"], indent=2))


if __name__ == "__main__":
    main()
