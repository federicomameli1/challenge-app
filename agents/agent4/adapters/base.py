"""
Agent 4 adapter base interfaces and source auto-detection.

This module defines a lightweight adapter abstraction so Agent 4 can ingest
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
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from ..ingestion import IngestionError, RawInputBundle


class AdapterError(Exception):
    """Raised for adapter-level failures (detection, registration, or loading)."""


@dataclass(frozen=True)
class SourceDetection:
    """
    Detection outcome for a candidate source root.

    Attributes:
        kind: Canonical source type key (e.g., "structured_dataset", "apcs_doc_bundle").
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
    factory: Callable[[Path], "Agent4SourceAdapter"]


class Agent4SourceAdapter(ABC):
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
          "environment": "DEV|..."
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
    Detect canonical structured dataset layout used by Agent 4 v1/v2.

    Required signals:
    - requirements_master.csv
    - release_calendar.csv
    - one of phase4_modules_versions.csv or modules_versions.csv
    """
    root = source_root
    req = root / "requirements_master.csv"
    cal = root / "release_calendar.csv"
    ver_a = root / "phase4_modules_versions.csv"
    ver_b = root / "modules_versions.csv"

    if req.exists() and cal.exists() and (ver_a.exists() or ver_b.exists()):
        return SourceDetection(
            kind="structured_dataset",
            confidence=0.98,
            reason="Found canonical Agent4 dataset contract files.",
            source_root=root,
        )
    return None


def _apcs_doc_bundle_detector(source_root: Path) -> Optional[SourceDetection]:
    """
    Detect teammate-style APCS dossier bundles (DOCX/TXT-centric).

    Supported locations:
    - source_root/Dataset/
    - source_root directly

    Tolerant behavior:
    - Detects both complete and partial APCS dossier folders.
    - Confidence increases with number of marker files found.
    """
    candidates = [source_root, source_root / "Dataset"]

    marker_files = [
        "APCS_Emails_v1.0.txt",
        "APCS_Requirements_v1.0.docx",
        "APCS_Requirements_v1.0.txt",
        "APCS_Module_Version_Inventory_v1.0.docx",
        "APCS_Module_Version_Inventory_v1.0.txt",
        "APCS_Test_Procedure_v1.0.docx",
        "APCS_Test_Procedure_v1.0.txt",
        "APCS_VDD_v1.0.docx",
        "APCS_VDD_v1.0.txt",
        "APCS_Inconsistencies_map_v1.0.docx",
        "APCS_Inconsistencies_map_v1.0.txt",
    ]

    best_detection: Optional[SourceDetection] = None

    for candidate in candidates:
        existing = [name for name in marker_files if (candidate / name).exists()]
        if not existing:
            continue

        # Heuristic confidence:
        # - one marker: lower confidence but still detectable
        # - more markers: stronger APCS bundle confidence
        coverage = len(existing) / len(marker_files)
        confidence = min(0.95, 0.60 + coverage)

        detection = SourceDetection(
            kind="apcs_doc_bundle",
            confidence=confidence,
            reason=(
                "Detected APCS dossier markers "
                f"({len(existing)} file(s): {', '.join(existing[:3])}"
                + (", ..." if len(existing) > 3 else "")
                + ")."
            ),
            source_root=candidate,
        )

        if best_detection is None or detection.confidence > best_detection.confidence:
            best_detection = detection

    return best_detection


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
        self, source_root: str | Path, kind: Optional[str] = None
    ) -> Agent4SourceAdapter:
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


def _build_structured_dataset_adapter(source_root: Path) -> Agent4SourceAdapter:
    # Lazy import to avoid circular imports at module load.
    from .structured_dataset import StructuredDatasetAdapter

    return StructuredDatasetAdapter(source_root)


def _build_apcs_doc_bundle_adapter(source_root: Path) -> Agent4SourceAdapter:
    # Lazy import so projects can keep this base module even if optional adapter
    # implementation is introduced later.
    from .apcs_doc_bundle import APCSDocBundleAdapter

    return APCSDocBundleAdapter(source_root)


def default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()

    registry.register(
        AdapterDescriptor(
            kind="structured_dataset",
            display_name="Structured dataset (v1/v2 canonical)",
            detector=_structured_dataset_detector,
            factory=_build_structured_dataset_adapter,
        )
    )
    registry.register(
        AdapterDescriptor(
            kind="apcs_doc_bundle",
            display_name="APCS dossier bundle (DOCX/TXT)",
            detector=_apcs_doc_bundle_detector,
            factory=_build_apcs_doc_bundle_adapter,
        )
    )

    return registry


def detect_source_kind(source_root: str | Path) -> Optional[SourceDetection]:
    """
    Convenience helper for one-shot source detection.
    """
    return default_registry().detect(source_root)
