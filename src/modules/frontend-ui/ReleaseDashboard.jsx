import { useMemo, useState } from "react";
import goEmailText from "../../../Dataset/GO Documents/APCS_Emails_v1.0.txt?raw";
import holdEmailText from "../../../Dataset/HOLD Documents/APCS_Emails_v1.0.txt?raw";
import goStableEmailText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Emails_v1.0.txt?raw";
import goStableRequirementsText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Requirements_v1.0.txt?raw";
import goStableVersionInventoryText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Module_Version_Inventory_v1.0.txt?raw";
import goStableTestProcedureText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Test_Procedure_v1.0.txt?raw";
import goStableVddText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_VDD_v1.0.txt?raw";
import goStableInconsistenciesText from "../../../Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Inconsistencies_map_v1.0.txt?raw";
import holdRuntimeEmailText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Emails_v1.0.txt?raw";
import holdRuntimeRequirementsText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Requirements_v1.0.txt?raw";
import holdRuntimeVersionInventoryText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Module_Version_Inventory_v1.0.txt?raw";
import holdRuntimeTestProcedureText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Test_Procedure_v1.0.txt?raw";
import holdRuntimeVddText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_VDD_v1.0.txt?raw";
import holdRuntimeInconsistenciesText from "../../../Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Inconsistencies_map_v1.0.txt?raw";
import holdA4EmailText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Emails_v1.0.txt?raw";
import holdA4RequirementsText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Requirements_v1.0.txt?raw";
import holdA4VersionInventoryText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Module_Version_Inventory_v1.0.txt?raw";
import holdA4TestProcedureText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Test_Procedure_v1.0.txt?raw";
import holdA4VddText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_VDD_v1.0.txt?raw";
import holdA4InconsistenciesText from "../../../Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Inconsistencies_map_v1.0.txt?raw";

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

const BUILTIN_SETS = [
  {
    id: "go",
    label: "GO Documents",
    source: "built-in",
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
      {
        name: "APCS_Inconsistencies_map_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_GO_STABLE_v1.1.2/APCS_Inconsistencies_map_v1.0.txt",
        text: goStableInconsistenciesText,
      },
    ],
  },
  {
    id: "hold-runtime-unresolved-v112",
    label: "SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2",
    source: "built-in",
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
      {
        name: "APCS_Inconsistencies_map_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_RUNTIME_UNRESOLVED_v1.1.2/APCS_Inconsistencies_map_v1.0.txt",
        text: holdRuntimeInconsistenciesText,
      },
    ],
  },
  {
    id: "hold-a4-continuity-v112",
    label: "SET_HOLD_A4_CONTINUITY_v1.1.2",
    source: "built-in",
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
      {
        name: "APCS_Inconsistencies_map_v1.0.txt",
        filePath:
          "Dataset/Test_Sets/SET_HOLD_A4_CONTINUITY_v1.1.2/APCS_Inconsistencies_map_v1.0.txt",
        text: holdA4InconsistenciesText,
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

function normalizeSetForAnalysis(set) {
  const docs = Array.isArray(set.documents) ? set.documents : [];
  const combinedText = docs.map((d) => String(d.text || "")).join("\n\n");
  return {
    id: set.id,
    label: set.label,
    source: set.source,
    documents: docs,
    text: combinedText,
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

export default function ReleaseDashboard() {
  const [customSets, setCustomSets] = useState(() => loadCustomSets());
  const [agentId, setAgentId] = useState("agent4");
  const [datasetId, setDatasetId] = useState("go");
  const [newSetName, setNewSetName] = useState("");
  const [newSetFiles, setNewSetFiles] = useState([]);
  const [createSetError, setCreateSetError] = useState("");
  const [importError, setImportError] = useState("");
  const [runOptions, setRunOptions] = useState({
    evaluateAll: false,
    checkLabel: false,
    strictSchema: false,
    failOnLabelMismatch: false,
    sourceAdapterKind: "auto",
  });

  const selectedAgent = AGENTS[agentId];

  const allSets = useMemo(() => {
    return [...BUILTIN_SETS, ...customSets].map((set) =>
      normalizeSetForAnalysis(set)
    );
  }, [customSets]);

  const selectedDataset =
    allSets.find((set) => set.id === datasetId) || allSets[0];

  const result = useMemo(
    () => analyze(agentId, selectedDataset),
    [agentId, selectedDataset]
  );

  const singleRunDiagnostics = useMemo(() => {
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
  }, [agentId, allSets, runOptions.checkLabel, runOptions.evaluateAll]);

  const isGo = result.decision === "GO";

  function updateRunOption(key, value) {
    setRunOptions((prev) => ({ ...prev, [key]: value }));
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

    const created = {
      id: `custom-${Date.now()}`,
      label: name,
      source: "custom",
      documents,
    };

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

    const updated = customSets.filter((set) => set.id !== selectedDataset.id);
    setCustomSets(updated);
    persistCustomSets(updated);
    setDatasetId("go");
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
          <div
            data-testid="decision-badge"
            className={`inline-flex min-w-28 items-center justify-center rounded-full border px-6 py-3 text-base font-extrabold tracking-[0.2em] shadow-sm ${
              isGo
                ? "border-emerald-200 bg-emerald-100 text-emerald-800"
                : "border-rose-200 bg-rose-100 text-rose-800"
            }`}
          >
            {result.decision}
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
                  evaluate-all
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={runOptions.checkLabel}
                    onChange={(event) =>
                      updateRunOption("checkLabel", event.target.checked)
                    }
                  />
                  check-label
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={runOptions.strictSchema}
                    onChange={(event) =>
                      updateRunOption("strictSchema", event.target.checked)
                    }
                  />
                  strict-schema
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
                  fail-on-label-mismatch
                </label>
              </div>

              {agentId === "agent4" ? (
                <div className="mt-3">
                  <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    source-adapter-kind
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
            Signal Table
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase text-slate-400">
                  <th className="py-2 pr-3">Rule</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2">Pattern</th>
                </tr>
              </thead>
              <tbody>
                {result.signals.map((signal) => (
                  <tr key={signal.code} className="border-b border-slate-100">
                    <td className="py-2 pr-3 font-mono text-xs">{signal.code}</td>
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
        </article>
      </div>
    </section>
  );
}
