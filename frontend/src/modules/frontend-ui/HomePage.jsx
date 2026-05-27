import { useEffect, useState } from "react";
import {
  fetchHealthSnapshot,
  fetchIssues,
  fetchPendingDeployments,
  fetchPulls,
} from "./dashboardApi.js";

function Widget({ title, body, footer, action }) {
  return (
    <article className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-theme duration-200 dark:border-slate-700 dark:bg-slate-900">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {title}
        </h3>
        <div className="mt-2 text-sm text-slate-700 dark:text-slate-200">{body}</div>
      </div>
      <footer className="mt-4 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
        <span>{footer}</span>
        {action ? (
          <button
            type="button"
            onClick={action.onClick}
            className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800 hover:bg-emerald-100 dark:border-emerald-700/50 dark:bg-emerald-950/40 dark:text-emerald-300 dark:hover:bg-emerald-950/70"
          >
            {action.label}
          </button>
        ) : null}
      </footer>
    </article>
  );
}

export default function HomePage({ subjectRepo, onNavigate }) {
  const [pullsCount, setPullsCount] = useState(null);
  const [deploymentsCount, setDeploymentsCount] = useState(null);
  const [approvalsError, setApprovalsError] = useState(null);
  const [issuesCount, setIssuesCount] = useState(null);
  const [issuesError, setIssuesError] = useState(null);
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [pullsResp, deploymentsResp] = await Promise.all([
          fetchPulls(subjectRepo, "open"),
          fetchPendingDeployments(subjectRepo),
        ]);
        if (!alive) return;
        setPullsCount(pullsResp.items.length);
        setDeploymentsCount(deploymentsResp.items.length);
      } catch (exc) {
        if (alive) setApprovalsError(exc?.message || String(exc));
      }
    })();
    (async () => {
      try {
        const data = await fetchIssues(subjectRepo, { state: "open" });
        if (alive) setIssuesCount(data.items.length);
      } catch (exc) {
        if (alive) setIssuesError(exc?.message || String(exc));
      }
    })();
    (async () => {
      try {
        const data = await fetchHealthSnapshot();
        if (alive) setHealth(data);
      } catch (exc) {
        if (alive) setHealthError(exc?.message || String(exc));
      }
    })();
    return () => {
      alive = false;
    };
  }, [subjectRepo]);

  const approvalsTotal =
    (pullsCount === null ? 0 : pullsCount) +
    (deploymentsCount === null ? 0 : deploymentsCount);

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-6">
      <header>
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
          Welcome
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Subject project: <span className="font-medium text-slate-700 dark:text-slate-300">{subjectRepo}</span>
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Widget
          title="Approvals"
          body={
            approvalsError ? (
              <span className="text-rose-600 dark:text-rose-300">{approvalsError}</span>
            ) : pullsCount === null || deploymentsCount === null ? (
              <span className="text-slate-500 dark:text-slate-400">Loading…</span>
            ) : approvalsTotal === 0 ? (
              <span>Nothing waiting for you right now.</span>
            ) : (
              <span>
                <span className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
                  {approvalsTotal}
                </span>{" "}
                awaiting review
                {pullsCount > 0 || deploymentsCount > 0 ? (
                  <span className="ml-1 text-xs text-slate-500 dark:text-slate-400">
                    ({pullsCount} PR{pullsCount === 1 ? "" : "s"} ·{" "}
                    {deploymentsCount} deployment
                    {deploymentsCount === 1 ? "" : "s"})
                  </span>
                ) : null}
              </span>
            )
          }
          footer="PRs + GitHub Actions environment gates"
          action={{ label: "Review now →", onClick: () => onNavigate("pulls") }}
        />

        <Widget
          title="Cluster Health"
          body={
            healthError ? (
              <span className="text-rose-600 dark:text-rose-300">{healthError}</span>
            ) : health === null ? (
              <span className="text-slate-500 dark:text-slate-400">Loading…</span>
            ) : health.apps_total === 0 ? (
              <span className="text-slate-500 dark:text-slate-400">
                No app events received yet — configure ArgoCD notifications.
              </span>
            ) : health.apps_degraded > 0 || health.apps_out_of_sync > 0 ? (
              <span>
                <span className="text-2xl font-semibold text-rose-700 dark:text-rose-300">
                  {health.apps_degraded + health.apps_out_of_sync}
                </span>{" "}
                app{health.apps_degraded + health.apps_out_of_sync === 1 ? "" : "s"} need attention
                <span className="ml-1 text-xs text-slate-500 dark:text-slate-400">
                  ({health.apps_healthy}/{health.apps_total} healthy)
                </span>
              </span>
            ) : (
              <span>
                <span className="text-2xl font-semibold text-emerald-700 dark:text-emerald-300">
                  {health.apps_healthy}/{health.apps_total}
                </span>{" "}
                apps healthy.
              </span>
            )
          }
          footer="ArgoCD notifications → Verdict (SSE)"
          action={{ label: "See all →", onClick: () => onNavigate("health") }}
        />

        <Widget
          title="Releases"
          body={<span className="text-slate-500 dark:text-slate-400">Coming soon (Phase D).</span>}
          footer="VDDs auto-drafted"
        />

        <Widget
          title="Tickets"
          body={
            issuesError ? (
              <span className="text-rose-600 dark:text-rose-300">{issuesError}</span>
            ) : issuesCount === null ? (
              <span className="text-slate-500 dark:text-slate-400">Loading…</span>
            ) : issuesCount === 0 ? (
              <span>No open tickets right now.</span>
            ) : (
              <span>
                <span className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
                  {issuesCount}
                </span>{" "}
                open ticket{issuesCount === 1 ? "" : "s"}.
              </span>
            )
          }
          footer="GitHub Issues mirror"
          action={{ label: "See all →", onClick: () => onNavigate("tickets") }}
        />
      </div>
    </section>
  );
}
