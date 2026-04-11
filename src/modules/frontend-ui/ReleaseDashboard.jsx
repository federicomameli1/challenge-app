import { useEffect, useMemo, useState } from "react";
import goEmailText from "../../../Dataset/GO Documents/APCS_Emails_v1.0.txt?raw";
import holdEmailText from "../../../Dataset/HOLD Documents/APCS_Emails_v1.0.txt?raw";
import goStableEmailText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Emails_v1.0.txt?raw";
import goStableRequirementsText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Requirements_v1.0.txt?raw";
import goStableVersionInventoryText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Module_Version_Inventory_v1.0.txt?raw";
import goStableTestProcedureText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Test_Procedure_v1.0.txt?raw";
import goStableVddText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_VDD_v1.0.txt?raw";
import holdRuntimeEmailText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Emails_v1.0.txt?raw";
import holdRuntimeRequirementsText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Requirements_v1.0.txt?raw";
import holdRuntimeVersionInventoryText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Module_Version_Inventory_v1.0.txt?raw";
import holdRuntimeTestProcedureText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Test_Procedure_v1.0.txt?raw";
import holdRuntimeVddText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_VDD_v1.0.txt?raw";
import holdA4EmailText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Emails_v1.0.txt?raw";
import holdA4RequirementsText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Requirements_v1.0.txt?raw";
import holdA4VersionInventoryText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Module_Version_Inventory_v1.0.txt?raw";
import holdA4TestProcedureText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Test_Procedure_v1.0.txt?raw";
import holdA4VddText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_VDD_v1.0.txt?raw";
import randomApcsEmailText from "../../../Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_Emails_v1.0.txt?raw";
import randomApcsRequirementsText from "../../../Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_Requirements_v1.0.txt?raw";
import randomApcsVersionInventoryText from "../../../Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_Module_Version_Inventory_v1.0.txt?raw";
import randomApcsTestProcedureText from "../../../Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_Test_Procedure_v1.0.txt?raw";
import randomApcsVddText from "../../../Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_VDD_v1.0.txt?raw";

const AGENTS = {
  agent4: {
    id: "agent4",
    name: "Agent 4",
    phase: "Phase 4",
    description: "Release readiness gate from operational and documentary evidence.",
  },
  agent5: {
    id: "agent5",
    name: "Agent 5",
    phase: "Phase 5",
    description: "Test-analysis gate with continuity checks from Agent 4 context.",
  },
};

const AGENT_BACKEND_URL =
  import.meta.env.VITE_AGENT_BACKEND_URL || "http://127.0.0.1:8001";

const BUILTIN_SETS = [
  {
    id: "go",
    label: "GO Documents",
    source: "built-in",
    backend: {
      agent4: {
        datasetRoot: "challenge-app/Dataset/GO Documents",
        scenarioId: "APCS-S4-001",
        sourceAdapterKind: "apcs_doc_bundle",
      },
      agent5: {
        datasetRoot: "synthetic_data/phase5/v2",
        scenarioId: "P5V2-001",
      },
    },
    documents: [
      {
        name: "APCS_Emails_v1.0.txt",
        filePath: "Dataset/GO Documents/APCS_Emails_v1.0.txt",
        text: goEmailText,
      },
    ],
  },
  {
    id: "hold",
    label: "HOLD Documents",
    source: "built-in",
    backend: {
      agent4: {
        datasetRoot: "challenge-app/Dataset/HOLD Documents",
        scenarioId: "APCS-S4-001",
        sourceAdapterKind: "apcs_doc_bundle",
      },
      agent5: {
        datasetRoot: "synthetic_data/phase5/v2",
        scenarioId: "P5V2-003",
      },
    },
    documents: [
      {
        name: "APCS_Emails_v1.0.txt",
        filePath: "Dataset/HOLD Documents/APCS_Emails_v1.0.txt",
        text: holdEmailText,
      },
    ],
  },
  {
    id: "go-stable-v112",
    label: "SET_GO_STABLE_v1.1.2",
    source: "built-in",
    backend: {
      agent4: {
        datasetRoot: "challenge-app/Dataset/Test_Sets/SET_GO_STABLE_v1.1.2",
        scenarioId: "APCS-S4-001",
        sourceAdapterKind: "apcs_doc_bundle",
      },
      agent5: {
        datasetRoot: "synthetic_data/phase5/v2",
        scenarioId: "P5V2-008",
      },
    },
    documents: [
      {
        name: "APCS_Emails_v1.0.txt",
        filePath: "Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Emails_v1.0.txt",
        text: goStableEmailText,
      },
      {
        name: "APCS_Requirements_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Requirements_v1.0.txt",
        text: goStableRequirementsText,
      },
      {
        name: "APCS_Module_Version_Inventory_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Module_Version_Inventory_v1.0.txt",
        text: goStableVersionInventoryText,
      },
      {
        name: "APCS_Test_Procedure_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Test_Procedure_v1.0.txt",
        text: goStableTestProcedureText,
      },
      {
        name: "APCS_VDD_v1.0.txt",
        filePath: "Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_VDD_v1.0.txt",
        text: goStableVddText,
      },
    ],
  },
  {
    id: "hold-runtime-unresolved-v112",
    label: "SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2",
    source: "built-in",
    backend: {
      agent4: {
        datasetRoot:
          "challenge-app/Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2",
        scenarioId: "APCS-S4-001",
        sourceAdapterKind: "apcs_doc_bundle",
      },
      agent5: {
        datasetRoot: "synthetic_data/phase5/v2",
        scenarioId: "P5V2-024",
      },
    },
    documents: [
      {
        name: "APCS_Emails_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Emails_v1.0.txt",
        text: holdRuntimeEmailText,
      },
      {
        name: "APCS_Requirements_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Requirements_v1.0.txt",
        text: holdRuntimeRequirementsText,
      },
      {
        name: "APCS_Module_Version_Inventory_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Module_Version_Inventory_v1.0.txt",
        text: holdRuntimeVersionInventoryText,
      },
      {
        name: "APCS_Test_Procedure_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Test_Procedure_v1.0.txt",
        text: holdRuntimeTestProcedureText,
      },
      {
        name: "APCS_VDD_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_VDD_v1.0.txt",
        text: holdRuntimeVddText,
      },
    ],
  },
  {
    id: "hold-a4-continuity-v112",
    label: "SET_HOLD_A4_CONTINUITY_v1.1.2",
    source: "built-in",
    backend: {
      agent4: {
        datasetRoot:
          "challenge-app/Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2",
        scenarioId: "APCS-S4-001",
        sourceAdapterKind: "apcs_doc_bundle",
      },
      agent5: {
        datasetRoot: "synthetic_data/phase5/v2",
        scenarioId: "P5V2-007",
      },
    },
    documents: [
      {
        name: "APCS_Emails_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Emails_v1.0.txt",
        text: holdA4EmailText,
      },
      {
        name: "APCS_Requirements_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Requirements_v1.0.txt",
        text: holdA4RequirementsText,
      },
      {
        name: "APCS_Module_Version_Inventory_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Module_Version_Inventory_v1.0.txt",
        text: holdA4VersionInventoryText,
      },
      {
        name: "APCS_Test_Procedure_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Test_Procedure_v1.0.txt",
        text: holdA4TestProcedureText,
      },
      {
        name: "APCS_VDD_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_VDD_v1.0.txt",
        text: holdA4VddText,
      },
    ],
  },
  {
    id: "random-apcs-v1",
    label: "SET_RANDOM_APCS_v1.0",
    source: "built-in",
    backend: {
      agent4: {
        datasetRoot: "challenge-app/Dataset/Test_Sets/SET_RANDOM_APCS_v1.0",
        scenarioId: "APCS-S4-001",
        sourceAdapterKind: "apcs_doc_bundle",
      },
      agent5: {
        datasetRoot: "synthetic_data/phase5/v2",
        scenarioId: "P5V2-024",
      },
    },
    documents: [
      {
        name: "APCS_Emails_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_Emails_v1.0.txt",
        text: randomApcsEmailText,
      },
      {
        name: "APCS_Requirements_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_Requirements_v1.0.txt",
        text: randomApcsRequirementsText,
      },
      {
        name: "APCS_Module_Version_Inventory_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_Module_Version_Inventory_v1.0.txt",
        text: randomApcsVersionInventoryText,
      },
      {
        name: "APCS_Test_Procedure_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_Test_Procedure_v1.0.txt",
        text: randomApcsTestProcedureText,
      },
      {
        name: "APCS_VDD_v1.0.txt",
        filePath: "Dataset/Test_Sets/SET_RANDOM_APCS_v1.0/APCS_VDD_v1.0.txt",
        text: randomApcsVddText,
      },
    ],
  },
];

const EXPECTED_DECISION_BY_SET_ID = {
  go: "GO",
  hold: "HOLD",
  "go-stable-v112": "GO",
  "hold-runtime-unresolved-v112": "HOLD",
  "hold-a4-continuity-v112": "HOLD",
  "random-apcs-v1": "HOLD",
};

const CUSTOM_SET_STORAGE_KEY = "hitachi-agent-console-custom-sets";

function loadCustomSets() {
  try {
    const raw = localStorage.getItem(CUSTOM_SET_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((set) => set && typeof set.id === "string");
  } catch {
    return [];
  }
}

function persistCustomSets(sets) {
  localStorage.setItem(CUSTOM_SET_STORAGE_KEY, JSON.stringify(sets));
}

async function fetchBackendCustomSets() {
  const response = await fetch(`${AGENT_BACKEND_URL}/datasets/custom-sets`);
  if (!response.ok) {
    return [];
  }

  const data = await response.json();
  return Array.isArray(data?.items) ? data.items : [];
}

async function saveCustomSetToBackend(payload) {
  const response = await fetch(`${AGENT_BACKEND_URL}/datasets/custom-sets`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data?.detail === "string" ? data.detail : "Unable to save set to backend.";
    throw new Error(message);
  }

  return data;
}

async function deleteCustomSetFromBackend(setId) {
  const response = await fetch(`${AGENT_BACKEND_URL}/datasets/custom-sets/${encodeURIComponent(setId)}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    if (response.status === 404) {
      return;
    }

    const data = await response.json().catch(() => ({}));
    const message = typeof data?.detail === "string" ? data.detail : "Unable to delete set from backend.";
    throw new Error(message);
  }
}

function normalizeSetForAnalysis(set) {
  const docs = Array.isArray(set.documents) ? set.documents : [];
  const combinedText = docs.map((d) => String(d.text || "")).join("\n\n");
  const backend = set.backend || null;
  const persisted = Boolean(set.persisted);
  return {
    id: set.id,
    label: set.label,
    source: set.source,
    documents: docs,
    text: combinedText,
    backend:
      backend ||
      (set.source === "custom" && persisted
        ? {
            agent4: {
              datasetRoot: `challenge-app/Dataset/Test_Sets/${set.id}`,
              sourceAdapterKind: "apcs_doc_bundle",
            },
          }
        : null),
    persisted,
  };
}

function readUploadedFile(file) {
  if (typeof file.text === "function") {
    return file.text();
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error(`Cannot read ${file.name}`));
    reader.readAsText(file);
  });
}

function downloadJsonFile(fileName, payload) {
  const text = JSON.stringify(payload, null, 2);
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function sanitizeImportedCustomSets(inputSets) {
  if (!Array.isArray(inputSets)) {
    return [];
  }

  const validSets = [];
  for (const candidate of inputSets) {
    if (!candidate || typeof candidate !== "object") {
      continue;
    }

    const label = String(candidate.label || "").trim();
    if (!label) {
      continue;
    }

    const docs = Array.isArray(candidate.documents) ? candidate.documents : [];
    const normalizedDocs = docs
      .map((doc, index) => ({
        name: String(doc?.name || `document-${index + 1}.txt`),
        filePath: String(doc?.filePath || `Imported/document-${index + 1}.txt`),
        text: String(doc?.text || ""),
      }))
      .filter((doc) => doc.text.trim().length > 0);

    if (normalizedDocs.length === 0) {
      continue;
    }

    validSets.push({
      id: String(candidate.id || `custom-${Date.now()}-${validSets.length}`),
      label,
      source: "custom",
      persisted: false,
      documents: normalizedDocs,
    });
  }

  return validSets;
}

function readSignals(agentId, text) {
  const low = text.toLowerCase();

  if (agentId === "agent4") {
    const signals = [
      {
        code: "critical_service_unhealthy",
        title: "Critical Service Unhealthy",
        matched: /(backend .* issue|incorrect .* values|not fully available in prod)/i.test(
          low
        ) &&
          /(still marked as fail|not re-?executed|would not consider.*ready|unresolved)/i.test(
            low
          ),
        pattern:
          "backend issue or incorrect values plus unresolved/fail evidence",
      },
      {
        code: "unresolved_error_or_critical_log",
        title: "Unresolved Error Or Critical Log",
        matched:
          /(incorrect occupancy|classification inconsistency|issue .* affect)/i.test(
            low
          ) &&
          /(still marked as fail|not re-?executed|known limitation|unresolved)/i.test(
            low
          ),
        pattern: "runtime issue plus unresolved/fail markers",
      },
      {
        code: "mandatory_version_mismatch",
        title: "Mandatory Version Mismatch",
        matched:
          /v1\.1\.0|v1\.1\.1/i.test(low) &&
          /v1\.0\.0/i.test(low) &&
          /(still using|production is still|not fully available in prod)/i.test(low),
        pattern: "mixed backend versions with production mismatch phrase",
      },
    ];

    return {
      gate: "Phase4",
      signals,
      hold: signals.some((s) => s.matched),
    };
  }

  const signals = [
    {
      code: "mandatory_requirement_failed_or_blocked",
      title: "Mandatory Requirement Failed Or Blocked",
      matched: /(result:\s*fail|\bblocked\b|not-run|not run)/i.test(low),
      pattern: "explicit fail/blocked/not-run evidence",
    },
    {
      code: "critical_defect_open",
      title: "Critical Defect Open",
      matched: /(critical defect|severity:\s*critical|open blocker)/i.test(low),
      pattern: "critical defect still open",
    },
    {
      code: "conditional_retest_unmet",
      title: "Conditional Retest Unmet",
      matched: /(retest required|conditional_unmet|pending validation)/i.test(low),
      pattern: "retest/conditional requirement not satisfied",
    },
    {
      code: "agent4_unresolved_hard_blocker_unclosed",
      title: "Agent4 Unresolved Hard Blocker Unclosed",
      matched:
        /(agent4.*hold|unresolved.*agent4|continuity blocker)/i.test(low) &&
        !/(approved|ready for test promotion|no blocking issues remain)/i.test(low),
      pattern: "A4 unresolved continuity without closure statement",
    },
  ];

  return {
    gate: "Phase5",
    signals,
    hold: signals.some((s) => s.matched),
  };
}

function collectEvidenceLines(text, filePath, signal, maxSnippets = 3) {
  const lines = text.split(/\r?\n/);
  const snippets = [];

  for (let idx = 0; idx < lines.length; idx += 1) {
    const line = lines[idx];
    if (line.trim().length === 0) {
      continue;
    }

    const low = line.toLowerCase();
    if (
      signal.code === "critical_service_unhealthy" &&
      /(backend|incorrect|prod)/i.test(low)
    ) {
      snippets.push({ filePath, line: idx + 1, snippet: line.trim() });
    }
    if (
      signal.code === "unresolved_error_or_critical_log" &&
      /(fail|unresolved|inconsistency|incorrect occupancy)/i.test(low)
    ) {
      snippets.push({ filePath, line: idx + 1, snippet: line.trim() });
    }
    if (
      signal.code === "mandatory_version_mismatch" &&
      /(v1\.1|v1\.0\.0|still using|production is still)/i.test(low)
    ) {
      snippets.push({ filePath, line: idx + 1, snippet: line.trim() });
    }
    if (
      signal.code === "mandatory_requirement_failed_or_blocked" &&
      /(fail|blocked|not run|not-run)/i.test(low)
    ) {
      snippets.push({ filePath, line: idx + 1, snippet: line.trim() });
    }
    if (
      signal.code === "critical_defect_open" &&
      /(critical|open blocker|severity)/i.test(low)
    ) {
      snippets.push({ filePath, line: idx + 1, snippet: line.trim() });
    }
    if (
      signal.code === "conditional_retest_unmet" &&
      /(retest|required|pending validation|conditional)/i.test(low)
    ) {
      snippets.push({ filePath, line: idx + 1, snippet: line.trim() });
    }
    if (
      signal.code === "agent4_unresolved_hard_blocker_unclosed" &&
      /(agent4|continuity|unresolved)/i.test(low)
    ) {
      snippets.push({ filePath, line: idx + 1, snippet: line.trim() });
    }

    if (snippets.length >= maxSnippets) {
      break;
    }
  }

  return snippets;
}

function collectEvidenceFromDocuments(documents, signal) {
  const snippets = [];
  for (const doc of documents) {
    const hits = collectEvidenceLines(doc.text, doc.filePath || doc.name, signal, 3);
    snippets.push(...hits);
    if (snippets.length >= 3) {
      return snippets.slice(0, 3);
    }
  }
  return snippets;
}

function analyze(agentId, dataset) {
  const signalSummary = readSignals(agentId, dataset.text);
  const matchedSignals = signalSummary.signals.filter((s) => s.matched);

  const reasons = matchedSignals.map((signal) => ({
    code: signal.code,
    title: signal.title,
    detail: signal.pattern,
    evidence: collectEvidenceFromDocuments(dataset.documents, signal),
  }));

  const decision = signalSummary.hold ? "HOLD" : "GO";
  const confidence = signalSummary.hold ? "high" : "medium";

  if (!signalSummary.hold) {
    reasons.push({
      code: null,
      title: "All hard release gates passed",
      detail:
        "No signal matching hard gate conditions was detected in the current evidence set.",
      evidence: [],
    });
  }

  return {
    decision,
    confidence,
    gate: signalSummary.gate,
    reasons,
    matchedSignals,
    signals: signalSummary.signals,
  };
}

function validateAnalysisSchemaLikePayload(result) {
  if (!result || typeof result !== "object") {
    return { valid: false, errors: ["analysis is missing"] };
  }

  const errors = [];
  if (result.decision !== "GO" && result.decision !== "HOLD") {
    errors.push("decision must be GO or HOLD");
  }
  if (!Array.isArray(result.reasons)) {
    errors.push("reasons must be an array");
  }
  if (!Array.isArray(result.signals)) {
    errors.push("signals must be an array");
  }
  if (typeof result.gate !== "string" || result.gate.trim().length === 0) {
    errors.push("gate must be a non-empty string");
  }

  return { valid: errors.length === 0, errors };
}

function normalizeBackendAnalysis(payload, fallbackGate) {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const findings = payload?.rule_findings?.findings;
  const signals = Array.isArray(findings)
    ? findings.map((f) => ({
        code: String(f?.code || "unknown"),
        title: String(f?.code || "unknown")
          .replace(/_/g, " ")
          .replace(/\b\w/g, (m) => m.toUpperCase()),
        matched: Boolean(f?.triggered),
        pattern: String(f?.reason || ""),
      }))
    : [];

  const reasons = Array.isArray(payload.reasons)
    ? payload.reasons.map((reason) => ({
        code: reason?.rule_code || null,
        title: String(reason?.title || "Reason"),
        detail: String(reason?.detail || ""),
        evidence: Array.isArray(reason?.evidence)
          ? reason.evidence.map((ev) => ({
              filePath: String(ev?.file_path || "unknown"),
              line: ev?.line_start ?? "-",
              snippet: String(ev?.snippet || ""),
            }))
          : [],
      }))
    : [];

  const matchedSignals = signals.filter((s) => s.matched);

  return {
    decision: String(payload.decision || "HOLD").toUpperCase(),
    confidence: String(payload.confidence || "medium").toLowerCase(),
    gate: fallbackGate,
    reasons,
    matchedSignals,
    signals,
  };
}

function buildBackendRunRequest({
  agentId,
  selectedDataset,
  runOptions,
}) {
  // For custom sets, ALWAYS send inline documents to backend, regardless of backendPreset
  if (selectedDataset?.source === "custom") {
    const payload = {
      agent: agentId,
      dataset_root: `challenge-app/Dataset/Test_Sets/${selectedDataset.id}`,
      custom_set_label: selectedDataset.label,
      documents: Array.isArray(selectedDataset.documents)
        ? selectedDataset.documents.map((doc) => ({
            name: doc.name,
            text: doc.text,
          }))
        : [],
      release_id: null,
      evaluate_all: Boolean(runOptions.evaluateAll),
      check_label: Boolean(runOptions.checkLabel),
      labels_path: null,
      fail_on_label_mismatch: Boolean(runOptions.failOnLabelMismatch),
      strict_schema: Boolean(runOptions.strictSchema),
      no_llm: Boolean(runOptions.noLlm),
    };

    if (!runOptions.evaluateAll) {
      payload.scenario_id = null;
    }

    if (agentId === "agent4") {
      payload.source_adapter_kind = "apcs_doc_bundle";
    }

    return payload;
  }

  const backendPreset = selectedDataset?.backend?.[agentId];
  if (!backendPreset) {
    return null;
  }

  const payload = {
    agent: agentId,
    dataset_root: backendPreset.datasetRoot,
    release_id: backendPreset.releaseId || null,
    evaluate_all: Boolean(runOptions.evaluateAll),
    check_label: Boolean(runOptions.checkLabel),
    labels_path: null,
    fail_on_label_mismatch: Boolean(runOptions.failOnLabelMismatch),
    strict_schema: Boolean(runOptions.strictSchema),
    no_llm: Boolean(runOptions.noLlm),
  };

  if (!runOptions.evaluateAll) {
    payload.scenario_id = backendPreset.scenarioId;
  }

  if (agentId === "agent4") {
    payload.source_adapter_kind =
      runOptions.sourceAdapterKind === "auto"
        ? backendPreset.sourceAdapterKind || "auto"
        : runOptions.sourceAdapterKind;
  }

  return payload;
}

export default function ReleaseDashboard() {
  const [customSets, setCustomSets] = useState(() => loadCustomSets());
  const [agentId, setAgentId] = useState("agent4");
  const [datasetId, setDatasetId] = useState("go");
  const [newSetName, setNewSetName] = useState("");
  const [newSetFiles, setNewSetFiles] = useState([]);
  const [createSetError, setCreateSetError] = useState("");
  const [importError, setImportError] = useState("");
  const [isBackendRunning, setIsBackendRunning] = useState(false);
  const [backendError, setBackendError] = useState("");
  const [backendResponse, setBackendResponse] = useState(null);
  const [runOptions, setRunOptions] = useState({
    evaluateAll: false,
    checkLabel: false,
    strictSchema: false,
    failOnLabelMismatch: false,
    noLlm: true,
    sourceAdapterKind: "auto",
  });

  const selectedAgent = AGENTS[agentId];

  useEffect(() => {
    let cancelled = false;

    async function syncBackendCustomSets() {
      try {
        const localCustomSets = loadCustomSets();
        const backendSets = await fetchBackendCustomSets();

        const normalizedBackendSets = backendSets.map((set) => ({
          ...set,
          persisted: true,
        }));

        const merged = [...localCustomSets];
        const existingLabels = new Set(
          merged.map((set) => String(set.label || "").trim().toLowerCase())
        );

        for (const set of normalizedBackendSets) {
          const key = String(set.label || "").trim().toLowerCase();
          if (existingLabels.has(key)) {
            continue;
          }
          existingLabels.add(key);
          merged.push(set);
        }

        const migrated = [];
        for (const set of merged) {
          if (set.source !== "custom" || set.persisted || !Array.isArray(set.documents)) {
            migrated.push(set);
            continue;
          }

          try {
            const created = await saveCustomSetToBackend({
              label: set.label,
              documents: set.documents.map((doc) => ({
                name: doc.name,
                text: doc.text,
              })),
            });
            migrated.push({
              ...created,
              persisted: true,
            });
          } catch {
            migrated.push(set);
          }
        }

        if (cancelled) {
          return;
        }

        persistCustomSets(migrated);
        setCustomSets(migrated);
      } catch {
        // Backend is optional for reading custom sets; keep localStorage fallback.
      }
    }

    syncBackendCustomSets();

    return () => {
      cancelled = true;
    };
  }, []);

  const allSets = useMemo(() => {
    return [...BUILTIN_SETS, ...customSets].map((set) =>
      normalizeSetForAnalysis(set)
    );
  }, [customSets]);

  const selectedDataset =
    allSets.find((set) => set.id === datasetId) || allSets[0];

  const localResult = useMemo(
    () => analyze(agentId, selectedDataset),
    [agentId, selectedDataset]
  );

  const backendRunRequest = useMemo(
    () =>
      buildBackendRunRequest({
        agentId,
        selectedDataset,
        runOptions,
      }),
    [agentId, selectedDataset, runOptions]
  );

  const backendDerivedResult = useMemo(() => {
    if (!backendResponse || backendResponse.mode !== "single") {
      return null;
    }
    return normalizeBackendAnalysis(backendResponse.payload, localResult.gate);
  }, [backendResponse, localResult.gate]);

  const result = backendDerivedResult || localResult;

  const agentSignalSummaries = useMemo(
    () =>
      Object.values(AGENTS).map((agent) => ({
        ...agent,
        analysis: analyze(agent.id, selectedDataset),
      })),
    [selectedDataset]
  );

  useEffect(() => {
    setBackendError("");
    setBackendResponse(null);
  }, [agentId, datasetId, runOptions.evaluateAll, runOptions.sourceAdapterKind]);

  const singleRunDiagnostics = useMemo(() => {
    if (backendResponse?.mode === "single") {
      const evaluation = backendResponse?.payload?.evaluation;
      return {
        expectedDecision: evaluation?.expected_decision || null,
        labelChecked: Boolean(evaluation?.label_check_performed),
        labelMatch:
          typeof evaluation?.match === "boolean" ? evaluation.match : null,
        schema: {
          valid: !backendResponse?.diagnostics?.schema_error_detected,
          errors: backendResponse?.diagnostics?.schema_error_detected
            ? ["schema validation failed"]
            : [],
        },
        simulatedExitCode: backendResponse?.diagnostics?.label_mismatch_detected
          ? 1
          : 0,
      };
    }

    const expectedDecision = EXPECTED_DECISION_BY_SET_ID[selectedDataset.id] || null;
    const labelChecked = runOptions.checkLabel && expectedDecision !== null;
    const labelMatch = labelChecked
      ? result.decision === expectedDecision
      : null;

    const schema = runOptions.strictSchema
      ? validateAnalysisSchemaLikePayload(result)
      : { valid: true, errors: [] };

    const shouldFail =
      runOptions.failOnLabelMismatch && labelChecked && labelMatch === false;

    return {
      expectedDecision,
      labelChecked,
      labelMatch,
      schema,
      simulatedExitCode: shouldFail ? 1 : 0,
    };
  }, [result, runOptions, selectedDataset.id]);

  const evaluateAllSummary = useMemo(() => {
    if (backendResponse?.mode === "evaluate_all") {
      const summary = backendResponse?.payload?.summary || {};
      return {
        totalScenarios: summary.total_scenarios || 0,
        goCount: (backendResponse.payload.predictions || []).filter(
          (p) => p?.decision === "GO"
        ).length,
        holdCount: (backendResponse.payload.predictions || []).filter(
          (p) => p?.decision === "HOLD"
        ).length,
        evaluatedLabels: summary.evaluated_scenarios || 0,
        matched: summary.matched || 0,
        accuracy:
          typeof summary.accuracy === "number" ? Number(summary.accuracy) : null,
      };
    }

    if (!runOptions.evaluateAll) {
      return null;
    }

    const predictions = allSets.map((set) => ({
      setId: set.id,
      label: set.label,
      decision: analyze(agentId, set).decision,
    }));

    const withExpected = predictions.filter(
      (p) => EXPECTED_DECISION_BY_SET_ID[p.setId]
    );
    const matched = withExpected.filter(
      (p) => p.decision === EXPECTED_DECISION_BY_SET_ID[p.setId]
    ).length;

    return {
      totalScenarios: predictions.length,
      goCount: predictions.filter((p) => p.decision === "GO").length,
      holdCount: predictions.filter((p) => p.decision === "HOLD").length,
      evaluatedLabels: runOptions.checkLabel ? withExpected.length : 0,
      matched: runOptions.checkLabel ? matched : 0,
      accuracy:
        runOptions.checkLabel && withExpected.length > 0
          ? Number((matched / withExpected.length).toFixed(4))
          : null,
    };
  }, [agentId, allSets, backendResponse, runOptions.checkLabel, runOptions.evaluateAll]);

  const isGo = result.decision === "GO";

  function updateRunOption(key, value) {
    setRunOptions((prev) => ({ ...prev, [key]: value }));
  }

  async function handleRunBackend() {
    if (!backendRunRequest) {
      setBackendError(
        "Backend run is not available for this set. Use built-in mapped sets."
      );
      return;
    }

    setIsBackendRunning(true);
    setBackendError("");

    try {
      const response = await fetch(`${AGENT_BACKEND_URL}/agents/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(backendRunRequest),
      });

      const data = await response.json();
      if (!response.ok) {
        const message =
          typeof data?.detail === "string"
            ? data.detail
            : `Backend error (${response.status})`;
        throw new Error(message);
      }

      setBackendResponse(data);
    } catch (error) {
      setBackendResponse(null);
      setBackendError(
        error instanceof Error ? error.message : "Unable to run backend analysis."
      );
    } finally {
      setIsBackendRunning(false);
    }
  }

  async function handleCreateSet(event) {
    event.preventDefault();
    const name = newSetName.trim();
    if (!name) {
      setCreateSetError("Set name is required.");
      return;
    }
    if (newSetFiles.length === 0) {
      setCreateSetError("Select at least one document.");
      return;
    }
    const lowerName = name.toLowerCase();
    if (
      allSets.some((set) => String(set.label || "").trim().toLowerCase() === lowerName)
    ) {
      setCreateSetError("A set with this name already exists.");
      return;
    }

    let documents;
    try {
      documents = await Promise.all(
        newSetFiles.map(async (file) => ({
          name: file.name,
          filePath: `Uploaded/${file.name}`,
          text: await readUploadedFile(file),
        }))
      );
    } catch {
      setCreateSetError("Cannot read one or more uploaded files.");
      return;
    }

    let created;
    try {
      created = await saveCustomSetToBackend({
        label: name,
        documents,
      });
    } catch (error) {
      setCreateSetError(
        error instanceof Error ? error.message : "Unable to save set to backend."
      );
      return;
    }

    created = {
      ...created,
      persisted: true,
    };
    if (created.source === "custom" && !created.backend) {
      created.backend = {
        agent4: {
          datasetRoot: `challenge-app/Dataset/Test_Sets/${created.id}`,
          sourceAdapterKind: "apcs_doc_bundle",
        },
      };
    }

    const updated = [...customSets, created];
    setCustomSets(updated);
    persistCustomSets(updated);
    setDatasetId(created.id);
    setNewSetName("");
    setNewSetFiles([]);
    setCreateSetError("");
    setImportError("");
  }

  function handleDeleteSelectedSet() {
    if (!selectedDataset || selectedDataset.source !== "custom") {
      return;
    }

    const removeSet = async () => {
      try {
        if (selectedDataset.persisted) {
          await deleteCustomSetFromBackend(selectedDataset.id);
        }

        const updated = customSets.filter((set) => set.id !== selectedDataset.id);
        setCustomSets(updated);
        persistCustomSets(updated);
        setDatasetId("go");
      } catch (error) {
        setImportError(
          error instanceof Error ? error.message : "Unable to delete custom set."
        );
      }
    };

    void removeSet();
  }

  function handleExportSets() {
    downloadJsonFile("agent-console-custom-sets.json", customSets);
  }

  async function handleImportSets(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    try {
      const raw = await readUploadedFile(file);
      const parsed = JSON.parse(raw);
      const imported = sanitizeImportedCustomSets(parsed);
      if (imported.length === 0) {
        setImportError("No valid sets were found in the imported file.");
        return;
      }

      const existingLabels = new Set(
        customSets.map((set) => String(set.label || "").trim().toLowerCase())
      );

      const deduped = imported
        .filter((set) => {
          const key = String(set.label).trim().toLowerCase();
          if (existingLabels.has(key)) {
            return false;
          }
          existingLabels.add(key);
          return true;
        })
        .map((set, index) => ({
          ...set,
          id: `${set.id}-${Date.now()}-${index}`,
        }));

      if (deduped.length === 0) {
        setImportError("All imported set names already exist.");
        return;
      }

      const updated = [...customSets, ...deduped];
      setCustomSets(updated);
      persistCustomSets(updated);
      setDatasetId(deduped[0].id);
      setImportError("");
    } catch {
      setImportError("Invalid JSON file for set import.");
    } finally {
      event.target.value = "";
    }
  }

  function handleExportCurrentAnalysis() {
    const payload = {
      generatedAtUtc: new Date().toISOString(),
      agent: {
        id: selectedAgent.id,
        name: selectedAgent.name,
        phase: selectedAgent.phase,
      },
      dataset: {
        id: selectedDataset.id,
        label: selectedDataset.label,
        source: selectedDataset.source,
        documents: selectedDataset.documents.map((doc) => ({
          name: doc.name,
          filePath: doc.filePath,
        })),
      },
      runOptions,
      diagnostics: singleRunDiagnostics,
      evaluateAllSummary,
      analysis: result,
    };

    downloadJsonFile(
      `${selectedAgent.id}-${selectedDataset.id}-analysis.json`,
      payload
    );
  }

  return (
    <section
      className="mx-auto flex h-full w-full max-w-[1600px] flex-col gap-5 overflow-y-auto px-6 pb-6"
      data-testid="agent-console"
    >
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">
              Agent Operations Console
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Select an agent and a document bundle to inspect deterministic analysis output.
            </p>
          </div>
          <div className="grid min-w-[280px] grid-cols-2 gap-3">
            {agentSignalSummaries.map((summary) => {
              const isSelected = agentId === summary.id;
              const isGoStatus = summary.analysis.decision === "GO";

              return (
                <button
                  key={summary.id}
                  type="button"
                  onClick={() => setAgentId(summary.id)}
                  data-testid={`agent-status-${summary.id}`}
                  className={`flex min-h-[76px] flex-col items-center justify-center rounded-xl border px-4 py-3 text-center shadow-sm transition ${
                    isGoStatus
                      ? "border-emerald-200 bg-emerald-100 text-emerald-800 hover:bg-emerald-50"
                      : "border-rose-200 bg-rose-100 text-rose-800 hover:bg-rose-50"
                  } ${isSelected ? "ring-2 ring-slate-900 ring-offset-2" : ""}`}
                  aria-label={`${summary.name} ${summary.analysis.decision}`}
                >
                  <span className="text-sm font-semibold text-slate-900">{summary.name}</span>
                  <span className="mt-1 text-sm font-extrabold tracking-[0.3em]">
                    {summary.analysis.decision}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-5 grid gap-5 2xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-4">
            <div>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Agent
              </h3>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-2">
                {Object.values(AGENTS).map((agent) => (
                  <button
                    key={agent.id}
                    onClick={() => setAgentId(agent.id)}
                    className={`rounded-lg border px-3 py-2 text-left text-sm transition ${
                      agentId === agent.id
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-200 bg-slate-50 text-slate-800 hover:bg-slate-100"
                    }`}
                  >
                    <p className="font-semibold">{agent.name}</p>
                    <p className="text-xs opacity-80">{agent.phase}</p>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Sets
              </h3>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {allSets.map((dataset) => (
                  <button
                    key={dataset.id}
                    onClick={() => setDatasetId(dataset.id)}
                    title={dataset.label}
                    className={`overflow-hidden rounded-lg border px-3 py-2 text-left text-sm transition ${
                      datasetId === dataset.id
                        ? "border-indigo-700 bg-indigo-50 text-indigo-900"
                        : "border-slate-200 bg-slate-50 text-slate-800 hover:bg-slate-100"
                    }`}
                  >
                    <p className="truncate font-semibold">{dataset.label}</p>
                    <p className="truncate text-xs text-slate-500">
                      {dataset.source === "built-in" ? "Built-in" : "Custom upload"}
                    </p>
                  </button>
                ))}
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={handleExportSets}
                  className="rounded border border-slate-300 bg-white px-2 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
                >
                  Export Sets
                </button>
                <label className="cursor-pointer rounded border border-slate-300 bg-white px-2 py-1.5 text-center text-xs font-semibold text-slate-700 hover:bg-slate-100">
                  Import Sets
                  <input
                    type="file"
                    accept=".json"
                    onChange={handleImportSets}
                    className="hidden"
                  />
                </label>
              </div>
              {importError ? (
                <p className="mt-2 text-xs font-medium text-rose-700">{importError}</p>
              ) : null}
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-600">
                Run Options
              </h3>
              <div className="grid gap-2 text-xs text-slate-700 sm:grid-cols-2">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={runOptions.evaluateAll}
                    onChange={(event) =>
                      updateRunOption("evaluateAll", event.target.checked)
                    }
                  />
                  Run all scenarios in the selected dataset
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={runOptions.checkLabel}
                    onChange={(event) =>
                      updateRunOption("checkLabel", event.target.checked)
                    }
                  />
                  Compare each decision with expected labels
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={runOptions.strictSchema}
                    onChange={(event) =>
                      updateRunOption("strictSchema", event.target.checked)
                    }
                  />
                  Require valid output schema
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={runOptions.failOnLabelMismatch}
                    onChange={(event) =>
                      updateRunOption("failOnLabelMismatch", event.target.checked)
                    }
                    disabled={!runOptions.checkLabel}
                  />
                  Return an error if decision and label differ
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={runOptions.noLlm}
                    onChange={(event) =>
                      updateRunOption("noLlm", event.target.checked)
                    }
                  />
                  Use deterministic rules only (no LLM calls)
                </label>
              </div>

              {agentId === "agent4" ? (
                <div className="mt-3">
                  <label className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    Dataset interpretation mode
                  </label>
                  <select
                    value={runOptions.sourceAdapterKind}
                    onChange={(event) =>
                      updateRunOption("sourceAdapterKind", event.target.value)
                    }
                    className="w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-xs"
                  >
                    <option value="auto">auto</option>
                    <option value="structured_dataset">structured_dataset</option>
                    <option value="apcs_doc_bundle">apcs_doc_bundle</option>
                  </select>
                </div>
              ) : null}
            </div>
          </div>

          <form
            onSubmit={handleCreateSet}
            className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3"
            data-testid="create-set-form"
          >
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
              Create New Set
            </h3>
            <input
              type="text"
              aria-label="Set name"
              value={newSetName}
              onChange={(event) => setNewSetName(event.target.value)}
              placeholder="Set name"
              className="w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm outline-none focus:border-slate-500"
            />
            <input
              type="file"
              aria-label="Upload documents"
              multiple
              accept=".txt,.md,.csv,.json"
              onChange={(event) =>
                setNewSetFiles(Array.from(event.target.files || []))
              }
              className="w-full text-xs text-slate-600"
            />
            {newSetFiles.length > 0 ? (
              <p className="text-xs text-slate-500">
                {newSetFiles.length} file(s) selected
              </p>
            ) : null}
            {createSetError ? (
              <p className="text-xs font-medium text-rose-700">{createSetError}</p>
            ) : null}
            <button
              type="submit"
              className="w-full rounded bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700"
            >
              Save Set
            </button>
            <div className="rounded-lg bg-white p-3 text-xs text-slate-600">
              <p className="mb-1 font-semibold text-slate-700">Selected profile</p>
              <p>{selectedAgent.description}</p>
            </div>
          </form>
        </div>
      </div>

      <header className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">
              {selectedAgent.name} · {result.gate}
            </p>
            <h3 className="text-xl font-semibold text-slate-900">{selectedDataset.label}</h3>
            <p className="mt-1 text-xs text-slate-500">
              {selectedDataset.documents.length} document(s)
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleRunBackend}
              disabled={isBackendRunning || !backendRunRequest}
              className={`rounded border px-3 py-1.5 text-xs font-semibold ${
                isBackendRunning || !backendRunRequest
                  ? "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400"
                  : "border-slate-700 bg-slate-900 text-white hover:bg-slate-800"
              }`}
            >
              {isBackendRunning ? "Running..." : "Run Agents"}
            </button>
            <button
              type="button"
              onClick={handleExportCurrentAnalysis}
              className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
            >
              Export Analysis JSON
            </button>
            <button
              type="button"
              onClick={handleDeleteSelectedSet}
              disabled={selectedDataset.source !== "custom"}
              className={`rounded border px-3 py-1.5 text-xs font-semibold ${
                selectedDataset.source === "custom"
                  ? "border-rose-300 bg-rose-50 text-rose-700 hover:bg-rose-100"
                  : "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400"
              }`}
            >
              Delete Selected Set
            </button>
          </div>
        </div>
        <p className="mt-3 text-sm text-slate-600">
          Confidence: <strong>{result.confidence}</strong> · Matched hard gates: {" "}
          <strong>{result.matchedSignals.length}</strong>
        </p>
        {singleRunDiagnostics.labelChecked ? (
          <p className="mt-2 text-xs text-slate-600">
            Label check: expected <strong>{singleRunDiagnostics.expectedDecision}</strong> ·
            match {" "}
            <strong>{singleRunDiagnostics.labelMatch ? "yes" : "no"}</strong>
          </p>
        ) : null}
        {runOptions.strictSchema ? (
          <p className="mt-1 text-xs text-slate-600">
            Schema validation: {" "}
            <strong>{singleRunDiagnostics.schema.valid ? "valid" : "invalid"}</strong>
            {!singleRunDiagnostics.schema.valid
              ? ` (${singleRunDiagnostics.schema.errors.join("; ")})`
              : ""}
          </p>
        ) : null}
        {runOptions.failOnLabelMismatch && singleRunDiagnostics.labelChecked ? (
          <p className="mt-1 text-xs text-slate-600">
            Simulated exit code: <strong>{singleRunDiagnostics.simulatedExitCode}</strong>
          </p>
        ) : null}
        {backendResponse ? (
          <p className="mt-1 text-xs text-slate-600">
            Source: <strong>backend</strong> ({backendResponse.mode})
          </p>
        ) : (
          <p className="mt-1 text-xs text-slate-500">
            Source: <strong>local preview</strong>
          </p>
        )}
        {backendError ? (
          <p className="mt-1 text-xs font-medium text-rose-700">{backendError}</p>
        ) : null}

        {evaluateAllSummary ? (
          <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
            <p className="font-semibold uppercase tracking-wide text-slate-500">
              evaluate-all summary
            </p>
            <p className="mt-1">
              total: <strong>{evaluateAllSummary.totalScenarios}</strong> · GO: {" "}
              <strong>{evaluateAllSummary.goCount}</strong> · HOLD: {" "}
              <strong>{evaluateAllSummary.holdCount}</strong>
            </p>
            {runOptions.checkLabel ? (
              <p className="mt-1">
                labels: <strong>{evaluateAllSummary.evaluatedLabels}</strong> · matched: {" "}
                <strong>{evaluateAllSummary.matched}</strong> · accuracy: {" "}
                <strong>
                  {evaluateAllSummary.accuracy === null
                    ? "n/a"
                    : evaluateAllSummary.accuracy}
                </strong>
              </p>
            ) : null}
          </div>
        ) : null}

        <ul className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
          {selectedDataset.documents.map((doc) => (
            <li key={doc.filePath} className="rounded bg-slate-100 px-2 py-1">
              {doc.name}
            </li>
          ))}
        </ul>
      </header>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
        <article
          className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
          data-testid="reasons-panel"
        >
          <h4 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Reasons & Evidence
          </h4>
          <div className="space-y-4">
            {result.reasons.map((reason) => (
              <div key={reason.title} className="rounded-lg border border-slate-200 p-4">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-slate-900">{reason.title}</p>
                  {reason.code ? (
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600">
                      {reason.code}
                    </span>
                  ) : null}
                </div>
                <p className="text-sm text-slate-600">{reason.detail}</p>

                {reason.evidence.length > 0 ? (
                  <ul className="mt-3 space-y-2 text-xs text-slate-600">
                    {reason.evidence.map((evidence, idx) => (
                      <li key={`${reason.title}-${idx}`} className="rounded bg-slate-50 p-2">
                        <p className="font-mono text-[11px] text-slate-500">
                          {evidence.filePath}:{evidence.line}
                        </p>
                        <p>{evidence.snippet}</p>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>
        </article>

        <article
          className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
          data-testid="signal-table"
        >
          <h4 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Agent Signal Overview
          </h4>
          <div className="grid gap-4">
            {agentSignalSummaries.map((summary) => {
              const hasHold = summary.analysis.decision === "HOLD";
              const matchedCodes = summary.analysis.matchedSignals.map((signal) => signal.code);

              return (
                <section
                  key={summary.id}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                  data-testid={`signal-summary-${summary.id}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{summary.name}</p>
                      <p className="text-xs text-slate-500">{summary.phase}</p>
                    </div>
                    <div
                      className={`rounded-full border px-3 py-1 text-xs font-extrabold tracking-[0.2em] ${
                        hasHold
                          ? "border-rose-200 bg-rose-100 text-rose-800"
                          : "border-emerald-200 bg-emerald-100 text-emerald-800"
                      }`}
                    >
                      {summary.analysis.decision}
                    </div>
                  </div>

                  <p className="mt-3 text-xs text-slate-600">
                    Matched hard gates: <strong>{summary.analysis.matchedSignals.length}</strong>
                  </p>

                  {matchedCodes.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {matchedCodes.map((code) => (
                        <span
                          key={`${summary.id}-${code}`}
                          className="rounded bg-rose-100 px-2 py-1 font-mono text-[11px] text-rose-700"
                        >
                          {code}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-emerald-700">No hard gates matched.</p>
                  )}

                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 text-[11px] uppercase text-slate-400">
                          <th className="py-2 pr-3">Rule</th>
                          <th className="py-2 pr-3">Status</th>
                          <th className="py-2">Pattern</th>
                        </tr>
                      </thead>
                      <tbody>
                        {summary.analysis.signals.map((signal) => (
                          <tr key={`${summary.id}-${signal.code}`} className="border-b border-slate-100 last:border-b-0">
                            <td className="py-2 pr-3 font-mono text-[11px]">{signal.code}</td>
                            <td className="py-2 pr-3">
                              {signal.matched ? (
                                <span className="font-semibold text-rose-700">matched</span>
                              ) : (
                                <span className="text-emerald-700">clear</span>
                              )}
                            </td>
                            <td className="py-2 text-slate-600">{signal.pattern}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              );
            })}
          </div>
        </article>
      </div>
    </section>
  );
}
