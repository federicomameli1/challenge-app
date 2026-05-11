"""
Agent 6 handoff bundle and structured dataset adapters.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .base import Agent6SourceAdapter


class HandoffBundleAdapter(Agent6SourceAdapter):
    """Primary adapter for BrainOrchestrator mode -- reads from A4/A5 handoff payloads."""

    def detect_source_confidence(
        self, path: str, metadata: Optional[Mapping[str, Any]] = None
    ) -> float:
        if metadata is None:
            return 0.0
        has_a4 = "agent4_handoff" in metadata
        has_a5 = "agent5_handoff" in metadata
        if has_a4 and has_a5:
            return 1.0
        elif has_a4 or has_a5:
            return 0.5
        return 0.0

    def list_scenarios(self) -> List[Dict[str, str]]:
        return []

    def ingest(
        self,
        scenario_id: str,
        agent4_handoff: Optional[Mapping[str, Any]] = None,
        agent5_handoff: Optional[Mapping[str, Any]] = None,
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if agent4_handoff is None and agent5_handoff is None:
            raise RuntimeError("HandoffBundleAdapter requires at least one handoff payload.")

        a4_ctx = self._extract_payload(agent4_handoff) if agent4_handoff else None
        a5_ctx = self._extract_payload(agent5_handoff) if agent5_handoff else None

        refs: Dict[str, Any] = {}
        missing: List[str] = []

        if a4_ctx is not None:
            refs["agent4_context"] = {"source_type": "handoff", "path": "agent4_handoff"}
        else:
            missing.append("agent4_context")

        if a5_ctx is not None:
            refs["agent5_context"] = {"source_type": "handoff", "path": "agent5_handoff"}
        else:
            missing.append("agent5_context")

        return {
            "agent4_context": a4_ctx,
            "agent5_context": a5_ctx,
            "approval_manifest": None,
            "source_references": refs,
            "missing_optional_artifacts": missing,
        }

    def _extract_payload(self, handoff: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(handoff, Mapping):
            return None
        result: Dict[str, Any] = dict(handoff)
        if "payload" in result and isinstance(result["payload"], Mapping):
            payload_fields = result.pop("payload")
            result = {**result, **payload_fields}
        return result

    def validate_source(self) -> Dict[str, Any]:
        return {"valid": True, "adapter": self.__class__.__name__, "notes": ["Always valid when handoffs present"]}


class StructuredDatasetAdapter(Agent6SourceAdapter):
    """Fallback adapter for standalone evaluation mode."""

    def __init__(self, dataset_root: str = "synthetic_data/phase6/v1") -> None:
        self.dataset_root = dataset_root

    def detect_source_confidence(
        self, path: str, metadata: Optional[Mapping[str, Any]] = None
    ) -> float:
        p = Path(path or self.dataset_root)
        if not p.exists():
            return 0.0
        if (p / "phase6_release_calendar.csv").exists():
            return 1.0
        has_a4 = (p / "agent4_context").exists()
        has_a5 = (p / "agent5_context").exists()
        if has_a4 and has_a5:
            return 0.7
        elif has_a4 or has_a5:
            return 0.4
        return 0.1

    def list_scenarios(self) -> List[Dict[str, str]]:
        p = Path(self.dataset_root)
        calendar = p / "phase6_release_calendar.csv"
        if not calendar.exists():
            return []
        scenarios: List[Dict[str, str]] = []
        with calendar.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                scenarios.append({
                    "scenario_id": (row.get("scenario_id") or "").strip(),
                    "release_id": (row.get("release_id") or "").strip(),
                })
        return scenarios

    def ingest(
        self,
        scenario_id: str,
        agent4_handoff: Optional[Mapping[str, Any]] = None,
        agent5_handoff: Optional[Mapping[str, Any]] = None,
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = Path(self.dataset_root)

        a4_ctx: Optional[Dict[str, Any]] = None
        if agent4_handoff is not None:
            a4_ctx = dict(agent4_handoff)
            if "payload" in a4_ctx and isinstance(a4_ctx["payload"], Mapping):
                a4_ctx = {**a4_ctx, **a4_ctx.pop("payload")}
        else:
            a4_path = p / "agent4_context" / f"{scenario_id}.json"
            if a4_path.exists():
                with a4_path.open("r", encoding="utf-8") as f:
                    a4_ctx = json.load(f)

        a5_ctx: Optional[Dict[str, Any]] = None
        if agent5_handoff is not None:
            a5_ctx = dict(agent5_handoff)
            if "payload" in a5_ctx and isinstance(a5_ctx["payload"], Mapping):
                a5_ctx = {**a5_ctx, **a5_ctx.pop("payload")}
        else:
            a5_path = p / "agent5_context" / f"{scenario_id}.json"
            if a5_path.exists():
                with a5_path.open("r", encoding="utf-8") as f:
                    a5_ctx = json.load(f)

        missing: List[str] = []
        if a4_ctx is None:
            missing.append("agent4_context")
        if a5_ctx is None:
            missing.append("agent5_context")

        return {
            "agent4_context": a4_ctx,
            "agent5_context": a5_ctx,
            "approval_manifest": None,
            "source_references": {},
            "missing_optional_artifacts": missing,
        }

    def validate_source(self) -> Dict[str, Any]:
        p = Path(self.dataset_root)
        calendar = p / "phase6_release_calendar.csv"
        return {
            "valid": calendar.exists(),
            "dataset_root": str(p),
            "notes": ["phase6_release_calendar.csv present" if calendar.exists() else "MISSING: phase6_release_calendar.csv"],
        }


__all__ = ["HandoffBundleAdapter", "StructuredDatasetAdapter"]