"""
Agent 5 package exports.

This package provides a LangChain-first Phase 5 test-analysis workflow:
- ingestion
- normalization
- deterministic policy evaluation
- evidence mapping
- deterministic/optional LLM explanation
"""

from .agent import Agent5Config, Agent5LangChainOrchestrator
from .evidence import (
    build_reasons_from_findings,
    build_traceable_reasons_and_evidence,
    dedupe_source_refs,
    evidence_coverage_ratio,
    flatten_finding_evidence,
    flatten_reason_evidence,
)
from .explanation import (
    ExplanationContext,
    ExplanationError,
    build_deterministic_explanation,
    build_explanation_with_optional_llm,
)
from .ingestion import IngestionError, Phase5Ingestion, RawInputBundle, ingest_scenario
from .lc_pipeline import (
    Agent5LCError,
    LangChainAgent5Pipeline,
    LCPipelineConfig,
    build_langchain_pipeline,
    build_step_functions,
)
from .lc_state import (
    Agent5State as LCAgent5State,
)
from .lc_state import (
    as_langchain_input,
    clone_state,
    finalize_state,
    from_langchain_output,
    merge_state,
    new_agent5_state,
    push_error,
    push_trace,
    require_state_keys,
)
from .models import (
    Agent5Output,
    Confidence,
    Decision,
    DecisionType,
    ReasonItem,
    RuleCode,
    RuleFinding,
    RuleFindings,
    SourceRef,
    build_agent5_output,
    confidence_from_findings,
    default_human_action,
    utc_now_iso,
    validate_output_schema,
)
from .normalization import (
    NormalizedEvidenceBundle,
    normalize_evidence_bundle,
)
from .policy import Phase5PolicyEngine, PolicyConfig, evaluate_phase5_readiness

__all__ = [
    # agent
    "Agent5Config",
    "Agent5LangChainOrchestrator",
    # ingestion
    "IngestionError",
    "Phase5Ingestion",
    "RawInputBundle",
    "ingest_scenario",
    # normalization
    "NormalizedEvidenceBundle",
    "normalize_evidence_bundle",
    # policy
    "PolicyConfig",
    "Phase5PolicyEngine",
    "evaluate_phase5_readiness",
    # evidence
    "build_reasons_from_findings",
    "build_traceable_reasons_and_evidence",
    "dedupe_source_refs",
    "flatten_finding_evidence",
    "flatten_reason_evidence",
    "evidence_coverage_ratio",
    # explanation
    "ExplanationContext",
    "ExplanationError",
    "build_deterministic_explanation",
    "build_explanation_with_optional_llm",
    # models
    "SourceRef",
    "Decision",
    "DecisionType",
    "Confidence",
    "RuleCode",
    "RuleFinding",
    "RuleFindings",
    "ReasonItem",
    "Agent5Output",
    "build_agent5_output",
    "confidence_from_findings",
    "default_human_action",
    "utc_now_iso",
    "validate_output_schema",
    # langchain pipeline
    "Agent5LCError",
    "LCPipelineConfig",
    "LangChainAgent5Pipeline",
    "build_langchain_pipeline",
    "build_step_functions",
    # langchain state
    "LCAgent5State",
    "new_agent5_state",
    "clone_state",
    "merge_state",
    "push_trace",
    "push_error",
    "finalize_state",
    "require_state_keys",
    "as_langchain_input",
    "from_langchain_output",
]
