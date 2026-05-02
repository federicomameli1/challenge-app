import { useCallback, useEffect, useMemo, useState } from "react";
import {
  approveCiDeployment,
  fetchCiPendingDeployments,
  fetchCiRunDetails,
  fetchCiRuns,
  fetchCiStatus,
} from "./dashboardApi.js";

function decisionBadgeClasses(decision) {
  if (decision === "GO") return "bg-emerald-100 text-emerald-800";
  if (decision === "HOLD") return "bg-rose-100 text-rose-800";
  return "bg-slate-100 text-slate-600";
}

function conclusionBadgeClasses(conclusion) {
  if (conclusion === "success") return "bg-emerald-100 text-emerald-800";
  if (conclusion === "failure") return "bg-rose-100 text-rose-800";
  if (conclusion === "cancelled") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-600";
}

function formatTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function ReportSummary({ phase, payload }) {
  if (!payload) return null;
  if (payload.error) {
    return (
      <p className="text-xs text-rose-700">
        {phase}: {payload.error}
      </p>
    );
  }
  const summary = payload.summary;
  if (!summary) {
    return <p className="text-xs text-slate-500">{phase}: no summary.</p>;
  }
  if (phase === "stage-results") {
    const tests = summary.tests || {};
    const build = summary.build || {};
    return (
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg bg-slate-50 p-2">
          <p className="font-semibold text-slate-700">Tests</p>
          <p className="text-slate-600">
            {tests.status || "—"} ({tests.outcome || "—"})
          </p>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <p className="font-semibold text-slate-700">Build</p>
          <p className="text-slate-600">
            {build.status || "—"} ({build.outcome || "—"})
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
      <div className="flex items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 font-semibold uppercase ${decisionBadgeClasses(summary.decision)}`}
        >
          {summary.decision || "—"}
        </span>
        <span className="font-medium text-slate-700">{phase}</span>
        {summary.confidence ? (
          <span className="text-slate-500">conf: {summary.confidence}</span>
        ) : null}
      </div>
      {summary.summary ? (
        <p className="mt-2 text-slate-700">{summary.summary}</p>
      ) : null}
      {summary.human_action ? (
        <p className="mt-1 italic text-slate-500">
          Next: {summary.human_action}
        </p>
      ) : null}
      {Array.isArray(summary.triggered_rules) && summary.triggered_rules.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {summary.triggered_rules.map((r) => (
            <span
              key={r}
              className="rounded-full bg-rose-50 px-2 py-0.5 font-mono text-[10px] text-rose-700"
            >
              {r}
            </span>
          ))}
        </div>
      ) : null}
      {Array.isArray(summary.release_docs_loaded) && summary.release_docs_loaded.length > 0 ? (
        <p className="mt-2 text-[10px] text-slate-400">
          Loaded release docs: {summary.release_docs_loaded.join(", ")}
        </p>
      ) : null}
      {summary.head_sha ? (
        <p className="mt-1 text-[10px] font-mono text-slate-400">
          head {summary.head_sha} · {summary.diff_stat || "no diff stat"}
        </p>
      ) : null}
    </div>
  );
}

function RunRow({ run, isSelected, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(run.id)}
      className={`w-full rounded-xl border px-3 py-2 text-left text-xs transition ${
        isSelected
          ? "border-sky-500 bg-sky-50"
          : "border-slate-200 bg-white hover:border-slate-300"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-semibold text-slate-800">
          #{run.run_number} · {run.event}
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${conclusionBadgeClasses(run.conclusion)}`}
        >
          {run.conclusion || run.status || "—"}
        </span>
      </div>
      <p className="mt-1 truncate text-slate-600" title={run.head_commit_message}>
        {run.head_commit_message || run.display_title || "(no commit message)"}
      </p>
      <p className="mt-1 text-[10px] text-slate-400">
        {run.head_branch} · {run.head_sha} · {formatTime(run.updated_at)}
      </p>
    </button>
  );
}

export default function CiPanel() {
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
        fetchCiRuns(10),
      ]);
      setStatus(statusData);
      setRuns(runsData.items);
      // Use functional update so we read the current selectedRunId at the time
      // the state update is applied, not the stale closure value from when the
      // fetch started (avoids overwriting a user selection made mid-flight).
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
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  const isConfigured = Boolean(status?.configured);

  const reports = useMemo(() => details?.reports || {}, [details]);

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
        comment: `Approved from dashboard (${new Date().toISOString()})`,
      });
      setApproveResult({ ok: true, message: `${state} sent for run ${selectedRunId}.`, data: res });
      // refresh after a short delay
      setTimeout(() => {
        refreshRuns();
        if (selectedRunId) {
          fetchCiRunDetails(selectedRunId).then(setDetails).catch(() => {});
          fetchCiPendingDeployments(selectedRunId)
            .then((d) => setPending(d?.items || []))
            .catch(() => {});
        }
      }, 1500);
    } catch (exc) {
      setApproveResult({ ok: false, message: String(exc?.message || exc) });
    } finally {
      setApproving(false);
    }
  };

  return (
    <section
      data-testid="ci-panel"
      className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            CI / CD Pipeline
          </p>
          <h2 className="text-lg font-semibold text-slate-800">
            GitHub Actions runs · Agent 4 → Agent 5
          </h2>
          {status?.repo ? (
            <p className="text-xs text-slate-500">
              Repo: <code className="rounded bg-slate-100 px-1">{status.repo}</code>
              {status.branch ? (
                <>
                  {" · branch "}
                  <code className="rounded bg-slate-100 px-1">{status.branch}</code>
                </>
              ) : null}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={refreshRuns}
          disabled={loadingRuns}
          className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {loadingRuns ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      {!isConfigured ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <p className="font-semibold">CI bridge is not configured.</p>
          <p className="mt-1">
            Set <code>CI_BRIDGE_REPO</code> and <code>CI_BRIDGE_TOKEN</code> in
            the backend environment to surface real GitHub Actions runs here.
          </p>
        </div>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
          {error}
        </p>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
        {/* Run list */}
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Recent runs
          </p>
          {loadingRuns ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : runs.length === 0 ? (
            <p className="text-xs text-slate-500">
              {isConfigured ? "No runs yet." : "Configure the CI bridge to load runs."}
            </p>
          ) : (
            <div className="space-y-2">
              {runs.map((run) => (
                <RunRow
                  key={run.id}
                  run={run}
                  isSelected={run.id === selectedRunId}
                  onSelect={setSelectedRunId}
                />
              ))}
            </div>
          )}
        </div>

        {/* Details */}
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Run details
          </p>
          {detailsLoading ? (
            <p className="mt-2 text-xs text-slate-500">Loading reports…</p>
          ) : !selectedRunId ? (
            <p className="mt-2 text-xs text-slate-500">Select a run to inspect reports.</p>
          ) : details?.error ? (
            <p className="mt-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              {details.error}
            </p>
          ) : (
            <div className="mt-2 space-y-3">
              {details?.run ? (
                <div className="rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
                  <p>
                    <strong>Status:</strong> {details.run.status || "—"} ·{" "}
                    <strong>Conclusion:</strong> {details.run.conclusion || "—"} ·{" "}
                    <strong>Event:</strong> {details.run.event || "—"}
                  </p>
                  {details.run.html_url ? (
                    <p className="mt-1">
                      <a
                        href={details.run.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sky-700 hover:underline"
                      >
                        Open on GitHub →
                      </a>
                    </p>
                  ) : null}
                </div>
              ) : null}

              <ReportSummary phase="pre-test" payload={reports["pre-test"]} />
              <ReportSummary phase="stage-results" payload={reports["stage-results"]} />
              <ReportSummary phase="pre-prod" payload={reports["pre-prod"]} />

              {/* Approval controls */}
              {pending.length > 0 ? (
                <div className="rounded-xl border border-sky-200 bg-sky-50 p-3">
                  <p className="text-xs font-semibold text-sky-900">
                    Pending human approval
                    {approvableEnvironments.length > 0
                      ? ` · ${approvableEnvironments.map((e) => e.name).join(", ")}`
                      : ""}
                  </p>
                  <p className="mt-1 text-xs text-sky-800">
                    Agent 4 has produced its recommendation. Review the report
                    above, then approve to start the test phase.
                  </p>
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      onClick={() => handleApprove("approved")}
                      disabled={approving || approvableEnvironments.length === 0}
                      className="rounded-full bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                    >
                      {approving ? "Sending…" : "Approve → Start tests"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleApprove("rejected")}
                      disabled={approving || approvableEnvironments.length === 0}
                      className="rounded-full border border-rose-300 bg-white px-3 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                  {approveResult ? (
                    <p
                      className={`mt-2 text-xs ${approveResult.ok ? "text-emerald-700" : "text-rose-700"}`}
                    >
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
