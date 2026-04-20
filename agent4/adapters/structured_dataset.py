"""
Structured dataset adapter for Agent 4.

This adapter is intentionally thin: it reuses the existing `Phase4Ingestion`
implementation and exposes an adapter-style interface that can be composed with
other source adapters (e.g., docx bundles) later.

Design goals:
- Zero behavioral drift from current structured ingestion.
- Keep migration path to a generic adapter registry simple.
- Preserve current scenario-based contracts (`scenario_id`, `release_id`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..ingestion import IngestionError, Phase4Ingestion, RawInputBundle


class AdapterError(Exception):
    """Raised when adapter-level validation or ingestion fails."""


@dataclass(frozen=True)
class AdapterDescriptor:
    """Metadata describing the adapter and source root."""

    adapter_name: str
    source_root: str
    source_type: str = "structured_dataset"


class StructuredDatasetAdapter:
    """
    Adapter over the existing `Phase4Ingestion` flow.

    Expected source shape:
      - requirements_master.csv
      - release_calendar.csv
      - phase4_modules_versions.csv OR modules_versions.csv
      - dev_deploy_logs/<scenario_id>.log
      - service_health_reports/<scenario_id>.json
      - dev_blockers_emails/<scenario_id>.txt
    """

    ADAPTER_NAME = "structured_dataset"

    def __init__(self, source_root: str | Path) -> None:
        self.source_root = Path(source_root)
        self._ingestion = Phase4Ingestion(dataset_root=self.source_root)

    # ---------------------------------------------------------------------
    # Capability / metadata
    # ---------------------------------------------------------------------

    @property
    def descriptor(self) -> AdapterDescriptor:
        return AdapterDescriptor(
            adapter_name=self.ADAPTER_NAME,
            source_root=str(self.source_root),
        )

    def can_ingest(self) -> bool:
        """
        Fast capability check: true when the source root exists and has the
        minimum required structured files.
        """
        report = self._ingestion.validate_dataset()
        return (
            bool(report.get("exists")) and len(report.get("missing_required", [])) == 0
        )

    def validate_source(self) -> Dict[str, Any]:
        """
        Return a normalized validation report for adapter orchestration.
        """
        report = self._ingestion.validate_dataset()
        return {
            "adapter_name": self.ADAPTER_NAME,
            "source_root": str(self.source_root),
            "exists": bool(report.get("exists", False)),
            "valid": bool(report.get("exists", False))
            and len(report.get("missing_required", [])) == 0,
            "missing_required": list(report.get("missing_required", [])),
            "missing_optional": list(report.get("missing_optional", [])),
            "present_optional": list(report.get("present_optional", [])),
        }

    # ---------------------------------------------------------------------
    # Scenario APIs
    # ---------------------------------------------------------------------

    def list_scenarios(self) -> List[Dict[str, str]]:
        """
        List available scenarios from `release_calendar.csv`.
        """
        try:
            return self._ingestion.list_scenarios()
        except IngestionError as exc:
            raise AdapterError(
                f"[{self.ADAPTER_NAME}] unable to list scenarios: {exc}"
            ) from exc

    def ingest(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> RawInputBundle:
        """
        Ingest one scenario and return the canonical RawInputBundle.
        """
        try:
            return self._ingestion.ingest(
                scenario_id=scenario_id, release_id=release_id
            )
        except IngestionError as exc:
            raise AdapterError(
                f"[{self.ADAPTER_NAME}] ingestion failed for scenario_id={scenario_id!r}: {exc}"
            ) from exc


def load_structured_bundle(
    *,
    source_root: str | Path,
    scenario_id: str,
    release_id: Optional[str] = None,
) -> RawInputBundle:
    """
    Convenience one-shot loader for structured datasets.
    """
    adapter = StructuredDatasetAdapter(source_root=source_root)
    return adapter.ingest(scenario_id=scenario_id, release_id=release_id)


__all__ = [
    "AdapterError",
    "AdapterDescriptor",
    "StructuredDatasetAdapter",
    "load_structured_bundle",
]
