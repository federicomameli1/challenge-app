import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchHealthSnapshot, openHealthStream } from "./dashboardApi.js";
import StatusPill from "./StatusPill.jsx";

function timeAgo(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function rollupTone(snap) {
  if (snap.health_status === "Healthy" && snap.sync_status === "Synced") return "healthy";
  if (snap.health_status === "Degraded" || snap.health_status === "Missing") return "degraded";
  if (snap.sync_status === "OutOfSync") return "outofsync";
  if (snap.health_status === "Progressing") return "pending";
  return "info";
}

function rollupLabel(snap) {
  if (snap.health_status === "Healthy" && snap.sync_status === "Synced") return "Healthy";
  if (snap.health_status === "Degraded") return "Degraded";
  if (snap.health_status === "Missing") return "Missing";
  if (snap.sync_status === "OutOfSync") return "OutOfSync";
  if (snap.health_status === "Progressing") return "Progressing";
  return snap.health_status || "Unknown";
}

function AppCard({ snap }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition-theme duration-200 dark:border-slate-700 dark:bg-slate-900">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
            {snap.app}
          </h4>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            {snap.namespace ? (
              <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] dark:bg-slate-800">
                {snap.namespace}
              </code>
            ) : null}
            {snap.revision ? (
              <>
                {" · "}
                <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] dark:bg-slate-800">
                  {snap.revision.slice(0, 8)}
                </code>
              </>
            ) : null}
          </p>
        </div>
        <StatusPill tone={rollupTone(snap)} label={rollupLabel(snap)} />
      </header>

      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500 dark:text-slate-400">
        <span>
          health:{" "}
          <span className="font-semibold text-slate-700 dark:text-slate-200">
            {snap.health_status || "Unknown"}
          </span>
        </span>
        <span>
          sync:{" "}
          <span className="font-semibold text-slate-700 dark:text-slate-200">
            {snap.sync_status || "Unknown"}
          </span>
        </span>
        {snap.operation_phase ? (
          <span>
            op:{" "}
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              {snap.operation_phase}
            </span>
          </span>
        ) : null}
        <span title={snap.received_at}>updated {timeAgo(snap.received_at)}</span>
      </div>

      {snap.url ? (
        <a
          href={snap.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-block text-xs font-semibold text-emerald-700 hover:text-emerald-800 dark:text-emerald-300 dark:hover:text-emerald-200"
        >
          ↗ Open in Argo CD
        </a>
      ) : null}
    </article>
  );
}

export default function HealthPage() {
  const [snapshot, setSnapshot] = useState({
    apps: [],
    apps_total: 0,
    apps_healthy: 0,
    apps_degraded: 0,
    apps_out_of_sync: 0,
    received_at: null,
  });
  const [error, setError] = useState(null);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef(null);

  const applyUpdate = useCallback((snap) => {
    setSnapshot((prev) => {
      const merged = new Map(prev.apps.map((a) => [a.app, a]));
      merged.set(snap.app, snap);
      const apps = Array.from(merged.values()).sort((a, b) => {
        if (a.cluster !== b.cluster) return a.cluster.localeCompare(b.cluster);
        return a.app.localeCompare(b.app);
      });
      const healthy = apps.filter(
        (a) => a.health_status === "Healthy" && a.sync_status === "Synced"
      ).length;
      const degraded = apps.filter(
        (a) => a.health_status === "Degraded" || a.health_status === "Missing"
      ).length;
      const oos = apps.filter(
        (a) => a.sync_status === "OutOfSync" && a.health_status !== "Degraded"
      ).length;
      return {
        apps,
        apps_total: apps.length,
        apps_healthy: healthy,
        apps_degraded: degraded,
        apps_out_of_sync: oos,
        received_at: new Date().toISOString(),
      };
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchHealthSnapshot();
        if (cancelled) return;
        setSnapshot({
          apps: Array.isArray(data?.apps) ? data.apps : [],
          apps_total: data?.apps_total || 0,
          apps_healthy: data?.apps_healthy || 0,
          apps_degraded: data?.apps_degraded || 0,
          apps_out_of_sync: data?.apps_out_of_sync || 0,
          received_at: data?.received_at,
        });
      } catch (exc) {
        if (!cancelled) setError(exc?.message || String(exc));
      }
    })();

    const source = openHealthStream({
      onSnapshot: (data) => {
        if (cancelled) return;
        setSnapshot({
          apps: Array.isArray(data?.apps) ? data.apps : [],
          apps_total: data?.apps_total || 0,
          apps_healthy: data?.apps_healthy || 0,
          apps_degraded: data?.apps_degraded || 0,
          apps_out_of_sync: data?.apps_out_of_sync || 0,
          received_at: data?.received_at,
        });
        setConnected(true);
      },
      onUpdate: (snap) => {
        if (!cancelled) applyUpdate(snap);
      },
      onError: () => {
        if (!cancelled) setConnected(false);
      },
    });
    sourceRef.current = source;
    setConnected(true);

    return () => {
      cancelled = true;
      try {
        source.close();
      } catch {
        // ignore
      }
    };
  }, [applyUpdate]);

  const groupedByCluster = useMemo(() => {
    const groups = new Map();
    for (const app of snapshot.apps) {
      const key = app.cluster || "(unknown cluster)";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(app);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [snapshot.apps]);

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-6 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Cluster Health
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Argo CD applications across mgmt / test / prod ·{" "}
            <span className="text-emerald-700 dark:text-emerald-300">
              {snapshot.apps_healthy} healthy
            </span>
            {" · "}
            <span className="text-rose-700 dark:text-rose-300">
              {snapshot.apps_degraded} degraded
            </span>
            {" · "}
            <span className="text-amber-700 dark:text-amber-300">
              {snapshot.apps_out_of_sync} out of sync
            </span>
          </p>
        </div>
        <div className="text-xs text-slate-500 dark:text-slate-400">
          <span
            className={`mr-2 inline-block h-2 w-2 rounded-full ${
              connected ? "bg-emerald-500" : "bg-slate-400"
            }`}
            aria-hidden
          />
          {connected ? "Live (SSE connected)" : "Offline — using last snapshot"}
        </div>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-700/60 dark:bg-rose-950/40 dark:text-rose-300"
        >
          Failed to load snapshot: {error}
        </div>
      ) : null}

      {snapshot.apps.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
          <p className="font-medium text-slate-700 dark:text-slate-200">No applications reported yet.</p>
          <p className="mt-2">
            When deployed on the management cluster, Verdict polls Argo CD automatically every 30 seconds.
          </p>
          <p className="mt-1">
            Running locally? Seed the state with{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 dark:bg-slate-800">
              python3 scripts/seed_health_local.py
            </code>
          </p>
        </div>
      ) : (
        groupedByCluster.map(([cluster, apps]) => (
          <div key={cluster}>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {cluster} · {apps.length} app{apps.length === 1 ? "" : "s"}
            </h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {apps.map((app) => (
                <AppCard key={`${cluster}-${app.app}`} snap={app} />
              ))}
            </div>
          </div>
        ))
      )}
    </section>
  );
}
