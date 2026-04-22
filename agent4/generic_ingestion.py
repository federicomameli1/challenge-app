"""
Agent 4 generic ingestion entrypoint with adapter-based source auto-detection.

This module introduces a source-agnostic ingestion façade that can ingest:
- canonical structured datasets (v1/v2)
- APCS document bundles
- any future source type registered in adapter registry

Design goals:
- Keep downstream normalization/policy/explanation unchanged.
- Minimize impact on existing Agent 4 code.
- Support explicit adapter selection or automatic detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .adapters import (
    AdapterError,
    AdapterRegistry,
    SourceDetection,
    default_registry,
)
from .ingestion import IngestionError, RawInputBundle


@dataclass(frozen=True)
class GenericIngestionConfig:
    """
    Configuration for generic source ingestion.

    Attributes:
        source_root: Root path containing either structured dataset files or
            adapter-specific evidence bundle files.
        adapter_kind: Optional explicit adapter key. If omitted, adapter type
            is auto-detected via registry.
    """

    source_root: str | Path
    adapter_kind: Optional[str] = None


class GenericPhase4Ingestion:
    """
    Adapter-driven ingestion façade for Agent 4.

    Usage:
        ingestion = GenericPhase4Ingestion("synthetic_data/v2")
        bundle = ingestion.ingest("S4V2-001")

    or with explicit adapter kind:
        ingestion = GenericPhase4Ingestion(
            GenericIngestionConfig(
                source_root="external_sources/challenge-app/Dataset",
                adapter_kind="apcs_doc_bundle",
            )
        )
        bundle = ingestion.ingest("APCS-S4-001")
    """

    def __init__(
        self,
        config: GenericIngestionConfig | str | Path,
        registry: Optional[AdapterRegistry] = None,
    ) -> None:
        if isinstance(config, GenericIngestionConfig):
            self.config = config
        else:
            self.config = GenericIngestionConfig(source_root=config)

        self.source_root = Path(self.config.source_root)
        self.registry = registry or default_registry()
        self._resolved_detection: Optional[SourceDetection] = None
        self._adapter: Any = None

    # ------------------------------------------------------------------
    # Public APIs
    # ------------------------------------------------------------------

    def detect_source(self) -> Optional[SourceDetection]:
        """
        Detect source type using registered adapters.

        Returns:
            SourceDetection when a source format is recognized, otherwise None.
        """
        detected = self.registry.detect(self.source_root)
        self._resolved_detection = detected
        return detected

    def validate_dataset(self) -> Dict[str, Any]:
        """
        Backward-compatible validation API expected by existing Agent 4 callers.
        """
        adapter = self._get_adapter()
        report = adapter.validate_source()

        normalized = {
            "source_root": str(self.source_root),
            "adapter_kind": self._adapter_kind_used(),
            "detected": self._resolved_detection_to_dict(),
            "adapter_report": report,
        }

        # Preserve compatibility with existing code paths that inspect these keys.
        adapter_report = normalized.get("adapter_report", {}) or {}
        normalized["dataset_root"] = str(self.source_root)
        normalized["exists"] = bool(adapter_report.get("exists", False))
        normalized["missing_required"] = list(
            adapter_report.get("missing_required", [])
        )
        normalized["missing_optional"] = list(
            adapter_report.get("missing_optional", [])
        )
        normalized["present_optional"] = list(
            adapter_report.get("present_optional", [])
        )

        return normalized

    def validate_source(self) -> Dict[str, Any]:
        """
        Source-agnostic validation API. Alias to validate_dataset() for compatibility.
        """
        return self.validate_dataset()

    def list_scenarios(self) -> List[Dict[str, str]]:
        """
        List scenarios available from the resolved source adapter.
        """
        adapter = self._get_adapter()
        try:
            return adapter.list_scenarios()
        except Exception as exc:
            raise IngestionError(
                f"Generic ingestion failed while listing scenarios for source "
                f"'{self.source_root}' ({self._adapter_kind_used()}): {exc}"
            ) from exc

    def ingest(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> RawInputBundle:
        """
        Ingest one scenario from the resolved source adapter.

        Args:
            scenario_id: Scenario key to ingest.
            release_id: Optional release filter.

        Returns:
            RawInputBundle compatible with current Agent 4 pipeline.
        """
        sid = (scenario_id or "").strip()
        if not sid:
            raise IngestionError("scenario_id is required and cannot be empty.")

        adapter = self._get_adapter()
        try:
            return adapter.ingest(scenario_id=sid, release_id=release_id)
        except IngestionError:
            raise
        except Exception as exc:
            raise IngestionError(
                f"Generic ingestion failed for scenario_id={sid!r} under source "
                f"'{self.source_root}' ({self._adapter_kind_used()}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_adapter(self) -> Any:
        if self._adapter is not None:
            return self._adapter

        explicit_kind = self.config.adapter_kind
        try:
            if explicit_kind is not None and explicit_kind.strip():
                self._adapter = self.registry.build(
                    source_root=self.source_root,
                    kind=explicit_kind.strip(),
                )
                # Keep detection metadata for diagnostics consistency.
                self._resolved_detection = SourceDetection(
                    kind=explicit_kind.strip(),
                    confidence=1.0,
                    reason="Adapter kind explicitly requested by caller.",
                    source_root=self.source_root,
                )
            else:
                detection = self.registry.detect(self.source_root)
                self._resolved_detection = detection
                self._adapter = self.registry.build(source_root=self.source_root)
        except AdapterError as exc:
            raise IngestionError(
                f"Unable to resolve ingestion adapter for source '{self.source_root}': {exc}"
            ) from exc

        return self._adapter

    def _adapter_kind_used(self) -> str:
        if self._resolved_detection is not None:
            return self._resolved_detection.kind
        if self.config.adapter_kind:
            return self.config.adapter_kind
        return "unknown"

    def _resolved_detection_to_dict(self) -> Optional[Dict[str, Any]]:
        d = self._resolved_detection
        if d is None:
            return None
        return {
            "kind": d.kind,
            "confidence": d.confidence,
            "reason": d.reason,
            "source_root": str(d.source_root),
        }


def detect_source_kind(
    source_root: str | Path,
    registry: Optional[AdapterRegistry] = None,
) -> Optional[Dict[str, Any]]:
    """
    Convenience helper returning detection details as plain dict.
    """
    reg = registry or default_registry()
    detection = reg.detect(Path(source_root))
    if detection is None:
        return None
    return {
        "kind": detection.kind,
        "confidence": detection.confidence,
        "reason": detection.reason,
        "source_root": str(detection.source_root),
    }


def ingest_from_any_source(
    *,
    source_root: str | Path,
    scenario_id: str,
    release_id: Optional[str] = None,
    adapter_kind: Optional[str] = None,
    registry: Optional[AdapterRegistry] = None,
) -> RawInputBundle:
    """
    One-shot ingestion helper with optional explicit adapter kind.
    """
    ingestion = GenericPhase4Ingestion(
        GenericIngestionConfig(
            source_root=source_root,
            adapter_kind=adapter_kind,
        ),
        registry=registry,
    )
    return ingestion.ingest(scenario_id=scenario_id, release_id=release_id)


__all__ = [
    "GenericIngestionConfig",
    "GenericPhase4Ingestion",
    "detect_source_kind",
    "ingest_from_any_source",
]
