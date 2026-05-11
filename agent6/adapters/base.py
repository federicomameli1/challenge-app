"""
Agent 6 source adapter interface.
Mirrors the Agent 4/Agent 5 adapter architecture.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional, Tuple

from agent6.models import SourceRef


class Agent6SourceAdapter(ABC):
    @abstractmethod
    def detect_source_confidence(
        self, path: str, metadata: Optional[Mapping[str, Any]] = None
    ) -> float:
        """Return 0.0-1.0 confidence that this adapter can handle the given source."""

    @abstractmethod
    def list_scenarios(self) -> List[Dict[str, str]]:
        """Enumerate scenarios available in this adapter's source."""

    @abstractmethod
    def ingest(
        self,
        scenario_id: str,
        agent4_handoff: Optional[Mapping[str, Any]] = None,
        agent5_handoff: Optional[Mapping[str, Any]] = None,
        release_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingest Phase 6 evidence for one scenario."""

    def validate_source(self) -> Dict[str, Any]:
        return {"valid": True, "notes": []}


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: List[Agent6SourceAdapter] = []

    def register(self, adapter: Agent6SourceAdapter) -> None:
        self._adapters.append(adapter)

    def detect(
        self, path: str, metadata: Optional[Mapping[str, Any]] = None
    ) -> Tuple[Agent6SourceAdapter, float]:
        best_adapter: Optional[Agent6SourceAdapter] = None
        best_confidence = 0.0
        for adapter in self._adapters:
            conf = adapter.detect_source_confidence(path, metadata)
            if conf > best_confidence:
                best_confidence = conf
                best_adapter = adapter
        if best_adapter is None or best_confidence == 0.0:
            raise RuntimeError("No adapter registered for source: {0}".format(path))
        return best_adapter, best_confidence

    def list_all_scenarios(self) -> List[Dict[str, Any]]:
        all_scenarios: List[Dict[str, Any]] = []
        seen: set = set()
        for adapter in self._adapters:
            for sc in adapter.list_scenarios():
                key = sc.get("scenario_id", "")
                if key and key not in seen:
                    seen.add(key)
                    all_scenarios.append(sc)
        return all_scenarios


__all__ = ["Agent6SourceAdapter", "AdapterRegistry"]