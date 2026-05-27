import { useEffect, useState } from "react";
import { fetchIssues, fetchPulls } from "./dashboardApi.js";

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
  const [pullsError, setPullsError] = useState(null);
  const [issuesCount, setIssuesCount] = useState(null);
  const [issuesError, setIssuesError] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await fetchPulls(subjectRepo, "open");
        if (alive) setPullsCount(data.items.length);
      } catch (exc) {
        if (alive) setPullsError(exc?.message || String(exc));
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
    return () => {
      alive = false;
    };
  }, [subjectRepo]);

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
          title="PR Review"
          body={
            pullsError ? (
              <span className="text-rose-600 dark:text-rose-300">{pullsError}</span>
            ) : pullsCount === null ? (
              <span className="text-slate-500 dark:text-slate-400">Loading…</span>
            ) : pullsCount === 0 ? (
              <span>No PRs open right now.</span>
            ) : (
              <span>
                <span className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
                  {pullsCount}
                </span>{" "}
                pull request{pullsCount === 1 ? "" : "s"} to review.
              </span>
            )
          }
          footer="Updated on open"
          action={{ label: "Review now →", onClick: () => onNavigate("pulls") }}
        />

        <Widget
          title="Cluster Health"
          body={<span className="text-slate-500 dark:text-slate-400">Coming soon (Phase E).</span>}
          footer="Polled via ArgoCD"
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
