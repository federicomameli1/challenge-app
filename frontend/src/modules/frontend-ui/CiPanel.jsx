import { useCallback, useEffect, useMemo, useState } from "react";
import {
  approveCiDeployment,
  fetchCiPendingDeployments,
  fetchCiRunDetails,
  fetchCiRuns,
  fetchCiStatus,
} from "./dashboardApi.js";

function decisionBadgeClasses(decision) {
  if (decision === "GO") return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300";
  if (decision === "HOLD") return "bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300";
  return "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400";
}

function conclusionBadgeClasses(conclusion) {
  if (conclusion === "success") return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300";
  if (conclusion === "failure") return "bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300";
  if (conclusion === "cancelled") return "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200";
  return "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400";
}

function formatTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function StageCard({ label, payload }) {
  if (!payload) return null;

  if (payload.error) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-800 dark:bg-rose-950/50">
        <p className="text-xs font-semibold uppercase tracking-wide text-rose-400">{label}</p>
        <p className="mt-1 text-sm text-rose-700 dark:text-rose-400">{payload.error}</p>
      </div>
    );
  }

  const summary = payload.summary;
  if (!summary) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-400">{label}</p>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">No data available.</p>
      </div>
    );
  }

  // Stage results card (tests + build)
  if (label === "Stage Results") {
    const tests = summary.tests || {};
    const build = summary.build || {};
    const testsPass = tests.status === "PASS";
    const buildPass = build.status === "PASS";
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
        <div className="grid grid-cols-2 gap-3">
          <div className={`rounded-xl border p-3 ${testsPass ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/50" : "border-rose-200 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/50"}`}>
            <p className={`text-xs font-semibold uppercase tracking-wide ${testsPass ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
              Tests
            </p>
            <p className={`mt-1 text-sm font-bold ${testsPass ? "text-emerald-800 dark:text-emerald-300" : "text-rose-800 dark:text-rose-300"}`}>
              {tests.status || "—"}
            </p>
          </div>
          <div className={`rounded-xl border p-3 ${buildPass ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/50" : "border-rose-200 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/50"}`}>
            <p className={`text-xs font-semibold uppercase tracking-wide ${buildPass ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
              Build
            </p>
            <p className={`mt-1 text-sm font-bold ${buildPass ? "text-emerald-800 dark:text-emerald-300" : "text-rose-800 dark:text-rose-300"}`}>
              {build.status || "—"}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Agent report card (pre-test / pre-prod)
  const isHold = summary.decision === "HOLD";
  const isGo = summary.decision === "GO";
  const borderColor = isHold ? "border-rose-200 dark:border-rose-800" : isGo ? "border-emerald-200 dark:border-emerald-800" : "border-slate-200 dark:border-slate-700";
  const bgColor = isHold ? "bg-rose-50 dark:bg-rose-950/50" : isGo ? "bg-emerald-50 dark:bg-emerald-950/50" : "bg-slate-50 dark:bg-slate-800";

  return (
    <div className={`rounded-2xl border p-4 ${borderColor} ${bgColor}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide ${decisionBadgeClasses(summary.decision)}`}>
            {summary.decision || "—"}
          </span>
          {summary.confidence ? (
            <span className="text-xs text-slate-500 dark:text-slate-400">conf: {summary.confidence}</span>
          ) : null}
        </div>
      </div>

      {summary.summary ? (
        <p className={`mt-2 text-sm leading-relaxed ${isHold ? "text-rose-800 dark:text-rose-300" : isGo ? "text-emerald-800 dark:text-emerald-300" : "text-slate-700 dark:text-slate-300"}`}>
          {summary.summary}
        </p>
      ) : null}

      {summary.human_action ? (
        <p className="mt-1.5 text-xs italic text-slate-500 dark:text-slate-400">→ {summary.human_action}</p>
      ) : null}

      {Array.isArray(summary.triggered_rules) && summary.triggered_rules.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {summary.triggered_rules.map((r) => (
            <span
              key={r}
              className="rounded-full bg-rose-100 px-2.5 py-0.5 font-mono text-[11px] font-medium text-rose-700 dark:bg-rose-950/50 dark:text-rose-400"
            >
              {r}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-slate-400 dark:text-slate-400">
        {summary.head_sha ? (
          <span className="font-mono">commit {summary.head_sha}</span>
        ) : null}
        {summary.diff_stat ? (
          <span>{summary.diff_stat}</span>
        ) : null}
        {Array.isArray(summary.release_docs_loaded) && summary.release_docs_loaded.length > 0 ? (
          <span>docs: {summary.release_docs_loaded.join(", ")}</span>
        ) : null}
      </div>
    </div>
  );
}

function RunRow({ run, isSelected, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(run.id)}
      className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
        isSelected
          ? "border-sky-400 bg-sky-50 shadow-sm dark:border-sky-600 dark:bg-sky-950/50"
          : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:hover:border-slate-600"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-semibold text-slate-800 dark:text-slate-200">
          #{run.run_number} · {run.event}
        </span>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase ${conclusionBadgeClasses(run.conclusion)}`}
        >
          {run.conclusion || run.status || "—"}
        </span>
      </div>
      <p className="mt-1 truncate text-sm text-slate-600 dark:text-slate-400" title={run.head_commit_message}>
        {run.head_commit_message || run.display_title || "(no commit message)"}
      </p>
      <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-400">
        {run.head_branch} · {run.head_sha} · {formatTime(run.updated_at)}
      </p>
    </button>
  );
}

export default function CiPanel({ standalone = false }) {
  const [status, setStatus] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [error, setError] = useState("");
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [details, setDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [pending, setPending] = useState([]);
  const [approving, setApproving] = useState(false);
  const [approveResult, setApproveResult] = useState(null);

  const refreshRuns = useCallback(async () => {
    setLoadingRuns(true);
    setError("");
    try {
      const [statusData, runsData] = await Promise.all([
        fetchCiStatus(),
        fetchCiRuns(15),
      ]);
      setStatus(statusData);
      setRuns(runsData.items);
      setSelectedRunId((current) => {
        if (!current && runsData.items.length > 0) {
          return runsData.items[0].id;
        }
        return current;
      });
    } catch (exc) {
      setError(String(exc?.message || exc));
    } finally {
      setLoadingRuns(false);
    }
  }, []);

  useEffect(() => {
    refreshRuns();
  }, [refreshRuns]);

  // Initial load with loading indicator when run selection changes
  useEffect(() => {
    let cancelled = false;
    if (!selectedRunId) {
      setDetails(null);
      setPending([]);
      return undefined;
    }
    setDetailsLoading(true);
    Promise.all([
      fetchCiRunDetails(selectedRunId).catch((exc) => ({ error: String(exc?.message || exc) })),
      fetchCiPendingDeployments(selectedRunId).catch(() => ({ items: [] })),
    ])
      .then(([detailsData, pendingData]) => {
        if (cancelled) return;
        setDetails(detailsData);
        setPending(Array.isArray(pendingData?.items) ? pendingData.items : []);
      })
      .finally(() => {
        if (!cancelled) setDetailsLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedRunId]);

  const isConfigured = Boolean(status?.configured);
  const reports = useMemo(() => details?.reports || {}, [details]);

  // Derive active-run state from the runs list (not from details, to avoid flicker on initial load)
  const selectedRun = useMemo(
    () => runs.find((r) => r.id === selectedRunId) || null,
    [runs, selectedRunId],
  );
  const hasActiveRun = useMemo(
    () => runs.some((r) => r.status !== "completed"),
    [runs],
  );
  const selectedRunIsActive = Boolean(selectedRun && selectedRun.status !== "completed");

  // Silent background refresh of details + pending (no loading spinner)
  const silentRefreshDetails = useCallback(async () => {
    if (!selectedRunId) return;
    const [detailsData, pendingData] = await Promise.all([
      fetchCiRunDetails(selectedRunId).catch(() => null),
      fetchCiPendingDeployments(selectedRunId).catch(() => ({ items: [] })),
    ]);
    if (detailsData) setDetails(detailsData);
    setPending(Array.isArray(pendingData?.items) ? pendingData.items : []);
  }, [selectedRunId]);

  // Auto-refresh run list every 20s while any run is still active
  useEffect(() => {
    if (!isConfigured || !hasActiveRun) return undefined;
    const id = setInterval(refreshRuns, 20_000);
    return () => clearInterval(id);
  }, [isConfigured, hasActiveRun, refreshRuns]);

  // Auto-refresh details every 15s while selected run is active
  useEffect(() => {
    if (!selectedRunId || !selectedRunIsActive) return undefined;
    const id = setInterval(silentRefreshDetails, 15_000);
    return () => clearInterval(id);
  }, [selectedRunId, selectedRunIsActive, silentRefreshDetails]);

  // Auto-clear approve result after 5s
  useEffect(() => {
    if (!approveResult) return undefined;
    const id = setTimeout(() => setApproveResult(null), 5000);
    return () => clearTimeout(id);
  }, [approveResult]);

  const approvableEnvironments = useMemo(() => {
    return pending
      .filter((p) => p?.current_user_can_approve !== false)
      .map((p) => ({ id: p?.environment?.id, name: p?.environment?.name }))
      .filter((e) => Number.isFinite(e.id));
  }, [pending]);

  const handleApprove = async (state) => {
    if (!selectedRunId || approvableEnvironments.length === 0) return;
    setApproving(true);
    setApproveResult(null);
    try {
      const res = await approveCiDeployment({
        runId: selectedRunId,
        environmentIds: approvableEnvironments.map((e) => e.id),
        state,
        comment: `${state === "approved" ? "Approved" : "Rejected"} from dashboard (${new Date().toISOString()})`,
      });
      setApproveResult({ ok: true, message: `Decision "${state}" sent for environments: ${approvableEnvironments.map((e) => e.name).join(", ")}.` , data: res });
      // Refresh after a short delay to let GitHub process the approval
      setTimeout(() => {
        refreshRuns();
        silentRefreshDetails();
      }, 2000);
    } catch (exc) {
      setApproveResult({ ok: false, message: String(exc?.message || exc) });
    } finally {
      setApproving(false);
    }
  };

  const outerClass = standalone
    ? "flex h-full flex-col overflow-hidden"
    : "flex flex-col rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900";

  return (
    <section data-testid="ci-panel" className={outerClass}>
      {/* Header */}
      <header className="flex shrink-0 flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            CI / CD Pipeline
          </p>
          <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-200">
            GitHub Actions · Agent 4 → Agent 5
          </h2>
          {status?.repo ? (
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">{status.repo}</code>
              {status.branch ? (
                <> · <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">{status.branch}</code></>
              ) : null}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          {hasActiveRun ? (
            <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-600">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              Live
            </span>
          ) : null}
          <button
            type="button"
            onClick={refreshRuns}
            disabled={loadingRuns}
            className="rounded-full border border-slate-300 bg-white px-4 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            {loadingRuns ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {!isConfigured ? (
        <div className="mt-4 shrink-0 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-200">
          <p className="font-semibold">CI bridge is not configured.</p>
          <p className="mt-1 text-xs">
            Set <code className="rounded bg-amber-100 px-1 dark:bg-amber-900/50">CI_BRIDGE_REPO</code> and{" "}
            <code className="rounded bg-amber-100 px-1 dark:bg-amber-900/50">CI_BRIDGE_TOKEN</code> in the backend
            environment to surface real GitHub Actions runs here.
          </p>
        </div>
      ) : null}

      {error ? (
        <p className="mt-4 shrink-0 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-300">
          {error}
        </p>
      ) : null}

      {/* Two-column layout */}
      <div className={`mt-4 grid gap-4 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)] ${standalone ? "min-h-0 flex-1 overflow-hidden" : ""}`}>

        {/* Run list */}
        <div className={`flex flex-col gap-2 ${standalone ? "overflow-y-auto pr-1" : ""}`}>
          <p className="shrink-0 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Recent runs
          </p>
          {loadingRuns ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
          ) : runs.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {isConfigured ? "No runs yet." : "Configure the CI bridge to load runs."}
            </p>
          ) : (
            runs.map((run) => (
              <RunRow
                key={run.id}
                run={run}
                isSelected={run.id === selectedRunId}
                onSelect={setSelectedRunId}
              />
            ))
          )}
        </div>

        {/* Details panel */}
        <div className={`min-w-0 ${standalone ? "overflow-y-auto pr-1" : ""}`}>
          <p className="shrink-0 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Run details
          </p>

          {detailsLoading ? (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Loading reports…</p>
          ) : !selectedRunId ? (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Select a run to inspect reports.</p>
          ) : details?.error ? (
            <p className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-300">
              {details.error}
            </p>
          ) : (
            <div className="mt-2 space-y-3">
              {/* Run meta */}
              {details?.run ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                  <span>
                    <strong>{details.run.status || "—"}</strong>
                    {details.run.conclusion ? ` · ${details.run.conclusion}` : ""}
                    {details.run.event ? ` · ${details.run.event}` : ""}
                  </span>
                  {details.run.html_url ? (
                    <a
                      href={details.run.html_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sky-700 hover:underline dark:text-sky-300"
                    >
                      Open on GitHub →
                    </a>
                  ) : null}
                </div>
              ) : null}

              <StageCard label="Pre-test (Agent 4)" payload={reports["pre-test"]} />
              <StageCard label="Stage Results" payload={reports["stage-results"]} />
              <StageCard label="Pre-prod (Agent 5)" payload={reports["pre-prod"]} />

              {/* Approval gate */}
              {pending.length > 0 ? (
                <div className="rounded-2xl border border-sky-200 bg-sky-50 p-4 dark:border-sky-800 dark:bg-sky-950/50">
                  <p className="font-semibold text-sky-900 dark:text-sky-200">Awaiting approval</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {pending.map((p, i) => (
                      <span
                        key={p?.environment?.id ?? i}
                        className="rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-medium text-sky-800 dark:bg-sky-900/50 dark:text-sky-300"
                      >
                        {p?.environment?.name || `env-${i + 1}`}
                      </span>
                    ))}
                  </div>

                  {approvableEnvironments.length > 0 ? (
                    <>
                      <p className="mt-2 text-sm text-sky-700 dark:text-sky-300">
                        Review the reports above, then approve or reject to continue the workflow.
                      </p>
                      <div className="mt-3 flex gap-2">
                        <button
                          type="button"
                          onClick={() => handleApprove("approved")}
                          disabled={approving}
                          className="rounded-full bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                        >
                          {approving ? "Sending…" : "Approve →"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleApprove("rejected")}
                          disabled={approving}
                          className="rounded-full border border-rose-300 bg-white px-4 py-1.5 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50 dark:border-rose-700 dark:bg-rose-950/50 dark:text-rose-300 dark:hover:bg-rose-900/50"
                        >
                          Reject
                        </button>
                      </div>
                    </>
                  ) : (
                    <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
                      The CI token does not have write access — approve directly on GitHub.
                    </p>
                  )}

                  {approveResult ? (
                    <p className={`mt-3 rounded-xl px-3 py-2 text-sm font-medium ${approveResult.ok ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300" : "bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300"}`}>
                      {approveResult.message}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
