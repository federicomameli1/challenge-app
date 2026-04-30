"""
Agent 5 source adapters package.

This package provides pluggable ingestion adapters so Agent 5 can ingest
multiple upstream evidence formats while keeping normalization/policy logic
unchanged.
"""

from .base import (
    AdapterDescriptor,
    AdapterError,
    AdapterRegistry,
    Agent5SourceAdapter,
    SourceDetection,
    default_registry,
    detect_source_kind,
)
from .structured_dataset import (
    AdapterDescriptor as StructuredAdapterDescriptor,
)
from .structured_dataset import (
    AdapterError as StructuredAdapterError,
)
from .structured_dataset import (
    StructuredDatasetAdapter,
    load_structured_bundle,
)

__all__ = [
    # base / registry
    "AdapterError",
    "SourceDetection",
    "Agent5SourceAdapter",
    "AdapterDescriptor",
    "AdapterRegistry",
    "default_registry",
    "detect_source_kind",
    # structured adapter
    "StructuredAdapterError",
    "StructuredAdapterDescriptor",
    "StructuredDatasetAdapter",
    "load_structured_bundle",
]
