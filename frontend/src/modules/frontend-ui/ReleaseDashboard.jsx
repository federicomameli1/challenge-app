import { useEffect, useMemo, useState } from "react";
import {
  buildAgentRunRequest,
  buildBrainRunRequest,
  buildIdleAnalysis,
  deleteCustomSetFromBackend,
  fetchBackendBundleSets,
  fetchBackendCustomSets,
  fetchBackendScenarios,
  normalizeAgentRunResponse,
  normalizeBrainStageResponse,
  normalizeSetForAnalysis,
  runBackendAgent,
  runBackendBrain,
  saveCustomSetToBackend,
  validateBackendDataset,
} from "./dashboardApi.js";

const AGENTS = {
  agent4: {
    id: "agent4",
    name: "Release Readiness Analyst",
    legacyName: "Agent 4",
    phase: "Phase 4",
    description:
      "Assesses DEV-to-TEST promotion readiness from APCS operational and documentary evidence.",
  },
  agent5: {
    id: "agent5",
    name: "Test Evidence Analyst",
    legacyName: "Agent 5",
    phase: "Phase 5",
    description:
      "Assesses Phase 5 test readiness, defects, and continuity closure after Phase 4.",
  },
};

const BRAIN_NAME = "Release Flow Coordinator";
const BRAIN_DESCRIPTION =
  "Runs Phase 4 then Phase 5 using the backend orchestration layer, including the gate that blocks Phase 5 when Phase 4 ends in HOLD unless you explicitly override it.";

const DEFAULT_RUN_OPTIONS = {
  evaluateAll: false,
  checkLabel: false,
  strictSchema: false,
  failOnLabelMismatch: false,
  noLlm: false,
  sourceAdapterKind: "auto",
};

const CUSTOM_SET_STORAGE_KEY = "hitachi-agent-console-custom-sets";

function loadCustomSets() {
  try {
    const raw = localStorage.getItem(CUSTOM_SET_STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((set) => set && typeof set.id === "string")
      : [];
  } catch {
    return [];
  }
}

function persistCustomSets(sets) {
  localStorage.setItem(CUSTOM_SET_STORAGE_KEY, JSON.stringify(sets));
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

function readUploadedFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error(`Cannot encode ${file.name}`));
        return;
      }

      const separatorIndex = reader.result.indexOf(",");
      resolve(
        separatorIndex >= 0 ? reader.result.slice(separatorIndex + 1) : reader.result
      );
    };
    reader.onerror = () => reject(new Error(`Cannot encode ${file.name}`));
    reader.readAsDataURL(file);
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
        isBinary: Boolean(doc?.isBinary),
        contentBase64: doc?.contentBase64 || doc?.content_base64 || null,
        contentType: doc?.contentType || null,
      }))
      .filter((doc) => doc.text.trim().length > 0 || Boolean(doc.contentBase64));

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

function createEmptyProfile(supported = false) {
  return {
    supported,
    loading: supported,
    error: "",
    validation: null,
    scenarios: [],
    defaultScenarioId: null,
    requestedDatasetRoot: null,
    resolvedDatasetRoot: null,
  };
}

function buildInitialProfiles(dataset) {
  return {
    agent4: createEmptyProfile(Boolean(dataset?.backend?.agent4)),
    agent5: createEmptyProfile(Boolean(dataset?.backend?.agent5)),
  };
}

function formatTimestamp(value) {
  if (!value) {
    return "n/a";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleString();
}

function collectValidationNotes(profile) {
  const validation = profile?.validation;
  if (!validation || typeof validation !== "object") {
    return [];
  }

  const notes = [];
  const missingOptional = Array.isArray(validation.missing_optional)
    ? validation.missing_optional
    : [];
  const presentOptional = Array.isArray(validation.present_optional)
    ? validation.present_optional
    : [];
  const adapterKind =
    validation.adapter_kind || validation.detected?.kind || validation.adapter_report?.adapter_name;

  if (adapterKind) {
    notes.push(`adapter: ${adapterKind}`);
  }
  if (presentOptional.length > 0) {
    notes.push(`optional present: ${presentOptional.join(", ")}`);
  }
  if (missingOptional.length > 0) {
    notes.push(`optional missing: ${missingOptional.join(", ")}`);
  }
  if (Array.isArray(validation.notes)) {
    notes.push(...validation.notes.map((item) => String(item)));
  }

  return notes;
}

function decisionBadgeClasses(decision) {
  if (decision === "GO") {
    return "border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300";
  }
  if (decision === "HOLD") {
    return "border-rose-200 bg-rose-100 text-rose-800 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-300";
  }
  if (decision === "BATCH") {
    return "border-sky-200 bg-sky-100 text-sky-800 dark:border-sky-800 dark:bg-sky-950/50 dark:text-sky-300";
  }
  if (decision === "LOADING") {
    return "border-amber-200 bg-amber-100 text-amber-800 dark:border-amber-800 dark:bg-amber-900/50 dark:text-amber-200";
  }
  return "border-slate-200 bg-slate-100 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400";
}

function supportLabel(profile, run) {
  if (profile?.loading && !run) {
    return "loading";
  }
  if (!profile?.supported) {
    return "not mapped";
  }
  if (run?.source === "brain") {
    return "brain";
  }
  if (run?.source === "bootstrap") {
    return "baseline";
  }
  if (run?.source === "manual") {
    return "manual";
  }
  return "idle";
}

function stageLabel(stageName) {
  return AGENTS[stageName]?.name || String(stageName || "stage");
}

function LoadingSpinner({ className = "" }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
    />
  );
}

async function persistImportedSet(candidate) {
  try {
    const created = await saveCustomSetToBackend({
      label: candidate.label,
      documents: candidate.documents.map((doc) => ({
        name: doc.name,
        text: doc.text,
        content_base64: doc.contentBase64 || null,
        content_type: doc.contentType || null,
      })),
    });
    return {
      ...created,
      persisted: true,
    };
  } catch {
    return candidate;
  }
}

export default function ReleaseDashboard() {
  const [bundleSets, setBundleSets] = useState([]);
  const [bundleSetsLoading, setBundleSetsLoading] = useState(true);
  const [customSets, setCustomSets] = useState(() => loadCustomSets());
  const [agentId, setAgentId] = useState("agent4");
  const [datasetId, setDatasetId] = useState(null);
  const [newSetName, setNewSetName] = useState("");
  const [newSetFiles, setNewSetFiles] = useState([]);
  const [createSetError, setCreateSetError] = useState("");
  const [importError, setImportError] = useState("");
  const [backendError, setBackendError] = useState("");
  const [brainError, setBrainError] = useState("");
  const [runOptions, setRunOptions] = useState(DEFAULT_RUN_OPTIONS);
  const [allowAgent5AfterAgent4Hold, setAllowAgent5AfterAgent4Hold] =
    useState(false);
  const [agentRuns, setAgentRuns] = useState({});
  const [brainRun, setBrainRun] = useState(null);
  const [isAgentRunning, setIsAgentRunning] = useState(false);
  const [isBrainRunning, setIsBrainRunning] = useState(false);
  const [isCreateSetOpen, setIsCreateSetOpen] = useState(false);
  const [activePanel, setActivePanel] = useState("analysis");
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [datasetProfiles, setDatasetProfiles] = useState(() =>
    buildInitialProfiles(null)
  );

  const allSets = useMemo(
    () => [...bundleSets, ...customSets].map((set) => normalizeSetForAnalysis(set)),
    [bundleSets, customSets]
  );

  const selectedDataset =
    allSets.find((set) => set.id === datasetId) ?? allSets[0] ?? null;
  const selectedAgent = AGENTS[agentId];
  const selectedProfile = datasetProfiles[agentId] || createEmptyProfile(false);
  const currentRun = agentRuns[agentId] || null;
  const availableAgentIds = Object.values(AGENTS)
    .filter((agent) => selectedDataset?.backend?.[agent.id])
    .map((agent) => agent.id);
  const selectedAgentIndex = Math.max(availableAgentIds.indexOf(agentId), 0);
  const previousAgentId =
    availableAgentIds.length > 1
      ? availableAgentIds[
          (selectedAgentIndex - 1 + availableAgentIds.length) % availableAgentIds.length
        ]
      : null;
  const nextAgentId =
    availableAgentIds.length > 1
      ? availableAgentIds[(selectedAgentIndex + 1) % availableAgentIds.length]
      : null;
  const currentAnalysis =
    currentRun?.analysis ||
    buildIdleAnalysis(
      agentId,
      selectedProfile.loading
        ? "Loading baseline snapshot from the backend."
        : selectedProfile.error
          ? selectedProfile.error
          : selectedProfile.supported
            ? "Run the backend analysis to inspect this dataset."
            : "This dataset is not mapped for the selected analyst."
    );

  const brainAvailable = Boolean(
    selectedDataset?.backend?.agent4 && selectedDataset?.backend?.agent5
  );

  useEffect(() => {
    let cancelled = false;
    async function loadBundles() {
      try {
        const items = await fetchBackendBundleSets();
        if (!cancelled) {
          setBundleSets(items);
          if (items.length > 0) {
            setDatasetId((prev) => prev ?? items[0].id);
          }
        }
      } catch {
        // backend unavailable — leave bundleSets empty
      } finally {
        if (!cancelled) setBundleSetsLoading(false);
      }
    }
    loadBundles();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (selectedDataset?.backend?.[agentId]) {
      return;
    }

    const fallbackAgent = Object.values(AGENTS).find(
      (agent) => selectedDataset?.backend?.[agent.id]
    );
    if (fallbackAgent && fallbackAgent.id !== agentId) {
      setAgentId(fallbackAgent.id);
    }
  }, [
    agentId,
    selectedDataset?.id,
    selectedDataset?.backend?.agent4,
    selectedDataset?.backend?.agent5,
  ]);

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

        const persisted = [];
        for (const set of merged) {
          if (set.source !== "custom" || set.persisted || !Array.isArray(set.documents)) {
            persisted.push(set);
            continue;
          }
          persisted.push(await persistImportedSet(set));
        }

        if (cancelled) {
          return;
        }

        persistCustomSets(persisted);
        setCustomSets(persisted);
      } catch {
        // Keep localStorage fallback if the backend is unavailable.
      }
    }

    syncBackendCustomSets();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    setBackendError("");
    setBrainError("");
    setBrainRun(null);
    setAgentRuns({});
    setDatasetProfiles(buildInitialProfiles(selectedDataset));

    async function loadProfilesAndBootstrap() {
      const nextProfiles = buildInitialProfiles(selectedDataset);
      const nextRuns = {};

      await Promise.all(
        Object.values(AGENTS).map(async (agent) => {
        const preset = selectedDataset?.backend?.[agent.id];
        if (!preset) {
          nextProfiles[agent.id] = {
            ...createEmptyProfile(false),
            error: "No backend mapping for this analyst in the selected dataset.",
          };
          return;
        }

        const inspectPayload = {
          agent: agent.id,
          dataset_root: preset.datasetRoot,
          source_adapter_kind:
            agent.id === "agent4" ? preset.sourceAdapterKind || "auto" : "auto",
        };

        try {
          const [validation, scenariosResponse] = await Promise.all([
            validateBackendDataset(inspectPayload),
            fetchBackendScenarios(inspectPayload).catch((error) => ({
              items: [],
              error: error.message,
            })),
          ]);

          const scenarios = Array.isArray(scenariosResponse?.items)
            ? scenariosResponse.items
            : [];

          nextProfiles[agent.id] = {
            supported: true,
            loading: false,
            error: scenariosResponse?.error || "",
            validation,
            scenarios,
            defaultScenarioId:
              preset.scenarioId ||
              scenarios.find((item) => item?.scenario_id)?.scenario_id ||
              null,
            requestedDatasetRoot: preset.datasetRoot,
            resolvedDatasetRoot:
              validation?.resolved_dataset_root ||
              scenariosResponse?.resolved_dataset_root ||
              preset.datasetRoot,
          };

          const bootstrapPayload = buildAgentRunRequest({
            agentId: agent.id,
            selectedDataset,
            runOptions: {
              ...DEFAULT_RUN_OPTIONS,
              // Keep the dashboard bootstrap snappy; the user-triggered run still
              // defaults to the richer LLM report.
              noLlm: true,
              sourceAdapterKind: preset.sourceAdapterKind || "auto",
            },
            defaultScenarioId:
              preset.scenarioId ||
              scenarios.find((item) => item?.scenario_id)?.scenario_id ||
              null,
          });

          if (bootstrapPayload) {
            try {
              const response = await runBackendAgent(bootstrapPayload);
              nextRuns[agent.id] = normalizeAgentRunResponse(
                agent.id,
                response,
                "bootstrap"
              );
            } catch (error) {
              nextProfiles[agent.id].error = nextProfiles[agent.id].error
                ? `${nextProfiles[agent.id].error} · ${error.message}`
                : error.message;
            }
          }
        } catch (error) {
          nextProfiles[agent.id] = {
            supported: true,
            loading: false,
            error: error instanceof Error ? error.message : "Cannot inspect dataset.",
            validation: null,
            scenarios: [],
            defaultScenarioId: preset.scenarioId || null,
            requestedDatasetRoot: preset.datasetRoot,
            resolvedDatasetRoot: null,
          };
        }
        })
      );

      if (cancelled) {
        return;
      }

      setDatasetProfiles(nextProfiles);
      setAgentRuns(nextRuns);
    }

    loadProfilesAndBootstrap();

    return () => {
      cancelled = true;
    };
  }, [
    selectedDataset?.id,
    selectedDataset?.backend?.agent4?.datasetRoot,
    selectedDataset?.backend?.agent5?.datasetRoot,
  ]);

  const agentStatusSummaries = useMemo(
    () =>
      Object.values(AGENTS).map((agent) => {
        const profile = datasetProfiles[agent.id] || createEmptyProfile(false);
        const run = agentRuns[agent.id] || null;

        let decision = "IDLE";
        if (!profile.supported) {
          decision = "N/A";
        } else if (profile.loading && !run) {
          decision = "LOADING";
        } else if (run?.analysis?.decision) {
          decision = run.analysis.decision;
        }

        return {
          ...agent,
          profile,
          run,
          decision,
          analysis:
            run?.analysis ||
            buildIdleAnalysis(
              agent.id,
              profile.loading
                ? "Loading baseline snapshot from the backend."
                : profile.error || "No backend run yet."
            ),
          source: supportLabel(profile, run),
        };
      }),
    [agentRuns, datasetProfiles]
  );

  const currentEvaluation = currentRun?.payload?.evaluation || null;
  const evaluateAllSummary =
    currentRun?.mode === "evaluate_all" ? currentRun.evaluateAllSummary : null;
  const evaluateAllPredictions =
    currentRun?.mode === "evaluate_all" ? currentRun.predictions : [];
  const currentValidationNotes = collectValidationNotes(selectedProfile);
  const brainStageSummary = brainRun?.stages || null;
  const hasEvaluateAllLabelMetrics = Boolean(
    evaluateAllSummary &&
      Array.isArray(currentRun?.payload?.rows) &&
      currentRun.payload.rows.length > 0
  );
  const isEvaluateAllRun = currentRun?.mode === "evaluate_all";
  const resultDecision = isEvaluateAllRun
    ? evaluateAllSummary
      ? evaluateAllSummary.holdCount > 0 && evaluateAllSummary.goCount > 0
        ? "BATCH"
        : evaluateAllSummary.holdCount > 0
          ? "HOLD"
          : evaluateAllSummary.goCount > 0
            ? "GO"
            : "BATCH"
      : "BATCH"
    : currentAnalysis.decision;
  const resultSummary = isEvaluateAllRun
    ? evaluateAllSummary
      ? `${evaluateAllSummary.totalScenarios} scenarios analyzed. GO: ${evaluateAllSummary.goCount}, HOLD: ${evaluateAllSummary.holdCount}.`
      : "Evaluate-all run loaded from the backend."
    : currentAnalysis.summary || currentAnalysis.humanAction;
  const resultConfidence = isEvaluateAllRun
    ? `${evaluateAllSummary?.totalScenarios ?? 0} scenarios`
    : currentAnalysis.confidence;
  const resultDecisionType = isEvaluateAllRun ? "batch_run" : currentAnalysis.decisionType;
  const resultPolicyVersion = isEvaluateAllRun
    ? currentRun?.payload?.predictions?.[0]?.policy_version || "n/a"
    : currentAnalysis.policyVersion || "n/a";
  const resultUpdatedAt = isEvaluateAllRun
    ? currentRun?.receivedAt || null
    : currentAnalysis.timestampUtc;
  const detailTabs = [
    {
      id: "analysis",
      label: isEvaluateAllRun ? "Scenarios" : "Reasons",
    },
    { id: "status", label: "Analyst Status" },
    { id: "diagnostics", label: "Diagnostics" },
    { id: "dataset", label: "Dataset" },
  ];

  function updateRunOption(key, value) {
    setRunOptions((previous) => ({
      ...previous,
      [key]: value,
      ...(key === "checkLabel" && !value
        ? { failOnLabelMismatch: false }
        : {}),
    }));
  }

  async function handleRunBackend() {
    const payload = buildAgentRunRequest({
      agentId,
      selectedDataset,
      runOptions,
      defaultScenarioId: selectedProfile.defaultScenarioId,
    });

    if (!payload) {
      setBackendError("Backend run is not available for this dataset and analyst.");
      return;
    }

    setIsAgentRunning(true);
    setBackendError("");

    try {
      const response = await runBackendAgent(payload);
      setBackendError("");
      setAgentRuns((previous) => ({
        ...previous,
        [agentId]: normalizeAgentRunResponse(agentId, response, "manual"),
      }));
    } catch (error) {
      setBackendError(
        error instanceof Error ? error.message : "Unable to run backend analysis."
      );
    } finally {
      setIsAgentRunning(false);
    }
  }

  async function handleRunBrain() {
    const payload = buildBrainRunRequest({
      selectedDataset,
      runOptions,
      agent4ScenarioId: datasetProfiles.agent4?.defaultScenarioId || null,
      agent5ScenarioId: datasetProfiles.agent5?.defaultScenarioId || null,
      allowAgent5AfterAgent4Hold,
    });

    if (!payload) {
      setBrainError(
        "Full workflow requires both Release Readiness Analyst and Test Evidence Analyst mappings."
      );
      return;
    }

    setIsBrainRunning(true);
    setBrainError("");

    try {
      const response = await runBackendBrain(payload);
      setBrainError("");
      const report = response?.payload || null;
      setBrainRun(report);

      if (report?.stages) {
        setAgentRuns((previous) => {
          const next = { ...previous };
          for (const agent of Object.values(AGENTS)) {
            const stage = report.stages?.[agent.id];
            if (stage?.status === "success" && stage?.payload) {
              next[agent.id] = normalizeBrainStageResponse(agent.id, stage);
            }
          }
          return next;
        });
      }
    } catch (error) {
      setBrainError(
        error instanceof Error ? error.message : "Unable to run the full workflow."
      );
    } finally {
      setIsBrainRunning(false);
    }
  }

  async function handleCreateSet(event) {
    event.preventDefault();

    const name = newSetName.trim();
    if (!name) {
      setCreateSetError("Dataset name is required.");
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
      setCreateSetError("A dataset with this name already exists.");
      return;
    }

    let documents;
    try {
      documents = await Promise.all(
        newSetFiles.map(async (file) => {
          const isDocx = /\.docx$/i.test(file.name);
          return {
            name: file.name,
            filePath: `Uploaded/${file.name}`,
            text: isDocx ? null : await readUploadedFile(file),
            content_base64: isDocx ? await readUploadedFileAsBase64(file) : null,
            content_type: file.type || null,
          };
        })
      );
    } catch {
      setCreateSetError("Cannot read one or more uploaded files.");
      return;
    }

    try {
      const created = await saveCustomSetToBackend({
        label: name,
        documents,
      });

      const normalized = {
        ...created,
        persisted: true,
      };

      const updated = [...customSets, normalized];
      setCustomSets(updated);
      persistCustomSets(updated);
      setDatasetId(normalized.id);
      setNewSetName("");
      setNewSetFiles([]);
      setCreateSetError("");
      setImportError("");
      setIsCreateSetOpen(false);
    } catch (error) {
      setCreateSetError(
        error instanceof Error ? error.message : "Unable to save dataset to backend."
      );
    }
  }

  async function handleDeleteSelectedSet() {
    if (!selectedDataset || selectedDataset.source !== "custom") {
      return;
    }

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
        error instanceof Error ? error.message : "Unable to delete custom dataset."
      );
    }
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
        setImportError("No valid custom sets found in the imported file.");
        return;
      }

      const existingLabels = new Set(
        customSets.map((set) => String(set.label || "").trim().toLowerCase())
      );

      const deduped = imported.filter((set) => {
        const key = String(set.label || "").trim().toLowerCase();
        if (existingLabels.has(key)) {
          return false;
        }
        existingLabels.add(key);
        return true;
      });

      const persisted = [];
      for (const set of deduped) {
        persisted.push(await persistImportedSet(set));
      }

      const updated = [...customSets, ...persisted];
      setCustomSets(updated);
      persistCustomSets(updated);
      setImportError("");
    } catch (error) {
      setImportError(
        error instanceof Error ? error.message : "Cannot import the selected file."
      );
    } finally {
      event.target.value = "";
    }
  }

  function handleExportCurrentAnalysis() {
    downloadJsonFile("challenge-analysis.json", {
      dataset: {
        id: selectedDataset?.id ?? null,
        label: selectedDataset?.label ?? null,
      },
      selectedAgent,
      runOptions,
      currentRun,
      brainRun,
    });
  }

  const quickFacts = [
    {
      label: "Dataset",
      value: selectedDataset?.label ?? "–",
    },
    {
      label: "Analyst",
      value: selectedAgent?.name ?? "–",
    },
    {
      label: "Report mode",
      value: runOptions.noLlm ? "Rules-only fallback" : "LLM-assisted default",
    },
    {
      label: "Demo mode",
      value: "Single demo case",
    },
  ];

  return (
    <section className="h-full overflow-hidden px-3 py-3" data-testid="agent-console">
      <div className="mx-auto flex h-full max-w-[1820px] flex-col gap-3">
<div className="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[300px_minmax(0,1fr)_330px]">
          <aside className="min-h-0 space-y-4 overflow-y-auto pr-1">
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Analysts
              </p>
              <div className="mt-3 grid gap-3">
                {Object.values(AGENTS).map((agent) => {
                  const unavailable = !selectedDataset?.backend?.[agent.id];
                  return (
                    <button
                      key={agent.id}
                      type="button"
                      onClick={() => setAgentId(agent.id)}
                      disabled={unavailable}
                      className={`rounded-2xl border px-4 py-4 text-left text-sm transition ${
                        agentId === agent.id
                          ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                          : unavailable
                            ? "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500"
                            : "border-slate-200 bg-slate-50 text-slate-800 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                      }`}
                    >
                      <p className="font-semibold">{agent.name}</p>
                      <p className="mt-1 text-xs opacity-80">
                        {agent.phase} · {agent.legacyName}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="flex min-h-0 flex-col rounded-3xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Datasets
                </p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setCreateSetError("");
                      setIsCreateSetOpen(true);
                    }}
                    className="rounded-full border border-slate-900 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
                  >
                    Upload Document Dataset
                  </button>
                  <button
                    type="button"
                    onClick={handleDeleteSelectedSet}
                    disabled={selectedDataset?.source !== "custom"}
                    className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${
                      selectedDataset?.source === "custom"
                        ? "border-rose-300 bg-rose-50 text-rose-700 hover:bg-rose-100 dark:border-rose-700 dark:bg-rose-950/50 dark:text-rose-300 dark:hover:bg-rose-900/50"
                        : "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500"
                    }`}
                  >
                    Delete Selected Dataset
                  </button>
                </div>
              </div>

              <div className="mt-3 min-h-0 space-y-3 overflow-y-auto pr-1">
                {bundleSetsLoading && (
                  <p className="text-xs text-slate-400 dark:text-slate-500">Loading datasets…</p>
                )}
                {allSets.map((dataset) => {
                  const isSelected = datasetId === dataset.id;
                  const supportedForAgent = Boolean(dataset?.backend?.[agentId]);
                  return (
                    <button
                      key={dataset.id}
                      type="button"
                      onClick={() => setDatasetId(dataset.id)}
                      title={dataset.label}
                      className={`w-full rounded-2xl border px-4 py-4 text-left text-sm transition ${
                        isSelected
                          ? "border-sky-600 bg-sky-50 text-sky-950 dark:border-sky-600 dark:bg-sky-950/50 dark:text-sky-200"
                          : "border-slate-200 bg-slate-50 text-slate-800 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="break-words font-semibold leading-snug">{dataset.label}</p>
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {dataset.backend?.agent4 && (
                              <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-700 dark:bg-violet-950/50 dark:text-violet-300">
                                A4
                              </span>
                            )}
                            {dataset.backend?.agent5 && (
                              <span className="rounded-full bg-teal-100 px-2 py-0.5 text-[10px] font-semibold text-teal-700 dark:bg-teal-950/50 dark:text-teal-300">
                                A5
                              </span>
                            )}
                            {dataset.source === "custom" && (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
                                Custom
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              {importError ? (
                <p className="mt-3 text-xs font-medium text-rose-700 dark:text-rose-400">{importError}</p>
              ) : null}
            </div>

          </aside>

          <main className="min-h-0 space-y-4 overflow-y-auto pr-1">
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Run Analysis
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-slate-700 dark:border-sky-800 dark:bg-sky-950/50 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={!runOptions.noLlm}
                      onChange={(event) => updateRunOption("noLlm", !event.target.checked)}
                    />
                    Enable LLM report
                  </label>
                  <button
                    type="button"
                    onClick={handleRunBackend}
                    disabled={isAgentRunning || !selectedProfile.supported}
                    className={`inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold ${
                      isAgentRunning || !selectedProfile.supported
                        ? "cursor-not-allowed border border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500"
                        : "border border-slate-900 bg-slate-900 text-white hover:bg-slate-800 dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
                    }`}
                    aria-busy={isAgentRunning ? "true" : "false"}
                  >
                    {isAgentRunning ? (
                      <>
                        <LoadingSpinner />
                        Running analysis...
                      </>
                    ) : (
                      "Run Selected Analysis"
                    )}
                  </button>
                </div>
              </div>

              <div className="mt-4">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800">
                  <button
                    type="button"
                    onClick={() => setShowAdvancedOptions((previous) => !previous)}
                    className="flex w-full items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3 text-left text-sm font-semibold text-slate-800 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                    aria-expanded={showAdvancedOptions ? "true" : "false"}
                  >
                    <span>Advanced options</span>
                    <span className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      {showAdvancedOptions ? "Hide" : "Click to open"}
                    </span>
                  </button>

                  {showAdvancedOptions ? (
                    <div className="mt-4 grid gap-3 text-sm text-slate-700 dark:text-slate-200">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={runOptions.checkLabel}
                          onChange={(event) => updateRunOption("checkLabel", event.target.checked)}
                        />
                        Compare decisions against benchmark labels
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={runOptions.strictSchema}
                          onChange={(event) => updateRunOption("strictSchema", event.target.checked)}
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

                      {agentId === "agent4" ? (
                        <div>
                          <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                            Dataset interpretation mode
                          </label>
                          <select
                            value={runOptions.sourceAdapterKind}
                            onChange={(event) =>
                              updateRunOption("sourceAdapterKind", event.target.value)
                            }
                            className="w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                          >
                            <option value="auto">auto</option>
                            <option value="structured_dataset">structured_dataset</option>
                            <option value="apcs_doc_bundle">apcs_doc_bundle</option>
                          </select>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                      Click the button above to show schema, label, and adapter controls.
                    </p>
                  )}
                </div>
              </div>

              {backendError ? (
                <p className="mt-3 text-sm font-medium text-rose-700 dark:text-rose-400">{backendError}</p>
              ) : null}
              {selectedProfile.error ? (
                <p className="mt-2 text-sm font-medium text-rose-700 dark:text-rose-400">{selectedProfile.error}</p>
              ) : null}
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Current result
                </p>
                <button
                  type="button"
                  onClick={handleExportCurrentAnalysis}
                  className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                >
                  Export Analysis JSON
                </button>
              </div>
              <div
                className={`relative mt-3 rounded-3xl border border-slate-200 bg-slate-50 p-5 transition dark:border-slate-700 dark:bg-slate-800 ${
                  isAgentRunning ? "overflow-hidden ring-2 ring-sky-100 dark:ring-sky-900" : ""
                }`}
              >
                {isAgentRunning ? (
                  <>
                    <div className="absolute inset-x-0 top-0 h-1 animate-pulse bg-gradient-to-r from-sky-200 via-sky-500 to-sky-200" />
                    <div
                      className="mb-4 inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wide text-sky-700 dark:border-sky-800 dark:bg-slate-900 dark:text-sky-300"
                      aria-live="polite"
                    >
                      <LoadingSpinner className="h-3.5 w-3.5" />
                      Preparing updated analysis
                    </div>
                  </>
                ) : null}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => previousAgentId && setAgentId(previousAgentId)}
                        disabled={!previousAgentId}
                        aria-label="Show previous analyst result"
                        className={`inline-flex h-9 w-9 items-center justify-center rounded-full border text-base font-semibold ${
                          previousAgentId
                            ? "border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                            : "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-600"
                        }`}
                      >
                        ‹
                      </button>
                      <button
                        type="button"
                        onClick={() => nextAgentId && setAgentId(nextAgentId)}
                        disabled={!nextAgentId}
                        aria-label="Show next analyst result"
                        className={`inline-flex h-9 w-9 items-center justify-center rounded-full border text-base font-semibold ${
                          nextAgentId
                            ? "border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                            : "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-600"
                        }`}
                      >
                        ›
                      </button>
                    </div>
                    <div>
                      <p
                        className="text-sm font-semibold text-slate-900 dark:text-slate-100"
                        data-testid="current-result-analyst-name"
                      >
                        {selectedAgent?.name ?? "–"}
                      </p>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{selectedDataset?.label ?? "–"}</p>
                    </div>
                  </div>
                  <span
                    className={`rounded-full border px-3 py-1 font-extrabold tracking-[0.2em] ${decisionBadgeClasses(
                      resultDecision
                    )}`}
                  >
                    {resultDecision}
                  </span>
                </div>

                <div className="mt-4 rounded-3xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-900">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                      {resultDecisionType === "batch_run"
                        ? "Batch report"
                        : String(resultDecisionType || "").includes("llm")
                          ? "LLM-assisted report"
                          : "Deterministic report"}
                    </span>
                    {!runOptions.noLlm ? (
                      <span className="rounded-full bg-sky-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-sky-700 dark:bg-sky-950/50 dark:text-sky-300">
                        Demo default
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-4 text-xl font-semibold leading-8 text-slate-900 dark:text-slate-100">
                    {resultSummary}
                  </p>
                  {!isEvaluateAllRun && !runOptions.noLlm ? (
                    <p className="mt-3 text-sm text-slate-600 dark:text-slate-200">
                      This central report is the LLM-refined explanation of the deterministic
                      verdict.
                    </p>
                  ) : null}
                </div>
                {!isEvaluateAllRun && currentAnalysis.humanAction ? (
                  <p className="mt-4 text-sm text-slate-600 dark:text-slate-200">
                    Next action: <strong>{currentAnalysis.humanAction}</strong>
                  </p>
                ) : null}

                <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-2xl border border-slate-200 bg-white p-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                    Confidence: <strong>{resultConfidence}</strong>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                    Decision type: <strong>{resultDecisionType}</strong>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                    Policy: <strong>{resultPolicyVersion}</strong>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                    Updated: <strong>{formatTimestamp(resultUpdatedAt)}</strong>
                  </div>
                </div>

                {currentRun?.diagnostics ? (
                  <p className="mt-4 text-sm text-slate-600 dark:text-slate-200">
                    Schema valid:{" "}
                    <strong>
                      {currentRun.diagnostics.schema_error_detected ? "no" : "yes"}
                    </strong>
                    {" · "}
                    mismatch detected:{" "}
                    <strong>
                      {currentRun.diagnostics.label_mismatch_detected ? "yes" : "no"}
                    </strong>
                  </p>
                ) : null}
                {currentRun?.diagnostics?.llm_warning ? (
                  <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-200">
                    <strong>LLM fallback:</strong> {currentRun.diagnostics.llm_warning}
                  </p>
                ) : null}
              </div>
            </div>

            <article
              className="flex min-h-0 flex-1 flex-col rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900"
              data-testid="reasons-panel"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Detail panels
                  </p>
                  <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                    Switch between explanation, analyst status, diagnostics, and dataset info.
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {detailTabs.map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setActivePanel(tab.id)}
                      className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                        activePanel === tab.id
                          ? "border border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                          : "border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:text-slate-100 dark:hover:bg-slate-700"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">
                {activePanel === "analysis" ? (
                  isEvaluateAllRun ? (
                    evaluateAllPredictions.length > 0 ? (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                          <thead>
                            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                              <th className="py-2 pr-3">Scenario</th>
                              <th className="py-2 pr-3">Decision</th>
                              <th className="py-2 pr-3">Confidence</th>
                              <th className="py-2 pr-3">Label</th>
                              <th className="py-2">Summary</th>
                            </tr>
                          </thead>
                          <tbody>
                            {evaluateAllPredictions.map((item) => (
                              <tr
                                key={item.scenarioId}
                                className="border-b border-slate-100 last:border-b-0 dark:border-slate-700"
                              >
                                <td className="py-2 pr-3 font-mono text-xs">{item.scenarioId}</td>
                                <td className="py-2 pr-3 font-semibold">{item.decision}</td>
                                <td className="py-2 pr-3 text-slate-600 dark:text-slate-300">{item.confidence}</td>
                                <td className="py-2 pr-3 text-slate-600 dark:text-slate-300">
                                  {item.expectedDecision ? (
                                    <span>
                                      {item.expectedDecision} ·{" "}
                                      <strong>{item.labelMatch ? "match" : "mismatch"}</strong>
                                    </span>
                                  ) : (
                                    "n/a"
                                  )}
                                </td>
                                <td className="py-2 text-slate-600 dark:text-slate-300">{item.summary || "n/a"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500 dark:text-slate-400">No evaluate-all predictions returned.</p>
                    )
                  ) : currentAnalysis.reasons.length > 0 ? (
                    <div className="space-y-4">
                      {currentAnalysis.reasons.map((reason) => (
                        <div
                          key={`${reason.title}-${reason.code || "reason"}`}
                          className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800"
                        >
                          <div className="mb-1 flex flex-wrap items-center gap-2">
                            <p className="font-semibold text-slate-900 dark:text-slate-100">{reason.title}</p>
                            {reason.code ? (
                              <span className="rounded bg-white px-2 py-0.5 font-mono text-xs text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                                {reason.code}
                              </span>
                            ) : null}
                          </div>
                          <p className="text-sm text-slate-600 dark:text-slate-200">
                            {reason.detail || "No additional detail."}
                          </p>

                          {reason.evidence.length > 0 ? (
                            <ul className="mt-3 space-y-2 text-xs text-slate-600 dark:text-slate-300">
                              {reason.evidence.map((evidence, index) => (
                                <li
                                  key={`${reason.title}-${index}`}
                                  className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900"
                                >
                                  <p
                                    className="font-mono text-[11px] text-slate-500 break-all dark:text-slate-400"
                                    title={evidence.fullPath || evidence.filePath}
                                  >
                                    {evidence.filePath}:{evidence.line}
                                  </p>
                                  {evidence.snippet ? (
                                    <p className="mt-1 whitespace-pre-wrap break-words">{evidence.snippet}</p>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500 dark:text-slate-300">{currentAnalysis.summary}</p>
                  )
                ) : null}

                {activePanel === "status" ? (
                  <article className="min-w-0 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800">
                    <h4 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      Analyst Status
                    </h4>
                    <div className="grid gap-4">
                      {agentStatusSummaries.map((summary) => (
                        <section
                          key={summary.id}
                          className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="min-w-0">
                              <p className="break-words text-sm font-semibold text-slate-900 dark:text-slate-100">
                                {summary.name}
                              </p>
                              <p className="break-words text-xs text-slate-500 dark:text-slate-400">
                                {summary.legacyName} · {summary.phase}
                              </p>
                            </div>
                            <div
                              className={`rounded-full border px-3 py-1 text-xs font-extrabold tracking-[0.2em] ${decisionBadgeClasses(
                                summary.decision
                              )}`}
                            >
                              {summary.decision}
                            </div>
                          </div>

                          <p className="mt-3 text-xs text-slate-600 dark:text-slate-400">
                            Source: <strong>{summary.source}</strong>
                          </p>
                          <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                            Matched hard gates:{" "}
                            <strong>{summary.analysis.matchedSignals.length}</strong>
                          </p>
                          {summary.analysis.summary ? (
                            <p className="mt-2 break-words text-xs text-slate-600 dark:text-slate-400">
                              {summary.analysis.summary}
                            </p>
                          ) : null}
                        </section>
                      ))}
                    </div>
                  </article>
                ) : null}

                {activePanel === "diagnostics" ? (
                  <div className="space-y-4">
                    {currentEvaluation?.label_check_performed ? (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        Label check: expected <strong>{currentEvaluation.expected_decision}</strong> ·
                        match <strong> {currentEvaluation.match ? "yes" : "no"}</strong>
                      </div>
                    ) : null}

                    {evaluateAllSummary ? (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <p className="font-semibold text-slate-800 dark:text-slate-200">Evaluate-all summary</p>
                        <p className="mt-2">
                          Total <strong>{evaluateAllSummary.totalScenarios}</strong> · GO{" "}
                          <strong>{evaluateAllSummary.goCount}</strong> · HOLD{" "}
                          <strong>{evaluateAllSummary.holdCount}</strong>
                        </p>
                        <p className="mt-1">
                          Schema validity rate:{" "}
                          <strong>
                            {evaluateAllSummary.schemaValidityRate === null
                              ? "n/a"
                              : evaluateAllSummary.schemaValidityRate}
                          </strong>
                        </p>
                        {hasEvaluateAllLabelMetrics ? (
                          <p className="mt-1">
                            Labels <strong>{evaluateAllSummary.evaluatedLabels}</strong> · matched{" "}
                            <strong>{evaluateAllSummary.matched}</strong> · accuracy{" "}
                            <strong>
                              {evaluateAllSummary.accuracy === null
                                ? "n/a"
                                : evaluateAllSummary.accuracy}
                            </strong>
                          </p>
                        ) : null}
                      </div>
                    ) : null}

                    {currentAnalysis.coverageMetrics ? (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <p className="font-semibold text-slate-800 dark:text-slate-200">Coverage metrics</p>
                        <ul className="mt-2 space-y-1">
                          {Object.entries(currentAnalysis.coverageMetrics).map(([key, value]) => (
                            <li key={key}>
                              {key}: <strong>{String(value)}</strong>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {currentAnalysis.crossPhaseContinuityFlags ? (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <p className="font-semibold text-slate-800 dark:text-slate-200">Cross-phase continuity</p>
                        <ul className="mt-2 space-y-1">
                          {Object.entries(currentAnalysis.crossPhaseContinuityFlags).map(
                            ([key, value]) => (
                              <li key={key}>
                                {key}:{" "}
                                <strong>
                                  {Array.isArray(value) ? value.join(", ") || "[]" : String(value)}
                                </strong>
                              </li>
                            )
                          )}
                        </ul>
                      </div>
                    ) : null}

                    {currentAnalysis.missingArtifacts.length > 0 ? (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <p className="font-semibold text-slate-800 dark:text-slate-200">Missing artifacts</p>
                        <ul className="mt-2 space-y-1">
                          {currentAnalysis.missingArtifacts.map((item) => (
                            <li key={item} className="font-mono text-xs">
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {brainStageSummary ? (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <p className="font-semibold text-slate-800 dark:text-slate-200">Last orchestration stages</p>
                        <ul className="mt-2 space-y-1">
                          {Object.entries(brainStageSummary).map(([stageName, stage]) => (
                            <li key={stageName}>
                              {stageLabel(stageName)}:{" "}
                              <strong>{String(stage?.status || "unknown").toUpperCase()}</strong>
                              {stage?.decision ? <> · decision <strong>{stage.decision}</strong></> : null}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {!currentEvaluation?.label_check_performed &&
                    !evaluateAllSummary &&
                    !currentAnalysis.coverageMetrics &&
                    !currentAnalysis.crossPhaseContinuityFlags &&
                    currentAnalysis.missingArtifacts.length === 0 &&
                    !brainStageSummary ? (
                      <p className="text-sm text-slate-500 dark:text-slate-400">No extra diagnostics available for this run.</p>
                    ) : null}
                  </div>
                ) : null}

                {activePanel === "dataset" ? (
                  <div className="space-y-4">
                    <div className="grid gap-3 md:grid-cols-2">
                      {quickFacts.map((fact) => (
                        <div key={fact.label} className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                            {fact.label}
                          </p>
                          <p className="mt-2 text-sm font-medium text-slate-800 dark:text-slate-200">{fact.value}</p>
                        </div>
                      ))}
                    </div>

                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                      <p className="font-semibold text-slate-800 dark:text-slate-200">Dataset inspection</p>
                      <p className="mt-2 break-words">
                        requested root:{" "}
                        <span className="font-mono">{selectedProfile.requestedDatasetRoot || "n/a"}</span>
                      </p>
                      {selectedProfile.resolvedDatasetRoot ? (
                        <p className="mt-1 break-words">
                          resolved root:{" "}
                          <span className="font-mono">{selectedProfile.resolvedDatasetRoot}</span>
                        </p>
                      ) : null}
                      <p className="mt-1">
                        demo mapping:{" "}
                        <strong>{selectedProfile.supported ? "available" : "not available"}</strong>
                      </p>
                      {currentValidationNotes.length > 0 ? (
                        <ul className="mt-2 space-y-1">
                          {currentValidationNotes.map((note) => (
                            <li key={note}>{note}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>

                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800">
                      <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">Included documents</p>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500 dark:text-slate-400">
                        {(selectedDataset?.documents ?? []).map((doc) => (
                          <span key={doc.filePath} className="rounded-full bg-white px-3 py-1.5 dark:bg-slate-900">
                            {doc.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            </article>
          </main>

          <aside className="min-h-0 space-y-4 overflow-y-auto pr-1">
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">
                {BRAIN_NAME}
              </h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{BRAIN_DESCRIPTION}</p>

              <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                <p>
                  The coordinator runs the default demo case for the selected dataset across
                  Phase 4 and Phase 5.
                </p>
                <label className="mt-3 flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={allowAgent5AfterAgent4Hold}
                    onChange={(event) =>
                      setAllowAgent5AfterAgent4Hold(event.target.checked)
                    }
                  />
                  Allow Phase 5 to continue even if Phase 4 ends in HOLD
                </label>
              </div>

              <button
                type="button"
                onClick={handleRunBrain}
                disabled={isBrainRunning || !brainAvailable}
                className={`mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold ${
                  isBrainRunning || !brainAvailable
                    ? "cursor-not-allowed border border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500"
                    : "border border-slate-900 bg-slate-900 text-white hover:bg-slate-800 dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
                }`}
                aria-busy={isBrainRunning ? "true" : "false"}
              >
                {isBrainRunning ? (
                  <>
                    <LoadingSpinner />
                    Running full workflow...
                  </>
                ) : (
                  "Run Full Workflow"
                )}
              </button>

              {!brainAvailable ? (
                <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                  Full workflow is available only when both analysts are mapped in the selected dataset.
                </p>
              ) : null}
              {brainError ? (
                <p className="mt-2 text-xs font-medium text-rose-700 dark:text-rose-400">{brainError}</p>
              ) : null}

              {brainRun ? (
                <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  <p className="font-semibold text-slate-800 dark:text-slate-200">Last orchestration</p>
                  <p className="mt-2">
                    Status: <strong>{String(brainRun.status || "unknown").toUpperCase()}</strong>
                  </p>
                </div>
              ) : null}
            </div>

            <article
              className="min-w-0 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900"
              data-testid="signal-table"
            >
              <h4 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Analyst Status
              </h4>
              <div className="space-y-3">
                {agentStatusSummaries.map((summary) => (
                  <section
                    key={summary.id}
                    className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800"
                    data-testid={`signal-summary-${summary.id}`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="break-words text-sm font-semibold text-slate-900 dark:text-slate-100">
                          {summary.name}
                        </p>
                        <p className="break-words text-xs text-slate-500 dark:text-slate-400">
                          {summary.legacyName} · {summary.phase}
                        </p>
                      </div>
                      <div
                        data-testid={`agent-status-${summary.id}`}
                        className={`rounded-full border px-3 py-1 text-xs font-extrabold tracking-[0.2em] ${decisionBadgeClasses(
                          summary.decision
                        )}`}
                      >
                        {summary.decision}
                      </div>
                    </div>
                    <p className="mt-3 text-xs text-slate-600 dark:text-slate-400">
                      Source: <strong>{summary.source}</strong>
                    </p>
                    {summary.analysis.summary ? (
                      <p className="mt-2 break-words text-xs text-slate-600 dark:text-slate-400">
                        {summary.analysis.summary}
                      </p>
                    ) : null}
                  </section>
                ))}
              </div>
            </article>
          </aside>
        </div>
      </div>

      {isCreateSetOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 px-4 dark:bg-slate-950/60">
          <div className="w-full max-w-xl rounded-3xl border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                  Upload Document Dataset
                </h3>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                  Add your own evidence bundle without leaving the dashboard.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsCreateSetOpen(false)}
                className="rounded-full border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-800"
              >
                Close
              </button>
            </div>

            <form
              onSubmit={handleCreateSet}
              className="mt-5 space-y-3"
              data-testid="create-set-form"
            >
              <input
                type="text"
                aria-label="Dataset name"
                value={newSetName}
                onChange={(event) => setNewSetName(event.target.value)}
                placeholder="Dataset name"
                className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-slate-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder-slate-500 dark:focus:border-slate-400"
              />
              <input
                type="file"
                aria-label="Upload documents"
                multiple
                accept=".txt,.md,.csv,.json,.log,.docx"
                onChange={(event) =>
                  setNewSetFiles(Array.from(event.target.files || []))
                }
                className="w-full text-xs text-slate-600 dark:text-slate-400"
              />
              {newSetFiles.length > 0 ? (
                <p className="text-xs text-slate-500 dark:text-slate-400">{newSetFiles.length} file(s) selected</p>
              ) : null}
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Use APCS text or `.docx` bundles for {AGENTS.agent4.name}, or structured CSV bundles for {AGENTS.agent5.name}. Uploaded datasets are persisted in the backend.
              </p>
              {createSetError ? (
                <p className="text-xs font-medium text-rose-700 dark:text-rose-400">{createSetError}</p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <button
                  type="submit"
                  className="rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
                >
                  Save Dataset
                </button>
                <button
                  type="button"
                  onClick={() => setIsCreateSetOpen(false)}
                  className="rounded-2xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}
