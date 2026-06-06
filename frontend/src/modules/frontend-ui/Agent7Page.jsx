import { useCallback, useEffect, useRef, useState } from "react";
import {
  agent7InjectProblem,
  agent7OpenStream,
  agent7Reset,
  agent7ResolveProblem,
  agent7StartDeployment,
} from "./dashboardApi.js";

const DEFAULT_SCENARIO = "P7-001";
const DEFAULT_PROBES = ["sensor-collector", "anomaly-engine", "alert-dispatcher", "redis-broker"];

function statusColor(status) {
  if (status === "healthy") return "text-emerald-700 dark:text-emerald-300";
  if (status === "degraded") return "text-amber-600 dark:text-amber-300";
  if (status === "unhealthy") return "text-rose-600 dark:text-rose-300";
  return "text-slate-500 dark:text-slate-400";
}

function statusBg(status) {
  if (status === "healthy") return "bg-emerald-500";
  if (status === "degraded") return "bg-amber-500";
  if (status === "unhealthy") return "bg-rose-500";
  return "bg-slate-400";
}

function ProbeRow({ probe, onInject, onResolve, injected }) {
  return (
    <tr className="border-t border-slate-100 dark:border-slate-800">
      <td className="py-2 pr-4 text-sm font-mono text-slate-700 dark:text-slate-200">{probe.probe_name}</td>
      <td className="py-2 pr-4">
        <span className={`text-sm font-semibold ${statusColor(probe.status)}`}>
          <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${statusBg(probe.status)}`} />
          {probe.status}
        </span>
      </td>
      <td className="py-2 pr-4 text-sm text-slate-500 dark:text-slate-400">
        {probe.response_time_ms ? `${Math.round(probe.response_time_ms)}ms` : "—"}
      </td>
      <td className="py-2 pr-4 text-xs text-rose-500 dark:text-rose-400">
        {probe.error_message || ""}
      </td>
      <td className="py-2 text-right">
        {injected ? (
          <button
            type="button"
            onClick={() => onResolve(probe.probe_name)}
            className="rounded border border-emerald-500 px-2 py-0.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-emerald-950/30"
          >
            Resolve
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onInject(probe.probe_name)}
            className="rounded border border-rose-400 px-2 py-0.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-950/30"
          >
            Inject failure
          </button>
        )}
      </td>
    </tr>
  );
}

export default function Agent7Page() {
  const [scenarioId] = useState(DEFAULT_SCENARIO);
  const [running, setRunning] = useState(false);
  const [connected, setConnected] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [log, setLog] = useState([]);
  const [injected, setInjected] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const sourceRef = useRef(null);

  const addLog = useCallback((msg) => {
    const ts = new Date().toLocaleTimeString();
    setLog((prev) => [`${ts}  ${msg}`, ...prev].slice(0, 50));
  }, []);

  const handleStart = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await agent7StartDeployment({
        scenario_id: scenarioId,
        release_id: "REL-demo",
        probe_names: DEFAULT_PROBES,
        stabilization_seconds: 30,
        interval_seconds: 3,
      });
      setRunning(true);
      setLog([]);
      setInjected({});
      setSnapshot(null);
      addLog("Deployment started — stabilization window open");
    } catch (exc) {
      setError(exc?.message || String(exc));
    } finally {
      setBusy(false);
    }
  }, [scenarioId, addLog]);

  const handleReset = useCallback(async () => {
    try {
      if (sourceRef.current) { sourceRef.current.close(); sourceRef.current = null; }
      await agent7Reset(scenarioId);
    } catch { /* ignore */ }
    setRunning(false);
    setConnected(false);
    setSnapshot(null);
    setInjected({});
    setLog([]);
  }, [scenarioId]);

  const handleInject = useCallback(async (probeName) => {
    try {
      await agent7InjectProblem({
        scenario_id: scenarioId,
        probe_name: probeName,
        status: "unhealthy",
        error_message: "simulated production outage",
      });
      setInjected((prev) => ({ ...prev, [probeName]: true }));
      addLog(`⚠ Injected failure → ${probeName}`);
    } catch (exc) {
      setError(exc?.message || String(exc));
    }
  }, [scenarioId, addLog]);

  const handleResolve = useCallback(async (probeName) => {
    try {
      await agent7ResolveProblem({ scenario_id: scenarioId, probe_name: probeName });
      setInjected((prev) => { const n = { ...prev }; delete n[probeName]; return n; });
      addLog(`✓ Resolved → ${probeName}`);
    } catch (exc) {
      setError(exc?.message || String(exc));
    }
  }, [scenarioId, addLog]);

  // SSE connection
  useEffect(() => {
    if (!running) return;
    const source = agent7OpenStream(scenarioId, {
      onSnapshot: (data) => {
        setSnapshot(data);
        setConnected(true);
        const overall = data.overall_status || "unknown";
        const count = data.snapshot_count || "?";
        addLog(`Snapshot #${count} — overall: ${overall} | stability: ${data.stability_achieved ? "✓" : "…"}`);
      },
      onError: () => setConnected(false),
    });
    sourceRef.current = source;
    return () => { source.close(); sourceRef.current = null; };
  }, [running, scenarioId, addLog]);

  const overallStatus = snapshot?.overall_status || "unknown";
  const probes = snapshot?.probe_results || DEFAULT_PROBES.map((n) => ({ probe_name: n, status: "unknown" }));

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-6 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Production Deployment Monitor
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Agent 7 — Phase 7 gate · scenario <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">{scenarioId}</code>
          </p>
        </div>
        <div className="flex gap-2">
          {!running ? (
            <button
              type="button"
              onClick={handleStart}
              disabled={busy}
              className="rounded-lg border border-emerald-600 bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {busy ? "Starting…" : "▶ Run Production Deployment"}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleReset}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
            >
              ■ Stop & Reset
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-700/60 dark:bg-rose-950/40 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Status card */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Overall Status</p>
          <p className={`mt-1 text-2xl font-bold ${statusColor(overallStatus)}`}>
            <span className={`mr-2 inline-block h-3 w-3 rounded-full ${statusBg(overallStatus)}`} />
            {overallStatus.toUpperCase()}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Deployment Status</p>
          <p className="mt-1 text-lg font-semibold text-slate-800 dark:text-slate-100">
            {snapshot?.deployment_status ?? (running ? "stabilizing" : "—")}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Stability</p>
          <p className={`mt-1 text-lg font-semibold ${snapshot?.stability_achieved ? "text-emerald-700 dark:text-emerald-300" : "text-amber-600 dark:text-amber-300"}`}>
            {snapshot?.stability_achieved ? "✓ Achieved" : running ? "…Monitoring" : "—"}
          </p>
          <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
            {connected ? "● Live (SSE)" : running ? "Connecting…" : ""}
          </p>
        </div>
      </div>

      {/* Probe table */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">Service Health Probes</h3>
        <table className="w-full">
          <thead>
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
              <th className="pb-2 pr-4">Service</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2 pr-4">Latency</th>
              <th className="pb-2 pr-4">Error</th>
              <th className="pb-2 text-right">Demo</th>
            </tr>
          </thead>
          <tbody>
            {probes.map((p) => (
              <ProbeRow
                key={p.probe_name}
                probe={p}
                injected={!!injected[p.probe_name]}
                onInject={handleInject}
                onResolve={handleResolve}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Event log */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">Event Log</h3>
        {log.length === 0 ? (
          <p className="text-xs text-slate-400 dark:text-slate-500">No events yet. Start a deployment to begin monitoring.</p>
        ) : (
          <ul className="space-y-0.5">
            {log.map((entry, i) => (
              <li key={i} className="font-mono text-xs text-slate-600 dark:text-slate-300">{entry}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
