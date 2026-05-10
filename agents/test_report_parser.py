"""
Parser for pytest-json-report output.

Converts the raw JSON produced by `pytest --json-report` into a compact
structured summary that the subject-repo pipeline can include in its LLM
prompt and in the CI report artifact.

Usage:
    from agents.test_report_parser import parse_pytest_json

    with open("test-report.json") as f:
        data = json.load(f)
    summary = parse_pytest_json(data)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


_MAX_FAILED_TESTS = 10
_MAX_MESSAGE_CHARS = 600


def parse_pytest_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a structured summary from a pytest-json-report payload."""
    if not isinstance(data, dict):
        return _empty_summary("Invalid report format.")

    raw_summary = data.get("summary") or {}
    tests: List[Dict[str, Any]] = data.get("tests") or []

    total = int(raw_summary.get("total", len(tests)))
    passed = int(raw_summary.get("passed", 0))
    failed = int(raw_summary.get("failed", 0))
    error = int(raw_summary.get("error", 0))
    skipped = int(raw_summary.get("skipped", 0))
    duration = round(float(data.get("duration", 0.0)), 2)

    failed_tests = [
        {
            "name": t.get("nodeid", "unknown"),
            "message": _extract_failure_message(t),
        }
        for t in tests
        if t.get("outcome") in ("failed", "error")
    ][:_MAX_FAILED_TESTS]

    all_passed = failed == 0 and error == 0

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "error": error,
        "skipped": skipped,
        "duration_s": duration,
        "all_passed": all_passed,
        "failed_tests": failed_tests,
        "available": True,
        "parse_error": None,
    }


def _extract_failure_message(test: Dict[str, Any]) -> str:
    call = test.get("call") or {}
    longrepr = call.get("longrepr", "")
    if isinstance(longrepr, str):
        return longrepr.strip()[:_MAX_MESSAGE_CHARS]
    if isinstance(longrepr, dict):
        reprcrash = longrepr.get("reprcrash") or {}
        return str(reprcrash.get("message", longrepr))[:_MAX_MESSAGE_CHARS]
    return str(longrepr)[:_MAX_MESSAGE_CHARS]


def _empty_summary(reason: str) -> Dict[str, Any]:
    return {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "error": 0,
        "skipped": 0,
        "duration_s": 0.0,
        "all_passed": False,
        "failed_tests": [],
        "available": False,
        "parse_error": reason,
    }


def format_test_summary_for_prompt(summary: Dict[str, Any]) -> str:
    """Render the test summary as a compact string suitable for an LLM prompt."""
    if not summary.get("available"):
        return f"Test results: NOT AVAILABLE ({summary.get('parse_error', 'unknown reason')})"

    status = "ALL PASSED" if summary["all_passed"] else "FAILED"
    lines = [
        f"Test results: {status}",
        f"  Total: {summary['total']}  Passed: {summary['passed']}  "
        f"Failed: {summary['failed']}  Error: {summary['error']}  "
        f"Skipped: {summary['skipped']}  Duration: {summary['duration_s']}s",
    ]

    if summary["failed_tests"]:
        lines.append("  Failed tests:")
        for t in summary["failed_tests"]:
            lines.append(f"    - {t['name']}")
            if t["message"]:
                first_line = t["message"].splitlines()[0][:200]
                lines.append(f"      {first_line}")

    return "\n".join(lines)
