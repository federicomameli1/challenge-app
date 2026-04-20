"""
Agent 4 data ingestion layer.

This module reads all raw Phase 4 evidence for a given `scenario_id` and returns
a single source-traceable bundle for downstream normalization and policy checks.
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
    Canonical output of ingestion for one scenario.

    This layer intentionally keeps content raw and preserves provenance references.
    """

    scenario_id: str
    release_id: str
    environment: str
    requirements: List[Dict[str, str]]
    module_versions: List[Dict[str, str]]
    release_metadata: Dict[str, str]
    deploy_log: str
    service_health_report: Dict[str, Any]
    blocker_email_thread: str
    source_references: Dict[str, SourceRef] = field(default_factory=dict)


class Phase4Ingestion:
    """
    Data ingestion façade for Agent 4.

    Expected dataset layout (default under `synthetic_data/v1`):
      - requirements_master.csv
      - phase4_modules_versions.csv OR modules_versions.csv
      - release_calendar.csv
      - dev_deploy_logs/<scenario_id>.log
      - service_health_reports/<scenario_id>.json
      - dev_blockers_emails/<scenario_id>.txt
      - optional scenario_manifest.json
    """

    REQUIRED_FILES = (
        "requirements_master.csv",
        "release_calendar.csv",
    )

    OPTIONAL_FILES = (
        "scenario_manifest.json",
        "phase4_modules_versions.csv",
        "modules_versions.csv",
    )

    def __init__(self, dataset_root: str | Path = "synthetic_data/v1") -> None:
        self.dataset_root = Path(dataset_root)

    # -------------------------
    # Public API
    # -------------------------

    def validate_dataset(self) -> Dict[str, Any]:
        """
        Validate the minimum dataset structure and return a diagnostic snapshot.
        """
        report: Dict[str, Any] = {
            "dataset_root": str(self.dataset_root),
            "exists": self.dataset_root.exists(),
            "missing_required": [],
            "missing_optional": [],
            "present_optional": [],
        }

        if not self.dataset_root.exists():
            report["missing_required"] = list(self.REQUIRED_FILES)
            report["missing_optional"] = list(self.OPTIONAL_FILES)
            return report

        for name in self.REQUIRED_FILES:
            if not (self.dataset_root / name).exists():
                report["missing_required"].append(name)

        for name in self.OPTIONAL_FILES:
            if (self.dataset_root / name).exists():
                report["present_optional"].append(name)
            else:
                report["missing_optional"].append(name)

        return report

    def list_scenarios(self) -> List[Dict[str, str]]:
        """
        Return release-calendar scenarios available for ingestion.
        """
        calendar_path = self.dataset_root / "release_calendar.csv"
        rows = self._read_csv(calendar_path)

        scenarios: List[Dict[str, str]] = []
        for row in rows:
            scenarios.append(
                {
                    "scenario_id": row.get("scenario_id", "").strip(),
                    "release_id": row.get("release_id", "").strip(),
                    "environment": row.get("environment", "").strip(),
                    "target_test_promotion": row.get(
                        "target_test_promotion", ""
                    ).strip(),
                }
            )
        return scenarios

    def ingest(
        self, scenario_id: str, release_id: Optional[str] = None
    ) -> RawInputBundle:
        """
        Ingest all raw evidence for a single scenario.

        Args:
            scenario_id: Scenario identifier (e.g., "S4-001").
            release_id: Optional release filter for additional consistency checking.
        """
        scenario_id = scenario_id.strip()
        if not scenario_id:
            raise IngestionError("scenario_id is required and cannot be empty.")

        self._assert_minimum_dataset()

        requirements_path = self.dataset_root / "requirements_master.csv"
        calendar_path = self.dataset_root / "release_calendar.csv"
        versions_path = self._resolve_versions_path()
        deploy_log_path = self.dataset_root / "dev_deploy_logs" / f"{scenario_id}.log"
        health_path = (
            self.dataset_root / "service_health_reports" / f"{scenario_id}.json"
        )
        email_path = self.dataset_root / "dev_blockers_emails" / f"{scenario_id}.txt"

        requirements = self._read_csv(requirements_path)
        release_metadata = self._lookup_release_metadata(
            calendar_path, scenario_id, release_id
        )
        module_versions = self._lookup_module_versions(
            versions_path=versions_path,
            scenario_id=scenario_id,
            release_id=release_metadata["release_id"],
            environment=release_metadata["environment"],
        )

        deploy_log = self._read_text(deploy_log_path)
        service_health_report = self._read_json(health_path)
        blocker_email_thread = self._read_text(email_path)

        refs = {
            "requirements": SourceRef(source_type="csv", path=str(requirements_path)),
            "release_metadata": SourceRef(source_type="csv", path=str(calendar_path)),
            "module_versions": SourceRef(source_type="csv", path=str(versions_path)),
            "deploy_log": SourceRef(source_type="log", path=str(deploy_log_path)),
            "service_health_report": SourceRef(
                source_type="json", path=str(health_path)
            ),
            "blocker_email_thread": SourceRef(source_type="txt", path=str(email_path)),
        }

        return RawInputBundle(
            scenario_id=scenario_id,
            release_id=release_metadata["release_id"],
            environment=release_metadata["environment"],
            requirements=requirements,
            module_versions=module_versions,
            release_metadata=release_metadata,
            deploy_log=deploy_log,
            service_health_report=service_health_report,
            blocker_email_thread=blocker_email_thread,
            source_references=refs,
        )

    # -------------------------
    # Internal helpers
    # -------------------------

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
                f"Dataset is missing required files under {self.dataset_root}: {', '.join(missing)}"
            )

    def _resolve_versions_path(self) -> Path:
        phase4_path = self.dataset_root / "phase4_modules_versions.csv"
        generic_path = self.dataset_root / "modules_versions.csv"

        if phase4_path.exists():
            return phase4_path
        if generic_path.exists():
            return generic_path

        raise IngestionError(
            "Missing module versions file. Expected `phase4_modules_versions.csv` "
            "or `modules_versions.csv`."
        )

    def _lookup_release_metadata(
        self, calendar_path: Path, scenario_id: str, release_id: Optional[str]
    ) -> Dict[str, str]:
        rows = self._read_csv(calendar_path)
        candidates = [
            r for r in rows if r.get("scenario_id", "").strip() == scenario_id
        ]

        if not candidates:
            raise IngestionError(
                f"Scenario `{scenario_id}` not found in release calendar: {calendar_path}"
            )

        if release_id:
            filtered = [
                r
                for r in candidates
                if r.get("release_id", "").strip() == release_id.strip()
            ]
            if not filtered:
                known = ", ".join(
                    sorted({r.get("release_id", "").strip() for r in candidates})
                )
                raise IngestionError(
                    f"Scenario `{scenario_id}` exists but not with release_id `{release_id}`. "
                    f"Known release_id values: {known or 'none'}"
                )
            chosen = filtered[0]
        else:
            chosen = candidates[0]

        return {
            "release_id": chosen.get("release_id", "").strip(),
            "scenario_id": chosen.get("scenario_id", "").strip(),
            "environment": chosen.get("environment", "").strip() or "DEV",
            "dev_window_start": chosen.get("dev_window_start", "").strip(),
            "dev_window_end": chosen.get("dev_window_end", "").strip(),
            "target_test_promotion": chosen.get("target_test_promotion", "").strip(),
        }

    def _lookup_module_versions(
        self, versions_path: Path, scenario_id: str, release_id: str, environment: str
    ) -> List[Dict[str, str]]:
        rows = self._read_csv(versions_path)

        selected: List[Dict[str, str]] = []
        for row in rows:
            if row.get("scenario_id", "").strip() != scenario_id:
                continue
            if row.get("release_id", "").strip() != release_id:
                continue

            env_value = row.get("environment", "").strip()
            if env_value and env_value != environment:
                continue

            selected.append(row)

        if not selected:
            raise IngestionError(
                f"No module versions found for scenario_id={scenario_id}, "
                f"release_id={release_id}, environment={environment} in {versions_path}"
            )

        return selected

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            raise IngestionError(f"Required file not found: {path}")
        return path.read_text(encoding="utf-8")

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise IngestionError(f"Required file not found: {path}")
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IngestionError(f"Invalid JSON in {path}: {exc}") from exc

        if not isinstance(content, dict):
            raise IngestionError(
                f"Expected JSON object in {path}, got {type(content).__name__}"
            )
        return content

    def _read_csv(self, path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            raise IngestionError(f"Required file not found: {path}")

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise IngestionError(f"CSV has no header row: {path}")

            rows: List[Dict[str, str]] = []
            for row in reader:
                normalized_row = {
                    (k or "").strip(): (v or "").strip() for k, v in row.items()
                }
                rows.append(normalized_row)
            return rows


def ingest_scenario(
    scenario_id: str,
    dataset_root: str | Path = "synthetic_data/v1",
    release_id: Optional[str] = None,
) -> RawInputBundle:
    """
    Convenience function for one-shot ingestion.
    """
    return Phase4Ingestion(dataset_root=dataset_root).ingest(
        scenario_id=scenario_id,
        release_id=release_id,
    )
