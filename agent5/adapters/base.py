"""
Agent 5 adapter base interfaces and source auto-detection.

This module defines a lightweight adapter abstraction so Agent 5 can ingest
different upstream evidence formats (structured synthetic datasets, dossier-style
document bundles, etc.) without changing deterministic policy logic.

Design goals:
- Keep policy/evaluation layers untouched.
- Make ingestion source-specific and pluggable.
- Enable graceful auto-detection with confidence and rationale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..ingestion import IngestionError, RawInputBundle


class AdapterError(Exception):
    """Raised for adapter-level failures (detection, registration, or loading)."""


@dataclass(frozen=True)
class SourceDetection:
    """
    Detection outcome for a candidate source root.

    Attributes:
        kind: Canonical source type key (e.g., "structured_dataset").
        confidence: 0..1 confidence score.
        reason: Human-readable rationale for why this type was detected.
        source_root: Normalized source root path.
    """

    kind: str
    confidence: float
    reason: str
    source_root: Path


@dataclass(frozen=True)
class AdapterDescriptor:
    """
    Metadata for a registered adapter.

    Attributes:
        kind: Adapter key used for selection.
        display_name: Human-friendly name.
        detector: Function that returns SourceDetection or None.
        factory: Function that builds a concrete adapter instance.
    """

    kind: str
    display_name: str
    detector: Callable[[Path], Optional[SourceDetection]]
    factory: Callable[[Path], "Agent5SourceAdapter"]


class Agent5SourceAdapter(ABC):
    """
    Abstract interface for source-specific ingestion adapters.

    Concrete adapters should normalize source artifacts into RawInputBundle
    so downstream normalization/policy/explanation remains unchanged.
    """

    def __init__(self, source_root: str | Path) -> None:
        self.source_root = Path(source_root)

    @abstractmethod
    def validate_source(self) -> Dict[str, Any]:
        """
        Validate source structure and return diagnostics.
        """

    @abstractmethod
    def list_scenarios(self) -> List[Dict[str, str]]:
        """
        Return available scenarios as minimal dictionaries:
        {
          "scenario_id": "...",
          "release_id": "...",
          "environment": "TEST|..."
        }
        """

    @abstractmethod
    def ingest(
        self,
        scenario_id: str,
        release_id: Optional[str] = None,
    ) -> RawInputBundle:
        """
        Build a canonical RawInputBundle for one scenario.
        """


# ---------------------------------------------------------------------------
# Built-in detectors
# ---------------------------------------------------------------------------


def _structured_dataset_detector(source_root: Path) -> Optional[SourceDetection]:
    """
    Detect canonical structured dataset layout used by Agent 5 v1/v2.

    Required signals:
    - requirements_master.csv
    - test_cases_master.csv
    - traceability_matrix.csv
    - test_execution_results.csv
    - defect_register.csv
    - one of phase5_release_calendar.csv or release_calendar.csv
    """
    root = source_root

    required = [
        root / "requirements_master.csv",
        root / "test_cases_master.csv",
        root / "traceability_matrix.csv",
        root / "test_execution_results.csv",
        root / "defect_register.csv",
    ]

    calendar_candidates = [
        root / "phase5_release_calendar.csv",
        root / "release_calendar.csv",
    ]

    if all(p.exists() for p in required) and any(
        p.exists() for p in calendar_candidates
    ):
        return SourceDetection(
            kind="structured_dataset",
            confidence=0.99,
            reason="Found canonical Agent5 dataset contract files.",
            source_root=root,
        )
    return None


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------


class AdapterRegistry:
    """
    Registry for adapter descriptors + auto-detection orchestration.
    """

    def __init__(self) -> None:
        self._descriptors: Dict[str, AdapterDescriptor] = {}

    def register(self, descriptor: AdapterDescriptor) -> None:
        key = descriptor.kind.strip()
        if not key:
            raise AdapterError("Adapter kind cannot be empty.")
        self._descriptors[key] = descriptor

    def kinds(self) -> List[str]:
        return sorted(self._descriptors.keys())

    def get_descriptor(self, kind: str) -> AdapterDescriptor:
        key = kind.strip()
        if key not in self._descriptors:
            known = ", ".join(self.kinds()) or "(none)"
            raise AdapterError(f"Unknown adapter kind '{kind}'. Known kinds: {known}")
        return self._descriptors[key]

    def detect(self, source_root: str | Path) -> Optional[SourceDetection]:
        root = Path(source_root)
        best: Optional[SourceDetection] = None

        for descriptor in self._descriptors.values():
            detection = descriptor.detector(root)
            if detection is None:
                continue
            if best is None or detection.confidence > best.confidence:
                best = detection

        return best

    def build(
        self,
        source_root: str | Path,
        kind: Optional[str] = None,
    ) -> Agent5SourceAdapter:
        root = Path(source_root)

        if kind is None:
            detected = self.detect(root)
            if detected is None:
                known = ", ".join(self.kinds()) or "(none)"
                raise AdapterError(
                    f"Could not auto-detect source type under '{root}'. "
                    f"Registered adapter kinds: {known}"
                )
            descriptor = self.get_descriptor(detected.kind)
            return descriptor.factory(detected.source_root)

        descriptor = self.get_descriptor(kind)
        return descriptor.factory(root)


# ---------------------------------------------------------------------------
# Default registry bootstrap
# ---------------------------------------------------------------------------


def _build_structured_dataset_adapter(source_root: Path) -> Agent5SourceAdapter:
    # Lazy import to avoid circular imports at module load.
    from .structured_dataset import StructuredDatasetAdapter

    return StructuredDatasetAdapter(source_root)


def default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()

    registry.register(
        AdapterDescriptor(
            kind="structured_dataset",
            display_name="Structured dataset (Phase 5 canonical)",
            detector=_structured_dataset_detector,
            factory=_build_structured_dataset_adapter,
        )
    )

    return registry


def detect_source_kind(source_root: str | Path) -> Optional[SourceDetection]:
    """
    Convenience helper for one-shot source detection.
    """
    return default_registry().detect(source_root)


__all__ = [
    "AdapterError",
    "SourceDetection",
    "Agent5SourceAdapter",
    "AdapterDescriptor",
    "AdapterRegistry",
    "default_registry",
    "detect_source_kind",
]
