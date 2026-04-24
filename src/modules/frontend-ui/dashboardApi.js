export const AGENT_BACKEND_URL =
  import.meta.env.VITE_AGENT_BACKEND_URL || "/api";

const AGENT_GATES = {
  agent4: "Phase 4",
  agent5: "Phase 5",
};

const PHASE5_REQUIRED_FILES = new Set([
  "requirements_master.csv",
  "test_cases_master.csv",
  "traceability_matrix.csv",
  "test_execution_results.csv",
  "defect_register.csv",
]);

const PHASE5_CALENDAR_FILES = new Set([
  "phase5_release_calendar.csv",
  "release_calendar.csv",
]);

function titleizeRuleCode(code) {
  return String(code || "rule")
    .replace(/_/g, " ")
    .replace(/\bagent4\b/gi, "Release Readiness Analyst")
    .replace(/\bagent5\b/gi, "Test Evidence Analyst")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function basename(value) {
  return String(value || "").split(/[\\/]/).pop() || "";
}

function normalizeEvidenceItem(item) {
  const lineStart = item?.line_start ?? item?.lineStart ?? item?.line ?? null;
  const lineEnd = item?.line_end ?? item?.lineEnd ?? null;

  let line = "-";
  if (lineStart !== null && lineStart !== undefined && lineStart !== "") {
    line = String(lineStart);
    if (lineEnd !== null && lineEnd !== undefined && lineEnd !== "" && lineEnd !== lineStart) {
      line = `${lineStart}-${lineEnd}`;
    }
  }

  return {
    filePath: String(item?.file_path || item?.filePath || "unknown"),
    line,
    snippet: String(item?.snippet || ""),
  };
}

function normalizeReason(reason, index = 0) {
  const title = String(reason?.title || `Reason ${index + 1}`);
  const code = reason?.rule_code || reason?.code || null;

  return {
    code: code ? String(code) : null,
    title,
    detail: String(reason?.detail || ""),
    evidence: Array.isArray(reason?.evidence)
      ? reason.evidence.map(normalizeEvidenceItem)
      : [],
  };
}

function normalizeSignal(signal) {
  const code = String(signal?.code || "unknown_rule");
  return {
    code,
    title: titleizeRuleCode(code),
    matched: Boolean(signal?.triggered ?? signal?.matched),
    pattern: String(signal?.reason || signal?.pattern || ""),
    evidence: Array.isArray(signal?.evidence)
      ? signal.evidence.map(normalizeEvidenceItem)
      : [],
  };
}

function summarizeEvaluateAll(payload) {
  const predictions = Array.isArray(payload?.predictions) ? payload.predictions : [];
  const summary = payload?.summary || {};

  return {
    totalScenarios: Number(summary.total_scenarios || predictions.length || 0),
    goCount: predictions.filter((item) => item?.decision === "GO").length,
    holdCount: predictions.filter((item) => item?.decision === "HOLD").length,
    evaluatedLabels: Number(summary.evaluated_scenarios || 0),
    matched: Number(summary.matched || 0),
    accuracy:
      typeof summary.accuracy === "number" ? Number(summary.accuracy) : null,
    schemaValidityRate:
      typeof summary.schema_validity_rate === "number"
        ? Number(summary.schema_validity_rate)
        : null,
    missingPredictions: Number(summary.missing_predictions || 0),
    falseGo: Number(summary.false_go || 0),
    falseHold: Number(summary.false_hold || 0),
    falseGoRate:
      typeof summary.false_go_rate === "number"
        ? Number(summary.false_go_rate)
        : null,
    falseHoldRate:
      typeof summary.false_hold_rate === "number"
        ? Number(summary.false_hold_rate)
        : null,
  };
}

function normalizePredictions(payload) {
  const evaluationRows = Array.isArray(payload?.rows) ? payload.rows : [];
  const evaluationByScenario = new Map(
    evaluationRows.map((row) => [
      String(row?.scenario_id || row?.set_id || row?.id || row?.label || ""),
      row,
    ])
  );

  return (Array.isArray(payload?.predictions) ? payload.predictions : []).map((item) => {
    const scenarioId = String(
      item?.scenario_id || item?.setId || item?.id || item?.label || ""
    );
    const evaluation = evaluationByScenario.get(scenarioId);
    return {
      scenarioId,
      releaseId: item?.release_id || null,
      decision: String(item?.decision || "UNKNOWN").toUpperCase(),
      confidence: String(item?.confidence || "unknown"),
      summary: String(item?.summary || ""),
      expectedDecision: evaluation?.expected_decision || null,
      labelMatch:
        typeof evaluation?.match === "boolean" ? evaluation.match : null,
    };
  });
}

export function buildIdleAnalysis(agentId, message = "No backend run yet.") {
  return {
    decision: "IDLE",
    confidence: "unknown",
    gate: AGENT_GATES[agentId] || "Unknown Phase",
    summary: message,
    humanAction: "Run the backend analysis to load decision details.",
    decisionType: "n/a",
    policyVersion: null,
    timestampUtc: null,
    reasons: [],
    signals: [],
    matchedSignals: [],
    evidence: [],
    coverageMetrics: null,
    crossPhaseContinuityFlags: null,
    missingArtifacts: [],
    diagnostics: null,
    meta: null,
    rawPayload: null,
  };
}

export function normalizeAnalysisPayload(agentId, payload) {
  if (!payload || typeof payload !== "object") {
    return buildIdleAnalysis(agentId, "No payload returned by the backend.");
  }

  const signals = Array.isArray(payload?.rule_findings?.findings)
    ? payload.rule_findings.findings.map(normalizeSignal)
    : [];
  const reasons = Array.isArray(payload?.reasons)
    ? payload.reasons.map(normalizeReason)
    : [];

  return {
    decision: String(payload?.decision || "UNKNOWN").toUpperCase(),
    confidence: String(payload?.confidence || "unknown").toLowerCase(),
    gate: AGENT_GATES[agentId] || "Unknown Phase",
    summary: String(payload?.summary || ""),
    humanAction: String(payload?.human_action || ""),
    decisionType: String(payload?.decision_type || "n/a"),
    policyVersion: payload?.policy_version || null,
    timestampUtc: payload?.timestamp_utc || null,
    reasons,
    signals,
    matchedSignals: signals.filter((signal) => signal.matched),
    evidence: Array.isArray(payload?.evidence)
      ? payload.evidence.map(normalizeEvidenceItem)
      : [],
    coverageMetrics:
      payload?.coverage_metrics && typeof payload.coverage_metrics === "object"
        ? payload.coverage_metrics
        : null,
    crossPhaseContinuityFlags:
      payload?.cross_phase_continuity_flags &&
      typeof payload.cross_phase_continuity_flags === "object"
        ? payload.cross_phase_continuity_flags
        : null,
    missingArtifacts: Array.isArray(payload?.missing_artifacts)
      ? payload.missing_artifacts.map((item) => String(item))
      : [],
    diagnostics:
      payload?.diagnostics && typeof payload.diagnostics === "object"
        ? payload.diagnostics
        : null,
    meta: payload?.meta && typeof payload.meta === "object" ? payload.meta : null,
    rawPayload: payload,
  };
}

export function normalizeAgentRunResponse(agentId, response, source = "manual") {
  const mode = response?.mode === "evaluate_all" ? "evaluate_all" : "single";

  return {
    agentId,
    source,
    mode,
    payload: response?.payload || null,
    diagnostics: response?.diagnostics || {},
    analysis:
      mode === "single"
        ? normalizeAnalysisPayload(agentId, response?.payload)
        : null,
    evaluateAllSummary:
      mode === "evaluate_all" ? summarizeEvaluateAll(response?.payload) : null,
    predictions:
      mode === "evaluate_all" ? normalizePredictions(response?.payload) : [],
    receivedAt: new Date().toISOString(),
  };
}

export function normalizeBrainStageResponse(agentId, stageResult) {
  return {
    agentId,
    source: "brain",
    mode: "single",
    payload: stageResult?.payload || null,
    diagnostics: {},
    analysis: normalizeAnalysisPayload(agentId, stageResult?.payload),
    stageStatus: stageResult?.status || "unknown",
    stageError: stageResult?.error || null,
    stageMetadata:
      stageResult?.metadata && typeof stageResult.metadata === "object"
        ? stageResult.metadata
        : {},
    receivedAt: new Date().toISOString(),
  };
}

async function requestJson(path, init = {}) {
  const response = await fetch(`${AGENT_BACKEND_URL}${path}`, init);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message =
      typeof data?.detail === "string"
        ? data.detail
        : `Backend error (${response.status})`;
    throw new Error(message);
  }

  return data;
}

export async function fetchBackendCustomSets() {
  const data = await requestJson("/datasets/custom-sets");
  return Array.isArray(data?.items) ? data.items : [];
}

export async function saveCustomSetToBackend(payload) {
  return requestJson("/datasets/custom-sets", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function deleteCustomSetFromBackend(setId) {
  return requestJson(`/datasets/custom-sets/${encodeURIComponent(setId)}`, {
    method: "DELETE",
  });
}

export async function validateBackendDataset(payload) {
  return requestJson("/agents/validate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function fetchBackendScenarios(payload) {
  return requestJson("/agents/scenarios", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function runBackendAgent(payload) {
  return requestJson("/agents/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function runBackendBrain(payload) {
  return requestJson("/brain/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

function inferBackendProfiles(set) {
  const docs = Array.isArray(set?.documents) ? set.documents : [];
  const names = new Set(
    docs
      .map((doc) => basename(doc?.name || doc?.filePath))
      .filter(Boolean)
  );

  const backend = {};
  if (Array.from(names).some((name) => name.startsWith("APCS_"))) {
    backend.agent4 = {
      datasetRoot: `challenge-app/Dataset/Test_Sets/${set.id}`,
      sourceAdapterKind: "apcs_doc_bundle",
    };
  }

  const hasPhase5Bundle =
    Array.from(PHASE5_REQUIRED_FILES).every((name) => names.has(name)) &&
    Array.from(PHASE5_CALENDAR_FILES).some((name) => names.has(name));
  if (hasPhase5Bundle) {
    backend.agent5 = {
      datasetRoot: `challenge-app/Dataset/Test_Sets/${set.id}`,
    };
  }

  return Object.keys(backend).length > 0 ? backend : null;
}

export function normalizeSetForAnalysis(set) {
  const docs = Array.isArray(set?.documents) ? set.documents : [];
  const backend =
    set?.backend && typeof set.backend === "object"
      ? set.backend
      : set?.source === "custom" && set?.id
        ? inferBackendProfiles(set)
        : null;

  return {
    id: String(set?.id || "set"),
    label: String(set?.label || set?.id || "Untitled Set"),
    source: set?.source === "custom" ? "custom" : "built-in",
    documents: docs.map((doc, index) => ({
      name: String(doc?.name || `document-${index + 1}.txt`),
      filePath: String(doc?.filePath || doc?.name || `document-${index + 1}.txt`),
      text: String(doc?.text || ""),
      isBinary: Boolean(doc?.isBinary),
      contentType: doc?.contentType || null,
      contentBase64: doc?.contentBase64 || doc?.content_base64 || null,
    })),
    persisted: Boolean(set?.persisted),
    backend,
  };
}

export function buildAgentRunRequest({
  agentId,
  selectedDataset,
  runOptions,
  defaultScenarioId = null,
}) {
  const backendPreset = selectedDataset?.backend?.[agentId];
  if (!backendPreset) {
    return null;
  }

  const payload = {
    agent: agentId,
    dataset_root: backendPreset.datasetRoot,
    release_id: backendPreset.releaseId || null,
    evaluate_all: false,
    check_label: Boolean(runOptions.checkLabel),
    labels_path: null,
    fail_on_label_mismatch: Boolean(runOptions.failOnLabelMismatch),
    strict_schema: Boolean(runOptions.strictSchema),
    no_llm: Boolean(runOptions.noLlm),
  };

  const scenarioId = backendPreset.scenarioId || defaultScenarioId || null;
  if (scenarioId) {
    payload.scenario_id = scenarioId;
  }

  if (agentId === "agent4") {
    payload.source_adapter_kind =
      runOptions.sourceAdapterKind === "auto"
        ? backendPreset.sourceAdapterKind || "auto"
        : runOptions.sourceAdapterKind;
  }

  return payload;
}

export function buildBrainRunRequest({
  selectedDataset,
  runOptions,
  agent4ScenarioId,
  agent5ScenarioId,
  allowAgent5AfterAgent4Hold,
}) {
  const agent4Preset = selectedDataset?.backend?.agent4;
  const agent5Preset = selectedDataset?.backend?.agent5;

  if (!agent4Preset || !agent5Preset) {
    return null;
  }

  const resolvedAgent4ScenarioId = agent4Preset.scenarioId || agent4ScenarioId || null;
  const resolvedAgent5ScenarioId = agent5Preset.scenarioId || agent5ScenarioId || null;

  if (!resolvedAgent4ScenarioId || !resolvedAgent5ScenarioId) {
    return null;
  }

  return {
    scenario_id: resolvedAgent4ScenarioId,
    agent4_scenario_id: resolvedAgent4ScenarioId,
    agent5_scenario_id: resolvedAgent5ScenarioId,
    agent4_dataset_root: agent4Preset.datasetRoot,
    agent5_dataset_root: agent5Preset.datasetRoot,
    agent4_source_adapter_kind: agent4Preset.sourceAdapterKind || null,
    agent4_use_llm_summary: !runOptions.noLlm,
    agent5_use_llm_summary: !runOptions.noLlm,
    agent4_strict_schema: Boolean(runOptions.strictSchema),
    agent5_strict_schema: Boolean(runOptions.strictSchema),
    allow_agent5_after_agent4_hold: Boolean(allowAgent5AfterAgent4Hold),
  };
}
