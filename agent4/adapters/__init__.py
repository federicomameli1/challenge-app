"""
Agent 4 source adapters package.

This package provides pluggable ingestion adapters so Agent 4 can ingest
multiple upstream evidence formats (canonical structured datasets, APCS-style
document bundles, etc.) while keeping normalization/policy logic unchanged.
"""

from .apcs_doc_bundle import (
    APCSAdapterConfig,
    APCSDocBundleAdapter,
    ingest_apcs_doc_bundle,
)
from .base import (
    AdapterDescriptor,
    AdapterError,
    AdapterRegistry,
    Agent4SourceAdapter,
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
    "Agent4SourceAdapter",
    "AdapterDescriptor",
    "AdapterRegistry",
    "default_registry",
    "detect_source_kind",
    # structured adapter
    "StructuredAdapterError",
    "StructuredAdapterDescriptor",
    "StructuredDatasetAdapter",
    "load_structured_bundle",
    # APCS adapter
    "APCSAdapterConfig",
    "APCSDocBundleAdapter",
    "ingest_apcs_doc_bundle",
]
