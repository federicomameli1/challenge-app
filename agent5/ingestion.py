"""
Phase 5 structured ingestion layer.

This module reads raw Phase 5 test-analysis evidence for a single scenario and
returns one source-traceable bundle for downstream normalization and policy.

Supported dataset layout (default: synthetic_data/phase5/v1):
- requirements_master.csv
- test_cases_master.csv
- traceability_matrix.csv
- test_execution_results.csv
- defect_register.csv
- phase5_release_calendar.csv (preferred) OR release_calendar.csv
- optional phase5_manifest.json
- optional phase5_decision_labels.csv
- optional test_analysis_emails/<scenario_id>.txt
- optional agent4_context/<scenario_id>.json
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


class IngestionError(Exception):
    """Raised when required ingestion inputs are missing or inconsistent."""


@dataclass(frozen=True)
class SourceRef:
    """Reference to the origin of an ingested artifact."""

    source_type: str
    path: str


@dataclass
class RawInputBundle:
    """
    Canonical output of Phase 5 ingestion for one scenario.

    This layer intentionally preserves raw content and provenance references.
    """

    scenario_id: str
    release_id: str
    environment: str
    release_metadata: Dict[str, str]

    requirements: List[Dict[str, str]]
    test_cases: List[Dict[str, str]]
    traceability_matrix: List[Dict[str, str]]
    test_execution_results: List[Dict[str, str]]
    defect_register: List[Dict[str, str]]

    agent4_context: Optional[Dict[str, Any]]
    test_analysis_email_thread: str

    source_references: Dict[str, SourceRef] = field(default_factory=dict)
    missing_optional_artifacts: List[str] = field(default_factory=list)


class Phase5Ingestion:
    """
    Data ingestion façade for Phase 5 test-analysis scenarios.

    Required files:
      - requirements_master.csv
      - test_cases_master.csv
      - traceability_matrix.csv
      - test_execution_results.csv
      - defect_register.csv
      - phase5_release_calendar.csv OR release_calendar.csv
    """

    REQUIRED_FILES = (
        "requirements_master.csv",
        "test_cases_master.csv",
        "traceability_matrix.csv",
        "test_execution_results.csv",
        "defect_register.csv",
    )

    OPTIONAL_FILES = (
        "phase5_manifest.json",
        "phase5_decision_labels.csv",
    )

    CALENDAR_CANDIDATES = (
        "phase5_release_calendar.csv",
        "release_calendar.csv",
    )

    def __init__(self, dataset_root: str | Path = "synthetic_data/phase5/v1") -> None:
        self.dataset_root = Path(dataset_root)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def validate_dataset(self) -> Dict[str, Any]:
        """
        Validate minimum dataset structure and return diagnostic snapshot.
        """
        report: Dict[str, Any] = {
            "dataset_root": str(self.dataset_root),
            "exists": self.dataset_root.exists(),
            "missing_required": [],
            "missing_optional": [],
            "present_optional": [],
            "notes": [],
        }

        if not self.dataset_root.exists():
            report["missing_required"] = list(self.REQUIRED_FILES) + [
                "phase5_release_calendar.csv|release_calendar.csv"
            ]
            report["missing_optional"] = list(self.OPTIONAL_FILES)
            return report

        for name in self.REQUIRED_FILES:
            if not (self.dataset_root / name).exists():
                report["missing_required"].append(name)

        calendar_path = self._resolve_calendar_path(raise_if_missing=False)
        if calendar_path is None:
            report["missing_required"].append(
                "phase5_release_calendar.csv|release_calendar.csv"
            )
        else:
            report["notes"].append(f"calendar_selected={calendar_path.name}")

        for name in self.OPTIONAL_FILES:
            p = self.dataset_root / name
            if p.exists():
                report["present_optional"].append(name)
            else:
                report["missing_optional"].append(name)

        # Optional evidence directories
        email_dir = self.dataset_root / "test_analysis_emails"
        a4_dir = self.dataset_root / "agent4_context"
        report["notes"].append(
            "has_test_analysis_emails_dir={0}".format(email_dir.exists())
        )
        report["notes"].append("has_agent4_context_dir={0}".format(a4_dir.exists()))

        return report

    def list_scenarios(self) -> List[Dict[str, str]]:
        """
        List scenario rows from release calendar.
        """
        calendar_path = self._resolve_calendar_path(raise_if_missing=True)
        rows = self._read_csv(calendar_path)

        scenarios: List[Dict[str, str]] = []
        for row in rows:
            scenarios.append(
                {
                    "scenario_id": (row.get("scenario_id") or "").strip(),
                    "release_id": (row.get("release_id") or "").strip(),
                    "environment": ((row.get("environment") or "TEST").strip() or "TEST"),
                    "target_phase5_gate": (row.get("target_phase5_gate") or "").strip(),
                }
            )
        return scenarios

    def ingest(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> RawInputBundle:
        """
        Ingest all Phase 5 evidence for one scenario.
        """
        sid = (scenario_id or "").strip()
        if not sid:
            raise IngestionError("scenario_id is required and cannot be empty.")

        self._assert_minimum_dataset()

        calendar_path = self._resolve_calendar_path(raise_if_missing=True)

        requirements_path = self.dataset_root / "requirements_master.csv"
        test_cases_path = self.dataset_root / "test_cases_master.csv"
        traceability_path = self.dataset_root / "traceability_matrix.csv"
        execution_path = self.dataset_root / "test_execution_results.csv"
        defect_path = self.dataset_root / "defect_register.csv"

        metadata = self._lookup_release_metadata(
            calendar_path=calendar_path,
            scenario_id=sid,
            release_id=release_id,
        )
        rid = metadata["release_id"]

        requirements = self._select_rows(
            path=requirements_path,
            scenario_id=sid,
            release_id=rid,
        )
        test_cases = self._select_rows(
            path=test_cases_path,
            scenario_id=sid,
            release_id=rid,
        )
        traceability = self._select_rows(
            path=traceability_path,
            scenario_id=sid,
            release_id=rid,
            must_match_scenario=True,
        )
        execution = self._select_rows(
            path=execution_path,
            scenario_id=sid,
            release_id=rid,
            must_match_scenario=True,
        )
        defects = self._select_rows(
            path=defect_path,
            scenario_id=sid,
            release_id=rid,
            must_match_scenario=True,
        )

        # Optional A4 continuity context.
        a4_ctx_path = self.dataset_root / "agent4_context" / f"{sid}.json"
        if a4_ctx_path.exists():
            a4_context = self._read_json(a4_ctx_path)
        else:
            a4_context = None

        # Optional email/narrative context.
        email_path = self.dataset_root / "test_analysis_emails" / f"{sid}.txt"
        if email_path.exists():
            email_text = self._read_text(email_path)
        else:
            email_text = ""

        missing_optional: List[str] = []
        if not email_path.exists():
            missing_optional.append(str(email_path))
        if not a4_ctx_path.exists():
            missing_optional.append(str(a4_ctx_path))

        refs: Dict[str, SourceRef] = {
            "release_metadata": SourceRef("csv", str(calendar_path)),
            "requirements": SourceRef("csv", str(requirements_path)),
            "test_cases": SourceRef("csv", str(test_cases_path)),
            "traceability_matrix": SourceRef("csv", str(traceability_path)),
            "test_execution_results": SourceRef("csv", str(execution_path)),
            "defect_register": SourceRef("csv", str(defect_path)),
            "agent4_context": SourceRef(
                "json_optional",
                str(a4_ctx_path) if a4_ctx_path.exists() else "missing:agent4_context",
            ),
            "test_analysis_email_thread": SourceRef(
                "txt_optional",
                str(email_path) if email_path.exists() else "missing:test_analysis_email",
            ),
        }

        return RawInputBundle(
            scenario_id=sid,
            release_id=rid,
            environment=metadata.get("environment", "TEST") or "TEST",
            release_metadata=metadata,
            requirements=requirements,
            test_cases=test_cases,
            traceability_matrix=traceability,
            test_execution_results=execution,
            defect_register=defects,
            agent4_context=a4_context,
            test_analysis_email_thread=email_text,
            source_references=refs,
            missing_optional_artifacts=missing_optional,
        )

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def _assert_minimum_dataset(self) -> None:
        if not self.dataset_root.exists():
            raise IngestionError(f"Dataset root not found: {self.dataset_root}")

        missing = [
            name
            for name in self.REQUIRED_FILES
            if not (self.dataset_root / name).exists()
        ]
        if missing:
            raise IngestionError(
                "Dataset is missing required files under {0}: {1}".format(
                    self.dataset_root, ", ".join(missing)
                )
            )

        if self._resolve_calendar_path(raise_if_missing=False) is None:
            raise IngestionError(
                "Missing release calendar. Expected one of: "
                "phase5_release_calendar.csv, release_calendar.csv"
            )

    def _resolve_calendar_path(self, raise_if_missing: bool) -> Optional[Path]:
        for name in self.CALENDAR_CANDIDATES:
            p = self.dataset_root / name
            if p.exists():
                return p

        if raise_if_missing:
            raise IngestionError(
                "Missing release calendar. Expected one of: "
                + ", ".join(self.CALENDAR_CANDIDATES)
            )
        return None

    def _lookup_release_metadata(
        self,
        calendar_path: Path,
        scenario_id: str,
        release_id: Optional[str],
    ) -> Dict[str, str]:
        rows = self._read_csv(calendar_path)
        candidates = [
            r for r in rows if (r.get("scenario_id") or "").strip() == scenario_id
        ]

        if not candidates:
            raise IngestionError(
                "Scenario `{0}` not found in release calendar: {1}".format(
                    scenario_id, calendar_path
                )
            )

        if release_id:
            rid = release_id.strip()
            filtered = [r for r in candidates if (r.get("release_id") or "").strip() == rid]
            if not filtered:
                known = sorted({(r.get("release_id") or "").strip() for r in candidates})
                raise IngestionError(
                    "Scenario `{0}` exists but not with release_id `{1}`. Known: {2}".format(
                        scenario_id, rid, ", ".join([k for k in known if k]) or "none"
                    )
                )
            chosen = filtered[0]
        else:
            chosen = candidates[0]

        return {
            "scenario_id": (chosen.get("scenario_id") or "").strip(),
            "release_id": (chosen.get("release_id") or "").strip(),
            "environment": ((chosen.get("environment") or "TEST").strip() or "TEST"),
            "phase5_window_start": (chosen.get("phase5_window_start") or "").strip(),
            "phase5_window_end": (chosen.get("phase5_window_end") or "").strip(),
            "target_phase5_gate": (chosen.get("target_phase5_gate") or "").strip(),
        }

    def _select_rows(
        self,
        path: Path,
        scenario_id: str,
        release_id: str,
        must_match_scenario: bool = False,
    ) -> List[Dict[str, str]]:
        """
        Row selection strategy:
        - If file has scenario_id column -> filter by scenario_id.
        - If file has release_id column -> filter by release_id.
        - If neither key exists -> return all rows (global baseline table).
        - If must_match_scenario=True and scenario_id exists but no rows match -> error.
        """
        rows = self._read_csv(path)
        if not rows:
            if must_match_scenario:
                raise IngestionError(f"No rows found in required scenario-scoped table: {path}")
            return []

        has_scenario_key = any("scenario_id" in r for r in rows)
        has_release_key = any("release_id" in r for r in rows)

        selected = rows
        if has_scenario_key:
            selected = [
                r for r in selected if (r.get("scenario_id") or "").strip() == scenario_id
            ]
        if has_release_key:
            selected = [
                r for r in selected if (r.get("release_id") or "").strip() == release_id
            ]

        if must_match_scenario and has_scenario_key and not selected:
            raise IngestionError(
                "No rows found for scenario_id={0}, release_id={1} in {2}".format(
                    scenario_id, release_id, path
                )
            )

        # For baseline tables, fallback to all rows if filtering removed everything.
        if not selected and not must_match_scenario and not has_scenario_key:
            return rows
        return selected

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            raise IngestionError(f"Required file not found: {path}")
        return path.read_text(encoding="utf-8", errors="replace")

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise IngestionError(f"Required file not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IngestionError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise IngestionError(
                f"Expected JSON object in {path}, got {type(payload).__name__}"
            )
        return payload

    def _read_csv(self, path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            raise IngestionError(f"Required file not found: {path}")

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise IngestionError(f"CSV has no header row: {path}")

            out: List[Dict[str, str]] = []
            for row in reader:
                normalized = {
                    (k or "").strip(): (v or "").strip() for k, v in row.items()
                }
                out.append(normalized)
            return out


def ingest_scenario(
    scenario_id: str,
    dataset_root: str | Path = "synthetic_data/phase5/v1",
    release_id: Optional[str] = None,
) -> RawInputBundle:
    """
    Convenience one-shot ingestion helper.
    """
    return Phase5Ingestion(dataset_root=dataset_root).ingest(
        scenario_id=scenario_id,
        release_id=release_id,
    )
