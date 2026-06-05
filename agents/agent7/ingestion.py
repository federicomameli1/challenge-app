"""
Phase 7 ingestion layer.

Reads deployment artifacts for Agent 7:
- Agent 6 handoff JSON (from BrainOrchestrator context)
- deployment_manifest.csv — deployment window and configuration
- production_release_calendar.csv — deployment schedule
- rollback_plan.csv — rollback procedure
- dependency_matrix.csv — production dependency versions
- staging_health_checks.csv — pre-deployment health probe results
- approval_workflow_manifest.csv — Nulla Osta sign-offs

Also supports standalone mode from file-based dataset.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from dataclasses import dataclass

from .models import DeploymentStatus, HealthProbeStatus, SourceRef
from .normalization import (
    NormalizedAgent6Context,
    NormalizedApprovalItem,
    NormalizedDependency,
    NormalizedDeploymentWindow,
    NormalizedHealthCheck,
    NormalizedPhase7Bundle,
)


class IngestionError(Exception):
    """Raised when Phase 7 artifact ingestion fails."""


# ---------------------------------------------------------------------------
# Raw bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawPhase7Bundle:
    scenario_id: str
    release_id: Optional[str]
    environment: str
    agent6_handoff: Optional[Mapping[str, Any]]
    deployment_manifest: Optional[Mapping[str, Any]]
    production_calendar: Optional[Mapping[str, Any]]
    rollback_plan: Optional[Mapping[str, Any]]
    dependencies: Tuple[Mapping[str, Any], ...]
    staging_health_checks: Tuple[Mapping[str, Any], ...]
    approval_items: Tuple[Mapping[str, Any], ...]


# ---------------------------------------------------------------------------
# Phase 7 Ingestion
# ---------------------------------------------------------------------------


class Phase7Ingestion:
    """
    Ingestion engine for Phase 7 production deployment gate.

    Supports two modes:
    - ingest_from_handoffs: BrainOrchestrator mode with A6 handoff payload
    - ingest: standalone file-based mode
    """

    REQUIRED_DEPLOYMENT_FILES = ["deployment_manifest.csv"]

    def __init__(self, dataset_root: str = "synthetic_data/phase7/v1") -> None:
        self.dataset_root = Path(dataset_root)

    def validate_dataset(self) -> Dict[str, Any]:
        if not self.dataset_root.exists():
            return {"exists": False, "missing_required": ["dataset_root"]}

        missing = [
            f for f in self.REQUIRED_DEPLOYMENT_FILES
            if not (self.dataset_root / f).exists()
        ]
        return {
            "exists": True,
            "missing_required": missing,
            "has_staging_health_checks": (self.dataset_root / "staging_health_checks.csv").exists(),
            "has_dependency_matrix": (self.dataset_root / "dependency_matrix.csv").exists(),
            "has_rollback_plan": (self.dataset_root / "rollback_plan.csv").exists(),
            "has_approval_manifest": (self.dataset_root / "approval_workflow_manifest.csv").exists(),
        }

    def list_scenarios(self) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        manifest = self.dataset_root / "deployment_manifest.csv"
        if not manifest.exists():
            return rows
        with manifest.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "scenario_id": row.get("scenario_id", "").strip(),
                    "release_id": row.get("release_id", "").strip(),
                })
        return rows

    def ingest(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> RawPhase7Bundle:
        """
        Standalone file-based ingestion for Phase 7.
        """
        manifest = self.dataset_root / "deployment_manifest.csv"
        if not manifest.exists():
            raise IngestionError(f"deployment_manifest.csv not found at {self.dataset_root}")

        deployments = self._read_csv_dict(manifest)
        deployment = self._find_by_scenario(deployments, scenario_id, release_id)
        if deployment is None:
            raise IngestionError(f"No deployment manifest for scenario {scenario_id}")

        env = str(deployment.get("environment", "PRODUCTION")).strip().upper()
        rid = self._coalesce(release_id, deployment.get("release_id"))

        all_deps = self._read_dependency_matrix()
        all_hc = self._read_staging_health_checks()

        all_approval_items = self._read_approval_items()

        return RawPhase7Bundle(
            scenario_id=scenario_id,
            release_id=rid,
            environment=env,
            agent6_handoff=None,
            deployment_manifest=dict(deployment),
            production_calendar=self._read_production_calendar(),
            rollback_plan=self._read_rollback_plan(),
            dependencies=tuple(r for r in all_deps if r.get("scenario_id", "").strip() == scenario_id),
            staging_health_checks=tuple(r for r in all_hc if r.get("scenario_id", "").strip() == scenario_id),
            approval_items=tuple(r for r in all_approval_items if r.get("scenario_id", "").strip() == scenario_id),
        )

    def ingest_from_handoffs(
        self,
        scenario_id: str,
        agent6_handoff: Optional[Mapping[str, Any]],
        release_id: Optional[str] = None,
        dataset_root: Optional[str] = None,
    ) -> RawPhase7Bundle:
        """
        BrainOrchestrator mode: ingest from A6 handoff payload + Phase 7 artifacts.
        """
        root = Path(dataset_root) if dataset_root else self.dataset_root

        manifest = root / "deployment_manifest.csv"
        deployment: Optional[Mapping[str, Any]] = None
        if manifest.exists():
            deployments = self._read_csv_dict(manifest)
            deployment = self._find_by_scenario(deployments, scenario_id, release_id)

        env = "PRODUCTION"
        rid = release_id
        if deployment:
            env = str(deployment.get("environment", "PRODUCTION")).strip().upper()
            rid = self._coalesce(release_id, deployment.get("release_id"))

        all_deps = self._read_dependency_matrix(root)
        all_hc = self._read_staging_health_checks(root)
        all_approval_items = self._read_approval_items(root)

        return RawPhase7Bundle(
            scenario_id=scenario_id,
            release_id=rid,
            environment=env,
            agent6_handoff=dict(agent6_handoff) if agent6_handoff else None,
            deployment_manifest=dict(deployment) if deployment else None,
            production_calendar=self._read_production_calendar(root),
            rollback_plan=self._read_rollback_plan(root),
            dependencies=tuple(r for r in all_deps if r.get("scenario_id", "").strip() == scenario_id),
            staging_health_checks=tuple(r for r in all_hc if r.get("scenario_id", "").strip() == scenario_id),
            approval_items=tuple(r for r in all_approval_items if r.get("scenario_id", "").strip() == scenario_id),
        )

    # -------------------------------------------------------------------------
    # CSV Readers
    # -------------------------------------------------------------------------

    def _read_csv_dict(self, path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            return []
        rows: List[Dict[str, str]] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return rows

    def _read_production_calendar(self, root: Optional[Path] = None) -> Optional[Mapping[str, Any]]:
        path = (root or self.dataset_root) / "production_release_calendar.csv"
        rows = self._read_csv_dict(path)
        return rows[0] if rows else None

    def _read_rollback_plan(self, root: Optional[Path] = None) -> Optional[Mapping[str, Any]]:
        path = (root or self.dataset_root) / "rollback_plan.csv"
        rows = self._read_csv_dict(path)
        return rows[0] if rows else None

    def _read_dependency_matrix(self, root: Optional[Path] = None) -> Tuple[Mapping[str, Any], ...]:
        path = (root or self.dataset_root) / "dependency_matrix.csv"
        return tuple(self._read_csv_dict(path))

    def _read_staging_health_checks(self, root: Optional[Path] = None) -> Tuple[Mapping[str, Any], ...]:
        path = (root or self.dataset_root) / "staging_health_checks.csv"
        return tuple(self._read_csv_dict(path))

    def _read_approval_items(self, root: Optional[Path] = None) -> Tuple[Mapping[str, Any], ...]:
        path = (root or self.dataset_root) / "approval_workflow_manifest.csv"
        raw_rows = self._read_csv_dict(path)
        items: List[Mapping[str, Any]] = []

        # Detect column-format vs item-format rows.
        # Column-format: has scenario_id + role-as-column (release_manager, deployment_engineer, etc.)
        ROLE_COLUMNS = {"release_manager", "deployment_engineer", "security_signoff",
                        "operations_lead", "supplier_qa_lead", "supplier_manager",
                        "customer_approver", "legal_review"}

        for row in raw_rows:
            col_roles = ROLE_COLUMNS & set(row.keys())
            if col_roles:
                # Expand each role column into an individual item for the target scenario
                sid = row.get("scenario_id", "").strip()
                rid = row.get("release_id", "").strip()
                for role in col_roles:
                    val = str(row.get(role, "")).strip().lower()
                    items.append({
                        "scenario_id": sid,
                        "release_id": rid,
                        "role": role,
                        "required": "true",
                        "signed": val,
                    })
            else:
                items.append(dict(row))
        return tuple(items)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _find_by_scenario(
        rows: List[Dict[str, str]],
        scenario_id: str,
        release_id: Optional[str],
    ) -> Optional[Mapping[str, str]]:
        for row in rows:
            sid = row.get("scenario_id", "").strip()
            rid = row.get("release_id", "").strip()
            if sid != scenario_id:
                continue
            if release_id and rid and rid != release_id:
                continue
            return row
        return None

    @staticmethod
    def _coalesce(*values: Optional[str]) -> Optional[str]:
        for v in values:
            if v and str(v).strip():
                return str(v).strip()
        return None


__all__ = [
    "IngestionError",
    "RawPhase7Bundle",
    "Phase7Ingestion",
]