import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCommits } from "./dashboardApi.js";
import StatusPill from "./StatusPill.jsx";

const REFRESH_INTERVAL_MS = 60_000;

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

function verdictTone(verdict) {
  const upper = String(verdict || "").toUpperCase();
  if (upper === "GO") return "go";
  if (upper === "HOLD") return "hold";
  return "pending";
}

function CommitCard({ commit }) {
  const [expanded, setExpanded] = useState(false);
  const evidence = commit.test_evidence;
  const verdict = evidence?.verdict || null;
  const summary =
    evidence?.summary ||
    (evidence ? "" : "No test evidence available for this commit yet.");

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-theme duration-200 dark:border-slate-700 dark:bg-slate-900">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold text-slate-900 dark:text-slate-100">
            <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm dark:bg-slate-800">
              {commit.short_sha}
            </code>
            <span className="ml-2 font-normal">
              {commit.message || "(no message)"}
            </span>
          </h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            by{" "}
            <span className="font-medium text-slate-700 dark:text-slate-300">
              {commit.author || "unknown"}
            </span>
            {" · "}
            <span title={commit.committed_at}>{timeAgo(commit.committed_at)}</span>
          </p>
        </div>
        <StatusPill tone={verdictTone(verdict)} label={verdict || "PENDING"} />
      </header>

      <p className="mt-3 text-sm leading-relaxed text-slate-700 dark:text-slate-200">
        {summary}
      </p>

      {evidence?.body_markdown ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-800 dark:text-emerald-300 dark:hover:text-emerald-200"
          >
            <span aria-hidden>{expanded ? "▾" : "▸"}</span>
            <span>{expanded ? "Hide full report" : "View full report"}</span>
          </button>
          {expanded ? (
            <pre className="mt-3 max-h-[440px] overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs leading-relaxed text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200">
{evidence.body_markdown}
            </pre>
          ) : null}
        </div>
      ) : null}

      <footer className="mt-4 flex flex-wrap items-center gap-2">
        <a
          href={commit.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          ↗ View commit on GitHub
        </a>
        {evidence?.html_url ? (
          <a
            href={evidence.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            ↗ Evidence comment
          </a>
        ) : null}
      </footer>
    </article>
  );
}

export default function ReleasesPage({ subjectRepo }) {
  const [commits, setCommits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    try {
      const data = await fetchCommits(subjectRepo, { branch: "main", limit: 20 });
      if (!isMountedRef.current) return;
      setCommits(data.items);
      setError(null);
      setRefreshedAt(new Date());
    } catch (exc) {
      if (!isMountedRef.current) return;
      setError(exc?.message || String(exc));
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [subjectRepo]);

  useEffect(() => {
    setLoading(true);
    load();
    const id = setInterval(load, REFRESH_INTERVAL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [load]);

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-6 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Releases
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {subjectRepo} · recent builds on <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] dark:bg-slate-800">main</code>
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          {refreshedAt ? (
            <span title={refreshedAt.toISOString()}>
              Updated {timeAgo(refreshedAt.toISOString())}
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              load();
            }}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Refresh
          </button>
        </div>
      </header>

      {loading && commits.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading recent commits…</p>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-700/60 dark:bg-rose-950/40 dark:text-rose-300"
        >
          Failed to load commits: {error}
        </div>
      ) : null}

      {!loading && !error && commits.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
          No commits found on main.
        </p>
      ) : null}

      <div className="flex flex-col gap-4">
        {commits.map((commit) => (
          <CommitCard key={commit.sha} commit={commit} />
        ))}
      </div>

      <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
        Tagged releases with VDD will appear here once Phase D is in place.
      </p>
    </section>
  );
}
