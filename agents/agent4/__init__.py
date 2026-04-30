"""
Agent 4 package exports.

This package provides a complete Phase 4 readiness workflow:
- data ingestion
- normalization
- deterministic policy evaluation
- evidence mapping
- deterministic/LLM explanation generation
"""

from .adapters import (
    AdapterError as SourceAdapterError,
)
from .adapters import (
    AdapterRegistry,
    Agent4SourceAdapter,
    APCSAdapterConfig,
    APCSDocBundleAdapter,
    SourceDetection,
    StructuredDatasetAdapter,
)
from .adapters import (
    default_registry as default_adapter_registry,
)
from .evidence import (
    build_reasons_from_findings,
    build_traceable_reasons_and_evidence,
    dedupe_source_refs,
    ensure_reason_has_evidence,
    evidence_coverage_ratio,
    finding_to_reason,
    flatten_finding_evidence,
    flatten_reason_evidence,
    merge_evidence,
)
from .explanation import (
    ExplanationContext,
    ExplanationError,
    build_deterministic_explanation,
    build_explanation_with_optional_llm,
)
from .generic_ingestion import (
    GenericIngestionConfig,
    GenericPhase4Ingestion,
    ingest_from_any_source,
)
from .generic_ingestion import (
    detect_source_kind as detect_source_kind_generic,
)
from .ingestion import (
    IngestionError,
    Phase4Ingestion,
    RawInputBundle,
    ingest_scenario,
)
from .ingestion import (
    SourceRef as IngestionSourceRef,
)
from .lc_pipeline import (
    Agent4LCError,
    LangChainAgent4Pipeline,
    LCPipelineConfig,
    build_langchain_pipeline,
    build_step_functions,
)
from .lc_state import (
    Agent4State as LCAgent4State,
)
from .lc_state import (
    as_langchain_input,
    clone_state,
    finalize_state,
    from_langchain_output,
    merge_state,
    new_agent4_state,
    push_error,
    push_trace,
    require_state_keys,
)
from .models import (
    Agent4Output,
    Confidence,
    Decision,
    DecisionType,
    EmailStatus,
    Environment,
    HealthReport,
    LogEvent,
    ModuleVersionRecord,
    ReasonItem,
    RequirementRecord,
    RuleCode,
    RuleFinding,
    RuleFindings,
    ScenarioInputBundle,
    ServiceStatus,
    Severity,
    build_agent4_output,
    confidence_from_findings,
    default_human_action,
    normalize_bool,
    parse_iso8601,
    utc_now_iso,
    validate_output_schema,
)
from .models import (
    SourceRef as ModelSourceRef,
)
from .models import (
    normalize_module_name as normalize_module_name_model,
)
from .normalization import (
    NormalizedEmailMessage,
    NormalizedEmailThread,
    NormalizedEvidenceBundle,
    NormalizedHealthReport,
    NormalizedHealthService,
    NormalizedLogEvent,
    NormalizedModuleVersion,
    NormalizedRequirement,
    normalize_deploy_log,
    normalize_email_thread,
    normalize_environment,
    normalize_evidence_bundle,
    normalize_health_report,
    normalize_module_name,
    normalize_module_versions,
    normalize_requirements,
    normalize_semver,
    parse_bool,
    parse_timestamp,
)
from .normalization import (
    SourceRef as NormalizationSourceRef,
)
from .policy import Phase4PolicyEngine, PolicyConfig, evaluate_phase4_readiness

__all__ = [
    # ingestion
    "IngestionError",
    "Phase4Ingestion",
    "RawInputBundle",
    "IngestionSourceRef",
    "ingest_scenario",
    # normalization
    "NormalizationSourceRef",
    "NormalizedRequirement",
    "NormalizedModuleVersion",
    "NormalizedLogEvent",
    "NormalizedHealthService",
    "NormalizedHealthReport",
    "NormalizedEmailMessage",
    "NormalizedEmailThread",
    "NormalizedEvidenceBundle",
    "normalize_requirements",
    "normalize_module_versions",
    "normalize_deploy_log",
    "normalize_health_report",
    "normalize_email_thread",
    "normalize_evidence_bundle",
    "normalize_module_name",
    "normalize_environment",
    "normalize_semver",
    "parse_bool",
    "parse_timestamp",
    # policy
    "PolicyConfig",
    "Phase4PolicyEngine",
    "evaluate_phase4_readiness",
    # evidence
    "build_reasons_from_findings",
    "build_traceable_reasons_and_evidence",
    "dedupe_source_refs",
    "ensure_reason_has_evidence",
    "evidence_coverage_ratio",
    "finding_to_reason",
    "flatten_finding_evidence",
    "flatten_reason_evidence",
    "merge_evidence",
    # explanation
    "ExplanationError",
    "ExplanationContext",
    "build_deterministic_explanation",
    "build_explanation_with_optional_llm",
    # models
    "ModelSourceRef",
    "Decision",
    "DecisionType",
    "Confidence",
    "Environment",
    "Severity",
    "EmailStatus",
    "RuleCode",
    "RequirementRecord",
    "ModuleVersionRecord",
    "LogEvent",
    "ServiceStatus",
    "HealthReport",
    "ScenarioInputBundle",
    "RuleFinding",
    "RuleFindings",
    "ReasonItem",
    "Agent4Output",
    "validate_output_schema",
    "build_agent4_output",
    "confidence_from_findings",
    "default_human_action",
    "normalize_bool",
    "normalize_module_name_model",
    "parse_iso8601",
    "utc_now_iso",
    # langchain state
    "LCAgent4State",
    "new_agent4_state",
    "clone_state",
    "merge_state",
    "push_trace",
    "push_error",
    "finalize_state",
    "require_state_keys",
    "as_langchain_input",
    "from_langchain_output",
    # langchain pipeline
    "Agent4LCError",
    "LCPipelineConfig",
    "build_step_functions",
    "build_langchain_pipeline",
    "LangChainAgent4Pipeline",
    # generic ingestion
    "GenericIngestionConfig",
    "GenericPhase4Ingestion",
    "detect_source_kind_generic",
    "ingest_from_any_source",
    # source adapters
    "SourceAdapterError",
    "SourceDetection",
    "Agent4SourceAdapter",
    "AdapterRegistry",
    "default_adapter_registry",
    "StructuredDatasetAdapter",
    "APCSAdapterConfig",
    "APCSDocBundleAdapter",
]
