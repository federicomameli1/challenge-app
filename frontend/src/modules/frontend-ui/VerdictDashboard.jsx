import { useCallback, useEffect, useState } from "react";
import {
  approveCiDeployment,
  buildAgentRunRequest,
  buildIdleAnalysis,
  fetchBackendBundleSets,
  fetchBackendScenarios,
  fetchCiPendingDeployments,
  fetchSubjectCiRuns,
  normalizeAgentRunResponse,
  normalizeSetForAnalysis,
  runBackendAgent,
} from "./dashboardApi.js";

const SUBJECT_REPO_KEY = "hitachi-ci-subject-repo";

const GATES = [
  {
    id: "gate_dev_test",
    agentId: "agent4",
    from: "DEV",
    to: "TEST",
    label: "Release Readiness",
    description: "Validates operational and documentary evidence for DEV → TEST promotion.",
  },
  {
    id: "gate_test_prod",
    agentId: "agent5",
    from: "TEST",
    to: "PROD",
    label: "Test Evidence",
    description: "Validates test coverage, defects, and continuity for TEST → PROD promotion.",
  },
];

const DEFAULT_RUN_OPTIONS = {
  noLlm: false,
  strictSchema: false,
  checkLabel: false,
  failOnLabelMismatch: false,
  sourceAdapterKind: "auto",
};

// ──────────────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────────────

function LoadingSpinner({ className = "h-4 w-4" }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
    />
  );
}

function VerdictBadge({ decision, large = false }) {
  const base = large
    ? "inline-flex items-center gap-3 rounded-2xl border-2 px-7 py-3.5 text-2xl font-black tracking-[0.3em]"
    : "inline-flex items-center rounded-full border px-3 py-1 text-xs font-extrabold tracking-[0.2em]";

  if (decision === "GO")
    return (
      <span
        className={`${base} border-emerald-300 bg-emerald-100 text-emerald-800 dark:border-emerald-600 dark:bg-emerald-950/70 dark:text-emerald-300`}
      >
        GO
      </span>
    );
  if (decision === "HOLD")
    return (
      <span
        className={`${base} border-rose-300 bg-rose-100 text-rose-800 dark:border-rose-600 dark:bg-rose-950/70 dark:text-rose-300`}
      >
        HOLD
      </span>
    );
  if (decision === "LOADING")
    return (
      <span
        className={`${base} border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950/70 dark:text-amber-300`}
      >
        {large && <LoadingSpinner className="h-6 w-6" />}
        {large ? "Analyzing…" : "…"}
      </span>
    );
  return (
    <span
      className={`${base} border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500`}
    >
      {large ? "Waiting" : "—"}
    </span>
  );
}

function EnvNode({ label, state }) {
  const isActive = state === "active";
  const isReady = state === "ready";
  const isLive = state === "live";
  const highlight = isActive || isReady || isLive;

  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className={`flex h-16 w-24 flex-col items-center justify-center gap-1.5 rounded-2xl border-2 transition-colors ${
          highlight
            ? "border-emerald-300 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-950/30"
            : "border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50"
        }`}
      >
        <span
          className={`text-sm font-bold ${
            highlight
              ? "text-emerald-700 dark:text-emerald-400"
              : "text-slate-400 dark:text-slate-500"
          }`}
        >
          {label}
        </span>
        {isActive && (
          <span className="h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-emerald-300 dark:ring-emerald-700" />
        )}
        {isLive && (
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
        )}
      </div>
      <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400 dark:text-slate-500">
        {isActive ? "Active" : isReady ? "Ready" : isLive ? "Live" : "Locked"}
      </span>
    </div>
  );
}

function Connector({ decision }) {
  const isGo = decision === "GO";
  const isHold = decision === "HOLD";
  return (
    <div
      className={`h-0.5 w-10 flex-shrink-0 transition-colors ${
        isGo
          ? "bg-emerald-400 dark:bg-emerald-600"
          : isHold
            ? "bg-rose-400 dark:bg-rose-600"
            : "bg-slate-200 dark:bg-slate-700"
      }`}
    />
  );
}

function GateNode({ decision }) {
  const isGo = decision === "GO";
  const isHold = decision === "HOLD";
  const isLoading = decision === "LOADING";

  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className={`flex h-16 w-28 items-center justify-center rounded-2xl border-2 transition-colors ${
          isGo
            ? "border-emerald-300 bg-emerald-100 dark:border-emerald-600 dark:bg-emerald-950/50"
            : isHold
              ? "border-rose-300 bg-rose-100 dark:border-rose-600 dark:bg-rose-950/50"
              : isLoading
                ? "border-amber-200 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/40"
                : "border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800"
        }`}
      >
        <VerdictBadge decision={decision} />
      </div>
      <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400 dark:text-slate-500">
        Gate
      </span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Data loading
// ──────────────────────────────────────────────────────────────────────────────

async function loadBestDataset() {
  const items = await fetchBackendBundleSets();
  const sets = items.map(normalizeSetForAnalysis);
  return (
    sets.find((s) => s.backend?.agent4 && s.backend?.agent5) ||
    sets.find((s) => s.backend?.agent4) ||
    sets[0] ||
    null
  );
}

async function runAgent(agentId, dataset) {
  const preset = dataset?.backend?.[agentId];
  if (!preset) return null;

  const scenariosResp = await fetchBackendScenarios({
    agent: agentId,
    dataset_root: preset.datasetRoot,
    source_adapter_kind: preset.sourceAdapterKind || "auto",
  }).catch(() => ({ items: [] }));

  const scenarioId =
    preset.scenarioId ||
    (Array.isArray(scenariosResp?.items)
      ? scenariosResp.items.find((s) => s?.scenario_id)?.scenario_id
      : null);

  const payload = buildAgentRunRequest({
    agentId,
    selectedDataset: dataset,
    runOptions: DEFAULT_RUN_OPTIONS,
    defaultScenarioId: scenarioId,
  });
  if (!payload) return null;

  const response = await runBackendAgent(payload);
  return normalizeAgentRunResponse(agentId, response, "auto");
}

// ──────────────────────────────────────────────────────────────────────────────
// Promote modal
// ──────────────────────────────────────────────────────────────────────────────

function PromoteModal({ gate, pendingRun, onConfirm, onCancel, isSubmitting }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 dark:bg-slate-950/70">
      <div className="w-full max-w-md rounded-3xl border border-emerald-200 bg-white p-6 shadow-2xl dark:border-emerald-800 dark:bg-slate-900">
        <p className="text-xs font-semibold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
          Confirm promotion
        </p>
        <h3 className="mt-2 text-lg font-bold text-slate-900 dark:text-slate-100">
          Promote to {gate.to}
        </h3>
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          Verdict has issued a <strong className="text-emerald-700 dark:text-emerald-400">GO</strong> for the{" "}
          <strong>{gate.from} → {gate.to}</strong> gate. This will approve the pending
          GitHub Actions deployment.
        </p>

        {pendingRun && (
          <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
            <p className="font-semibold">Workflow run #{pendingRun.runId}</p>
            <p className="mt-1 opacity-75">{pendingRun.label}</p>
          </div>
        )}

        {!pendingRun && (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
            No pending GitHub Actions deployment detected. Configure the CI
            integration in the CI/CD Pipeline tab to enable one-click promotion.
          </div>
        )}

        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={onConfirm}
            disabled={isSubmitting || !pendingRun}
            className="flex flex-1 items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50 dark:bg-emerald-700 dark:hover:bg-emerald-600"
          >
            {isSubmitting && <LoadingSpinner className="h-4 w-4" />}
            {isSubmitting ? "Promoting…" : "Confirm Promotion"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-2xl border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────────────────────────────────────

export default function VerdictDashboard() {
  const [dataset, setDataset] = useState(null);
  const [verdicts, setVerdicts] = useState({ agent4: null, agent5: null });
  const [loading, setLoading] = useState({ agent4: true, agent5: true });
  const [errors, setErrors] = useState({ agent4: "", agent5: "" });
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [expandedGate, setExpandedGate] = useState(null);
  const [promoteGate, setPromoteGate] = useState(null);
  const [pendingDeployment, setPendingDeployment] = useState(null);
  const [isPromoting, setIsPromoting] = useState(false);
  const [promoteError, setPromoteError] = useState("");
  const [promoteSuccess, setPromoteSuccess] = useState("");

  const runAnalysis = useCallback(async (ds) => {
    if (!ds) return;
    setLoading({ agent4: true, agent5: true });
    setErrors({ agent4: "", agent5: "" });
    setVerdicts({ agent4: null, agent5: null });

    await Promise.all(
      ["agent4", "agent5"].map(async (agentId) => {
        try {
          const result = await runAgent(agentId, ds);
          setVerdicts((prev) => ({ ...prev, [agentId]: result }));
        } catch (err) {
          setErrors((prev) => ({
            ...prev,
            [agentId]: err instanceof Error ? err.message : "Analysis failed.",
          }));
        } finally {
          setLoading((prev) => ({ ...prev, [agentId]: false }));
        }
      })
    );
  }, []);

  useEffect(() => {
    loadBestDataset()
      .then((ds) => {
        setDataset(ds);
        runAnalysis(ds);
      })
      .catch(() => setLoading({ agent4: false, agent5: false }));
  }, [runAnalysis]);

  async function handleRefresh() {
    if (isRefreshing || !dataset) return;
    setIsRefreshing(true);
    setPromoteSuccess("");
    setPromoteError("");
    await runAnalysis(dataset);
    setIsRefreshing(false);
  }

  async function handlePromoteClick(gate) {
    setPromoteError("");
    setPromoteSuccess("");
    setPendingDeployment(null);

    // Try to find a pending CI deployment for this environment
    const repo = localStorage.getItem(SUBJECT_REPO_KEY);
    if (repo) {
      try {
        const { items } = await fetchSubjectCiRuns(repo, 5);
        for (const run of items) {
          const deployments = await fetchCiPendingDeployments(run.id).catch(() => []);
          const match = (Array.isArray(deployments) ? deployments : []).find(
            (d) =>
              String(d?.environment?.name || "")
                .toUpperCase()
                .includes(gate.to)
          );
          if (match) {
            setPendingDeployment({
              runId: run.id,
              envId: match.id,
              label: run.display_title || run.name || `Run #${run.id}`,
            });
            break;
          }
        }
      } catch {
        // no CI runs available — show modal anyway for UX
      }
    }

    setPromoteGate(gate);
  }

  async function handlePromoteConfirm() {
    if (!promoteGate || !pendingDeployment) return;
    setIsPromoting(true);
    try {
      await approveCiDeployment({
        runId: pendingDeployment.runId,
        environmentIds: [pendingDeployment.envId],
        state: "approved",
        comment: `Verdict GO — ${promoteGate.from} → ${promoteGate.to} gate cleared.`,
      });
      setPromoteSuccess(
        `Promotion to ${promoteGate.to} approved. GitHub Actions will proceed with the deployment.`
      );
    } catch (err) {
      setPromoteError(
        err instanceof Error ? err.message : "Promotion failed. Check the CI/CD Pipeline tab."
      );
    } finally {
      setIsPromoting(false);
      setPromoteGate(null);
      setPendingDeployment(null);
    }
  }

  // ── Derived state ───────────────────────────────────────────────────────────

  const decision4 = loading.agent4 ? "LOADING" : (verdicts.agent4?.analysis?.decision ?? "IDLE");
  const decision5 = loading.agent5 ? "LOADING" : (verdicts.agent5?.analysis?.decision ?? "IDLE");

  const canPromoteToTest = decision4 === "GO";
  const canPromoteToProd = decision5 === "GO";

  const devState = "active";
  const testState = canPromoteToTest ? "ready" : "locked";
  const prodState = canPromoteToProd ? "live" : "locked";

  const isAnalyzing = loading.agent4 || loading.agent5;

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <section className="h-full overflow-y-auto px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-6">

        {/* ── Top bar ── */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
              Release Pipeline
            </p>
            {dataset && (
              <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
                Evidence bundle:{" "}
                <span className="font-medium text-slate-700 dark:text-slate-300">
                  {dataset.label}
                </span>
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isAnalyzing || isRefreshing}
            className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400 dark:hover:bg-emerald-950/50"
          >
            {isRefreshing || isAnalyzing ? (
              <LoadingSpinner className="h-4 w-4" />
            ) : (
              <span aria-hidden="true">↻</span>
            )}
            Re-analyze
          </button>
        </div>

        {/* ── Pipeline strip ── */}
        <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <p className="mb-6 text-[10px] font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500">
            Deployment pipeline
          </p>

          <div className="flex items-center justify-center gap-0 overflow-x-auto">
            <EnvNode label="DEV" state={devState} />
            <Connector decision={decision4} />
            <GateNode decision={decision4} />
            <Connector decision={decision4} />
            <EnvNode label="TEST" state={testState} />
            <Connector decision={decision5} />
            <GateNode decision={decision5} />
            <Connector decision={decision5} />
            <EnvNode label="PROD" state={prodState} />
          </div>

          {/* Inline progress caption */}
          <div className="mt-6 flex items-center justify-center gap-3 text-xs text-slate-400 dark:text-slate-500">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span>GO — promotion cleared</span>
            <span className="h-2 w-2 rounded-full bg-rose-400" />
            <span>HOLD — promotion blocked</span>
            <span className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600" />
            <span>Waiting / analyzing</span>
          </div>
        </div>

        {/* ── Feedback banners ── */}
        {promoteSuccess && (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm font-medium text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
            {promoteSuccess}
          </div>
        )}
        {promoteError && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm font-medium text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">
            {promoteError}
          </div>
        )}

        {/* ── Gate cards ── */}
        <div className="grid gap-5 md:grid-cols-2">
          {GATES.map((gate) => {
            const agentId = gate.agentId;
            const isLoading = loading[agentId];
            const error = errors[agentId];
            const verdict = verdicts[agentId]?.analysis;
            const decision = isLoading ? "LOADING" : (verdict?.decision ?? "IDLE");
            const canPromote = decision === "GO";
            const isExpanded = expandedGate === gate.id;

            return (
              <div
                key={gate.id}
                className={`flex flex-col rounded-3xl border p-6 shadow-sm transition-colors ${
                  decision === "GO"
                    ? "border-emerald-200 bg-gradient-to-b from-emerald-50 to-white dark:border-emerald-800 dark:from-emerald-950/20 dark:to-slate-900"
                    : decision === "HOLD"
                      ? "border-rose-200 bg-gradient-to-b from-rose-50 to-white dark:border-rose-800 dark:from-rose-950/20 dark:to-slate-900"
                      : "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
                }`}
              >
                {/* Gate header */}
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500">
                      {gate.from} → {gate.to}
                    </p>
                    <p className="mt-1 text-base font-bold text-slate-900 dark:text-slate-100">
                      {gate.label}
                    </p>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      {gate.description}
                    </p>
                  </div>
                  <div className="flex-shrink-0">
                    <VerdictBadge decision={decision} large />
                  </div>
                </div>

                {/* Summary */}
                {!isLoading && verdict?.summary && (
                  <p className="mt-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                    {verdict.summary}
                  </p>
                )}

                {isLoading && (
                  <div className="mt-4 flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
                    <LoadingSpinner className="h-4 w-4" />
                    Running analysis…
                  </div>
                )}

                {error && (
                  <p className="mt-4 text-sm text-rose-700 dark:text-rose-400">{error}</p>
                )}

                {/* Confidence + policy pills */}
                {verdict && !isLoading && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {verdict.confidence && verdict.confidence !== "unknown" && (
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                        Confidence: {verdict.confidence}
                      </span>
                    )}
                    {verdict.policyVersion && (
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                        Policy: {verdict.policyVersion}
                      </span>
                    )}
                  </div>
                )}

                {/* Spacer */}
                <div className="flex-1" />

                {/* Promote button */}
                <button
                  type="button"
                  onClick={() => canPromote && handlePromoteClick(gate)}
                  disabled={!canPromote || isLoading}
                  className={`mt-5 w-full rounded-2xl px-5 py-3.5 text-sm font-semibold transition ${
                    canPromote
                      ? "border border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700 active:bg-emerald-800 dark:border-emerald-700 dark:bg-emerald-700 dark:hover:bg-emerald-600"
                      : "cursor-not-allowed border border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500"
                  }`}
                >
                  {isLoading
                    ? "Analyzing…"
                    : canPromote
                      ? `Promote to ${gate.to} →`
                      : decision === "HOLD"
                        ? `Blocked — HOLD on ${gate.from} → ${gate.to}`
                        : `Promote to ${gate.to}`}
                </button>

                {/* Expand reasons */}
                {!isLoading && verdict?.reasons?.length > 0 && (
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedGate(isExpanded ? null : gate.id)
                    }
                    className="mt-3 w-full text-center text-xs font-medium text-slate-400 hover:text-slate-700 dark:text-slate-500 dark:hover:text-slate-300"
                  >
                    {isExpanded
                      ? "Hide details ↑"
                      : `View ${verdict.reasons.length} reason${verdict.reasons.length !== 1 ? "s" : ""} ↓`}
                  </button>
                )}

                {/* Reasons list */}
                {isExpanded && verdict?.reasons && (
                  <div className="mt-4 space-y-3">
                    {verdict.reasons.map((reason, i) => (
                      <div
                        key={`${reason.title}-${i}`}
                        className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                            {reason.title}
                          </p>
                          {reason.code && (
                            <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                              {reason.code}
                            </span>
                          )}
                        </div>
                        {reason.detail && (
                          <p className="mt-1.5 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                            {reason.detail}
                          </p>
                        )}
                        {reason.evidence?.length > 0 && (
                          <ul className="mt-2 space-y-1">
                            {reason.evidence.slice(0, 3).map((ev, j) => (
                              <li
                                key={j}
                                className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 font-mono text-[10px] text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
                              >
                                {ev.filePath}:{ev.line}
                                {ev.snippet && (
                                  <span className="ml-2 opacity-70">{ev.snippet}</span>
                                )}
                              </li>
                            ))}
                            {reason.evidence.length > 3 && (
                              <li className="text-[10px] text-slate-400 dark:text-slate-500">
                                +{reason.evidence.length - 3} more items
                              </li>
                            )}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Human action hint ── */}
        {!isAnalyzing && (verdict4action(verdicts.agent4) || verdict4action(verdicts.agent5)) && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4 dark:border-slate-700 dark:bg-slate-800">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500">
              Recommended actions
            </p>
            <ul className="mt-3 space-y-2 text-sm text-slate-700 dark:text-slate-300">
              {verdict4action(verdicts.agent4) && (
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-500" />
                  <span>
                    <strong>DEV → TEST:</strong> {verdicts.agent4.analysis.humanAction}
                  </span>
                </li>
              )}
              {verdict4action(verdicts.agent5) && (
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-500" />
                  <span>
                    <strong>TEST → PROD:</strong> {verdicts.agent5.analysis.humanAction}
                  </span>
                </li>
              )}
            </ul>
          </div>
        )}
      </div>

      {/* ── Promote modal ── */}
      {promoteGate && (
        <PromoteModal
          gate={promoteGate}
          pendingRun={pendingDeployment}
          onConfirm={handlePromoteConfirm}
          onCancel={() => { setPromoteGate(null); setPendingDeployment(null); }}
          isSubmitting={isPromoting}
        />
      )}
    </section>
  );
}

function verdict4action(run) {
  return run?.analysis?.humanAction ? run : null;
}
