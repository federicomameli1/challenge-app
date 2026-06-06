/**
 * Agent 7 Live Monitoring — Dashboard page
 *
 * Self-contained React component for the Agent 7 production deployment
 * live monitoring view. Reached from the Sidebar's "Live Monitoring" item.
 *
 * Backend: Verdict FastAPI at /agent7/* (SSE stream).
 */

import { useState } from "react";
import { useAgent7WebSocket } from "./hooks/useAgent7WebSocket.js";

const STATUS_STYLES = {
  healthy: {
    text: "text-emerald-700",
    bg: "bg-emerald-100",
    dot: "bg-emerald-500",
  },
  degraded: {
    text: "text-amber-700",
    bg: "bg-amber-100",
    dot: "bg-amber-500",
  },
  unhealthy: {
    text: "text-red-700",
    bg: "bg-red-100",
    dot: "bg-red-500",
  },
  unknown: {
    text: "text-slate-600",
    bg: "bg-slate-100",
    dot: "bg-slate-400",
  },
};

function statusLabel(s) {
  if (!s) return "Unknown";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function StatusPill({ status }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.unknown;
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${style.text} ${style.bg}`}
    >
      {statusLabel(status)}
    </span>
  );
}

function Metric({ label, value, accent }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 transition-theme duration-200 dark:border-slate-700 dark:bg-slate-900">
      <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p
        className={`mt-1 text-2xl font-semibold ${accent ?? "text-slate-900 dark:text-slate-100"}`}
      >
        {value}
      </p>
    </div>
  );
}

function PrimaryButton({ children, onClick, disabled, color = "emerald" }) {
  const colorClass =
    color === "emerald"
      ? "bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-300"
      : color === "slate"
      ? "bg-slate-600 hover:bg-slate-700 disabled:bg-slate-300"
      : "bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-4 py-2 text-sm font-semibold text-white transition ${colorClass} disabled:cursor-not-allowed`}
    >
      {children}
    </button>
  );
}

function SmallButton({ children, onClick, disabled, color = "red" }) {
  const colorClass =
    color === "red"
      ? "bg-red-600 hover:bg-red-700 disabled:bg-red-300"
      : "bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-300";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-2.5 py-1 text-xs font-semibold text-white transition ${colorClass} disabled:cursor-not-allowed`}
    >
      {children}
    </button>
  );
}

export default function LiveMonitoringPage() {
  const [scenarioId, setScenarioId] = useState("P7-001");
  const [draftScenarioId, setDraftScenarioId] = useState("P7-001");
  const [scenarios] = useState([]);
  const [busy, setBusy] = useState(null);

  const { snapshot, history, connected, error, reconnect } = useAgent7WebSocket(scenarioId);

  const overall = snapshot?.overall_status ?? "unknown";
  const overallStyle = STATUS_STYLES[overall] ?? STATUS_STYLES.unknown;

  async function startDeployment() {
    setBusy("start");
    try {
      await fetch("/api/agent7/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_id: scenarioId,
          interval_seconds: 1.5,
        }),
      });
    } finally {
      setBusy(null);
    }
  }

  async function inject(probeName) {
    setBusy(probeName);
    try {
      await fetch("/api/agent7/demo/inject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_id: scenarioId,
          probe_name: probeName,
          status: "unhealthy",
        }),
      });
    } finally {
      setBusy(null);
    }
  }

  async function resolve(probeName) {
    setBusy(probeName);
    try {
      await fetch("/api/agent7/demo/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_id: scenarioId,
          probe_name: probeName,
        }),
      });
    } finally {
      setBusy(null);
    }
  }

  async function resolveAll() {
    setBusy("all");
    try {
      await fetch("/api/agent7/demo/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_id: scenarioId }),
      });
    } finally {
      setBusy(null);
    }
  }

  function applyScenario() {
    if (draftScenarioId.trim()) {
      setScenarioId(draftScenarioId.trim());
    }
  }

  return (
    <section className="mx-auto max-w-5xl px-6 py-8">
      {/* Header */}
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="mb-1 text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Live Monitoring
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Real-time production deployment health.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-medium ${
              connected
                ? "text-emerald-700 dark:text-emerald-400"
                : "text-red-700 dark:text-red-400"
            }`}
          >
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                connected ? "bg-emerald-500" : "bg-red-500"
              }`}
            />
            {connected ? "Connected" : "Disconnected"}
          </span>
          {!connected && (
            <PrimaryButton color="slate" onClick={reconnect}>
              Reconnect
            </PrimaryButton>
          )}
        </div>
      </header>

      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Scenario picker */}
      <div className="mb-6 flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 transition-theme duration-200 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex-1 min-w-[200px]">
          <label
            htmlFor="scenario-input"
            className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
          >
            Scenario ID
          </label>
          <input
            id="scenario-input"
            type="text"
            value={draftScenarioId}
            onChange={(e) => setDraftScenarioId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") applyScenario();
            }}
            list="agent7-scenarios"
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
          <datalist id="agent7-scenarios">
            {scenarios.map((s) => (
              <option key={s.scenario_id} value={s.scenario_id}>
                {s.release_id}
              </option>
            ))}
          </datalist>
        </div>
        <PrimaryButton color="slate" onClick={applyScenario}>
          Apply
        </PrimaryButton>
      </div>

      {/* Metrics */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric
          label="Overall"
          value={statusLabel(overall)}
          accent={overallStyle.text}
        />
        <Metric
          label="Error Rate"
          value={`${snapshot?.error_rate_percent ?? 0}%`}
          accent={
            (snapshot?.error_rate_percent ?? 0) > 0
              ? "text-red-600 dark:text-red-400"
              : undefined
          }
        />
        <Metric
          label="P99 Latency"
          value={
            snapshot?.p99_latency_ms != null
              ? `${snapshot.p99_latency_ms} ms`
              : "—"
          }
        />
        <Metric
          label="Active Probes"
          value={String(snapshot?.active_instances ?? 0)}
        />
      </div>

      {/* Actions */}
      <div className="mb-6 flex flex-wrap gap-3">
        <PrimaryButton
          color="emerald"
          onClick={startDeployment}
          disabled={busy !== null}
        >
          {busy === "start" ? "Starting..." : "Start Deployment"}
        </PrimaryButton>
        <PrimaryButton
          color="slate"
          onClick={resolveAll}
          disabled={busy !== null}
        >
          {busy === "all" ? "Resolving..." : "Resolve All Probes"}
        </PrimaryButton>
      </div>

      {/* Probe table */}
      <div className="mb-6 rounded-lg border border-slate-200 bg-white p-4 transition-theme duration-200 dark:border-slate-700 dark:bg-slate-900">
        <h3 className="mb-3 text-base font-semibold text-slate-900 dark:text-slate-100">
          Service Probes
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase text-slate-400 dark:border-slate-700">
                <th className="py-2 pr-3">Service</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Latency</th>
                <th className="py-2 pr-3">Error</th>
                <th className="py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(snapshot?.probe_results ?? []).map((p) => (
                <tr
                  key={p.probe_name}
                  className="border-b border-slate-100 last:border-0 dark:border-slate-800"
                >
                  <td className="py-2 pr-3 font-mono text-xs">{p.probe_name}</td>
                  <td className="py-2 pr-3">
                    <StatusPill status={p.status} />
                  </td>
                  <td className="py-2 pr-3 text-slate-600 dark:text-slate-400">
                    {p.response_time_ms != null
                      ? `${p.response_time_ms.toFixed(0)} ms`
                      : "—"}
                  </td>
                  <td className="py-2 pr-3 text-xs text-slate-500 dark:text-slate-400">
                    {p.error_message ?? "—"}
                  </td>
                  <td className="py-2">
                    <div className="flex gap-1.5">
                      <SmallButton
                        color="red"
                        onClick={() => inject(p.probe_name)}
                        disabled={busy !== null}
                      >
                        {busy === p.probe_name ? "..." : "Inject"}
                      </SmallButton>
                      <SmallButton
                        color="emerald"
                        onClick={() => resolve(p.probe_name)}
                        disabled={busy !== null}
                      >
                        Resolve
                      </SmallButton>
                    </div>
                  </td>
                </tr>
              ))}
              {(!snapshot || snapshot.probe_results?.length === 0) && (
                <tr>
                  <td
                    colSpan={5}
                    className="py-6 text-center text-sm text-slate-400"
                  >
                    Waiting for first snapshot...
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent history */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 transition-theme duration-200 dark:border-slate-700 dark:bg-slate-900">
        <h3 className="mb-3 text-base font-semibold text-slate-900 dark:text-slate-100">
          Recent Snapshots ({history.length})
        </h3>
        <div className="max-h-60 overflow-y-auto">
          {history
            .slice()
            .reverse()
            .slice(0, 30)
            .map((s, idx) => {
              const style = STATUS_STYLES[s.overall_status] ?? STATUS_STYLES.unknown;
              return (
                <div
                  key={`${s.timestamp_utc}-${idx}`}
                  className="flex items-center gap-3 border-b border-slate-100 py-1.5 text-xs last:border-0 dark:border-slate-800"
                >
                  <span className={`inline-block h-2 w-2 rounded-full ${style.dot}`} />
                  <code className="text-slate-500 dark:text-slate-400">
                    {s.timestamp_utc}
                  </code>
                  <span className={`font-semibold uppercase ${style.text}`}>
                    {s.overall_status}
                  </span>
                  <span className="text-slate-500 dark:text-slate-400">
                    err={s.error_rate_percent ?? 0}%
                  </span>
                  <span className="text-slate-500 dark:text-slate-400">
                    p99={s.p99_latency_ms ?? 0}ms
                  </span>
                </div>
              );
            })}
          {history.length === 0 && (
            <p className="py-4 text-center text-sm text-slate-400">
              No snapshots yet.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
