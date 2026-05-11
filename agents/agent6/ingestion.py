"""
Phase 6 structured ingestion layer.

This module reads raw Phase 6 evidence for a single scenario and returns a
source-traceable bundle for downstream normalization and policy.

Agent 6's primary input source is the BrainOrchestrator handoff mechanism
(A4 and A5 HandoffEnvelope payloads). For standalone evaluation, it also
supports a Phase 6 structured dataset.

Dataset layout (synthetic_data/phase6/v1):
- phase6_release_calendar.csv
- phase6_decision_labels.csv
- approval_workflow_manifest.csv (per-scenario approval requirements)
- optional vdd_templates/ (reference VDD section templates)
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .models import SourceRef

# ---------------------------------------------------------------------------
# Raw input bundle (from file-based dataset for standalone use)
# ---------------------------------------------------------------------------


@dataclass
class RawPhase6Bundle:
    scenario_id: str
    release_id: str
    environment: str
    release_metadata: Dict[str, str]

    # From Agent 4 handoff (or dataset fallback)
    agent4_context: Optional[Dict[str, Any]] = None
    # From Agent 5 handoff (or dataset fallback)
    agent5_context: Optional[Dict[str, Any]] = None

    # Phase 6-specific
    approval_manifest: Optional[Dict[str, Any]] = None

    source_references: Dict[str, SourceRef] = field(default_factory=dict)
    missing_optional_artifacts: List[str] = field(default_factory=list)


class Phase6Ingestion:
    """
    Data ingestion façade for Phase 6 release-documentation scenarios.

    Agent 6 primarily derives data from A4 and A5 handoff payloads. This
    ingestion layer supports file-based dataset fallback for standalone
    evaluation and benchmark testing.

    Required files (for file-based mode):
      - phase6_release_calendar.csv

    Optional files:
      - phase6_decision_labels.csv
      - approval_workflow_manifest.csv
      - agent4_context/<scenario_id>.json
      - agent5_context/<scenario_id>.json
    """

    REQUIRED_FILES = ("phase6_release_calendar.csv",)

    OPTIONAL_FILES = (
        "phase6_decision_labels.csv",
        "approval_workflow_manifest.csv",
    )

    def __init__(self, dataset_root: str | Path = "synthetic_data/phase6/v1") -> None:
        self.dataset_root = Path(dataset_root)

    def validate_dataset(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "dataset_root": str(self.dataset_root),
            "exists": self.dataset_root.exists(),
            "missing_required": [],
            "missing_optional": [],
            "present_optional": [],
            "notes": [],
        }

        if not self.dataset_root.exists():
            report["missing_required"] = list(self.REQUIRED_FILES)
            report["missing_optional"] = list(self.OPTIONAL_FILES)
            return report

        for name in self.REQUIRED_FILES:
            if not (self.dataset_root / name).exists():
                report["missing_required"].append(name)

        for name in self.OPTIONAL_FILES:
            p = self.dataset_root / name
            if p.exists():
                report["present_optional"].append(name)
            else:
                report["missing_optional"].append(name)

        report["notes"].append(
            "has_agent4_context_dir={0}".format(
                (self.dataset_root / "agent4_context").exists()
            )
        )
        report["notes"].append(
            "has_agent5_context_dir={0}".format(
                (self.dataset_root / "agent5_context").exists()
            )
        )
        return report

    def list_scenarios(self) -> List[Dict[str, str]]:
        calendar_path = self.dataset_root / "phase6_release_calendar.csv"
        rows = self._read_csv(calendar_path)

        scenarios: List[Dict[str, str]] = []
        for row in rows:
            scenarios.append(
                {
                    "scenario_id": (row.get("scenario_id") or "").strip(),
                    "release_id": (row.get("release_id") or "").strip(),
                    "environment": (
                        (row.get("environment") or "RELEASE").strip() or "RELEASE"
                    ),
                    "agent4_scenario_id": (row.get("agent4_scenario_id") or "").strip(),
                    "agent5_scenario_id": (row.get("agent5_scenario_id") or "").strip(),
                }
            )
        return scenarios

    def ingest(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
        agent4_context: Optional[Dict[str, Any]] = None,
        agent5_context: Optional[Dict[str, Any]] = None,
    ) -> RawPhase6Bundle:
        """
        Ingest Phase 6 evidence for one scenario.

        Args:
            scenario_id: Phase 6 scenario identifier.
            release_id: Optional release override.
            agent4_context: Optional A4 handoff payload dict. If provided,
                this takes precedence over file-based A4 context.
            agent5_context: Optional A5 handoff payload dict. If provided,
                this takes precedence over file-based A5 context.
        """
        sid = (scenario_id or "").strip()
        if not sid:
            raise IngestionError("scenario_id is required and cannot be empty.")

        calendar_path = self.dataset_root / "phase6_release_calendar.csv"
        if not calendar_path.exists():
            raise IngestionError(f"Required file not found: {calendar_path}")

        metadata = self._lookup_release_metadata(
            calendar_path=calendar_path,
            scenario_id=sid,
            release_id=release_id,
        )
        rid = metadata["release_id"]

        # Load A4 context from file if not provided directly
        a4_ctx = agent4_context
        if a4_ctx is None:
            a4_path = self.dataset_root / "agent4_context" / f"{sid}.json"
            if a4_path.exists():
                a4_ctx = self._read_json(a4_path)

        # Load A5 context from file if not provided directly
        a5_ctx = agent5_context
        if a5_ctx is None:
            a5_path = self.dataset_root / "agent5_context" / f"{sid}.json"
            if a5_path.exists():
                a5_ctx = self._read_json(a5_path)

        # Load Phase 6 approval manifest
        approval_path = self.dataset_root / "approval_workflow_manifest.csv"
        approval_manifest: Optional[Dict[str, Any]] = None
        if approval_path.exists():
            rows = self._read_csv(approval_path)
            for row in rows:
                if (row.get("scenario_id") or "").strip() == sid:
                    approval_manifest = dict(row)
                    break

        refs: Dict[str, SourceRef] = {
            "release_metadata": SourceRef("csv", str(calendar_path)),
        }
        if a4_ctx is not None:
            refs["agent4_context"] = SourceRef(
                "handoff", str(self.dataset_root / "agent4_context" / f"{sid}.json")
            )
        if a5_ctx is not None:
            refs["agent5_context"] = SourceRef(
                "handoff", str(self.dataset_root / "agent5_context" / f"{sid}.json")
            )
        if approval_manifest is not None:
            refs["approval_manifest"] = SourceRef("csv", str(approval_path))

        missing_optional: List[str] = []
        if a4_ctx is None:
            missing_optional.append("agent4_context")
        if a5_ctx is None:
            missing_optional.append("agent5_context")

        return RawPhase6Bundle(
            scenario_id=sid,
            release_id=rid,
            environment=metadata.get("environment", "RELEASE") or "RELEASE",
            release_metadata=metadata,
            agent4_context=a4_ctx,
            agent5_context=a5_ctx,
            approval_manifest=approval_manifest,
            source_references=refs,
            missing_optional_artifacts=missing_optional,
        )

    def ingest_from_handoffs(
        self,
        scenario_id: str,
        release_id: Optional[str],
        agent4_handoff: Optional[Mapping[str, Any]],
        agent5_handoff: Optional[Mapping[str, Any]],
    ) -> RawPhase6Bundle:
        """
        Ingest Phase 6 evidence directly from BrainOrchestrator handoff payloads.

        This is the primary entry point when running within BrainOrchestrator.
        """
        sid = (scenario_id or "").strip()
        if not sid:
            raise IngestionError("scenario_id is required and cannot be empty.")

        rid = (release_id or "").strip() or sid
        env = "RELEASE"

        # Extract payloads from HandoffEnvelope-like structures.
        # HandoffEnvelope has: source_stage, scenario_id, release_id, decision,
        # payload (dict), metadata, produced_at_utc.
        a4_ctx: Optional[Dict[str, Any]] = None
        if isinstance(agent4_handoff, Mapping):
            a4_ctx = dict(agent4_handoff)
            if "payload" in a4_ctx and isinstance(a4_ctx["payload"], Mapping):
                # Merge payload fields at top level for easier access.
                payload_fields = a4_ctx.pop("payload")
                a4_ctx = {**a4_ctx, **payload_fields}

        a5_ctx: Optional[Dict[str, Any]] = None
        if isinstance(agent5_handoff, Mapping):
            a5_ctx = dict(agent5_handoff)
            if "payload" in a5_ctx and isinstance(a5_ctx["payload"], Mapping):
                payload_fields = a5_ctx.pop("payload")
                a5_ctx = {**a5_ctx, **payload_fields}

        refs: Dict[str, SourceRef] = {}
        if a4_ctx is not None:
            refs["agent4_context"] = SourceRef("handoff", "agent4_handoff")
        if a5_ctx is not None:
            refs["agent5_context"] = SourceRef("handoff", "agent5_handoff")

        # Load Phase 6 approval manifest from CSV (shared with file-based mode)
        approval_path = self.dataset_root / "approval_workflow_manifest.csv"
        approval_manifest: Optional[Dict[str, Any]] = None
        if approval_path.exists():
            rows = self._read_csv(approval_path)
            for row in rows:
                if (row.get("scenario_id") or "").strip() == sid:
                    approval_manifest = dict(row)
                    break

        if approval_manifest is not None:
            refs["approval_manifest"] = SourceRef("csv", str(approval_path))

        missing: List[str] = []
        if a4_ctx is None:
            missing.append("agent4_context")
        if a5_ctx is None:
            missing.append("agent5_context")

        return RawPhase6Bundle(
            scenario_id=sid,
            release_id=rid,
            environment=env,
            release_metadata={"release_id": rid, "environment": env},
            agent4_context=a4_ctx,
            agent5_context=a5_ctx,
            approval_manifest=approval_manifest,
            source_references=refs,
            missing_optional_artifacts=missing,
        )

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
                "Scenario `{0}` not found in {1}".format(scenario_id, calendar_path)
            )

        if release_id:
            rid = release_id.strip()
            filtered = [
                r for r in candidates if (r.get("release_id") or "").strip() == rid
            ]
            if filtered:
                chosen = filtered[0]
            else:
                known = sorted({(r.get("release_id") or "").strip() for r in candidates})
                raise IngestionError(
                    "Scenario `{0}` not found with release_id `{1}`. Known: {2}".format(
                        scenario_id, rid, ", ".join([k for k in known if k]) or "none"
                    )
                )
        else:
            chosen = candidates[0]

        return {
            "scenario_id": (chosen.get("scenario_id") or "").strip(),
            "release_id": (chosen.get("release_id") or "").strip(),
            "environment": ((chosen.get("environment") or "RELEASE").strip() or "RELEASE"),
            "agent4_scenario_id": (chosen.get("agent4_scenario_id") or "").strip(),
            "agent5_scenario_id": (chosen.get("agent5_scenario_id") or "").strip(),
        }

    def _read_csv(self, path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return []
            out: List[Dict[str, str]] = []
            for row in reader:
                normalized = {
                    (k or "").strip(): (v or "").strip() for k, v in row.items()
                }
                out.append(normalized)
            return out

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


class IngestionError(Exception):
    """Raised when required ingestion inputs are missing or inconsistent."""


# ---------------------------------------------------------------------------
# Convenience factories
# ---------------------------------------------------------------------------


def ingest_from_handoffs(
    scenario_id: str,
    agent4_handoff: Optional[Mapping[str, Any]],
    agent5_handoff: Optional[Mapping[str, Any]],
    release_id: Optional[str] = None,
) -> RawPhase6Bundle:
    """
    One-shot ingestion from BrainOrchestrator handoff payloads.
    """
    return Phase6Ingestion().ingest_from_handoffs(
        scenario_id=scenario_id,
        release_id=release_id,
        agent4_handoff=agent4_handoff,
        agent5_handoff=agent5_handoff,
    )