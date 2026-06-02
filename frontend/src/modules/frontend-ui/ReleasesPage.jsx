import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCommits, fetchReleases, fetchVddContent } from "./dashboardApi.js";
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

function mdToHtml(md) {
  return md
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>(\n|$))+/g, (m) => `<ul>${m}</ul>`)
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/^(?!<[hul])(.+)$/gm, (line) => line ? line : "")
    .replace(/^(<p>)?(.+?)(<\/p>)?$/gms, (_, a, b, c) =>
      a || c ? `<p>${b}</p>` : b
    );
}

function openVddPrintWindow(tag, markdown) {
  const html = `<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"/>
<title>VDD ${tag}</title>
<style>
  body{font-family:Georgia,serif;max-width:820px;margin:40px auto;color:#111;line-height:1.6;font-size:13pt}
  h1{font-size:20pt;border-bottom:2px solid #222;padding-bottom:6px}
  h2{font-size:15pt;margin-top:28px;border-bottom:1px solid #ccc;padding-bottom:4px}
  h3{font-size:13pt;margin-top:18px}
  ul{padding-left:20px}li{margin:3px 0}
  strong{font-weight:700}
  p{margin:8px 0}
  @media print{body{margin:20mm}}
</style>
</head><body>
${mdToHtml(markdown)}
<script>window.onload=()=>{window.print()}<\/script>
</body></html>`;
  const w = window.open("", "_blank");
  if (w) { w.document.write(html); w.document.close(); }
}

function ReleaseCard({ release, subjectRepo }) {
  const [expanded, setExpanded] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const hasVdd = Boolean(release.vdd_url);

  async function handleDownloadPdf() {
    setDownloading(true);
    try {
      const { content } = await fetchVddContent(subjectRepo, release.tag);
      openVddPrintWindow(release.tag, content);
    } finally {
      setDownloading(false);
    }
  }
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-theme duration-200 dark:border-slate-700 dark:bg-slate-900">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold text-slate-900 dark:text-slate-100">
            <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-sm dark:bg-slate-800">
              {release.tag}
            </code>
            {release.name && release.name !== release.tag ? (
              <span className="ml-2 font-normal">{release.name}</span>
            ) : null}
          </h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            by <span className="font-medium text-slate-700 dark:text-slate-300">{release.author || "n/a"}</span>
            {release.published_at ? (
              <>
                {" · "}
                <span title={release.published_at}>{timeAgo(release.published_at)}</span>
              </>
            ) : null}
            {release.prerelease ? " · prerelease" : ""}
          </p>
        </div>
        <StatusPill
          tone={hasVdd ? "info" : "pending"}
          label={hasVdd ? "VDD ready" : "VDD pending"}
          emoji={hasVdd ? "✎" : "…"}
        />
      </header>

      {release.body ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-800 dark:text-emerald-300 dark:hover:text-emerald-200"
          >
            <span aria-hidden>{expanded ? "▾" : "▸"}</span>
            <span>{expanded ? "Hide release notes" : "Show release notes"}</span>
          </button>
          {expanded ? (
            <pre className="mt-3 max-h-[300px] overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs leading-relaxed text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200">
{release.body}
            </pre>
          ) : null}
        </div>
      ) : null}

      <footer className="mt-4 flex flex-wrap items-center gap-2">
        {release.vdd_url ? (
          <>
            <a
              href={release.vdd_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg border border-emerald-600 bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              ↗ Open VDD
            </a>
            <button
              type="button"
              onClick={handleDownloadPdf}
              disabled={downloading}
              className="rounded-lg border border-emerald-600 px-3 py-1.5 text-sm font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-50 dark:text-emerald-300 dark:hover:bg-emerald-950/30"
            >
              {downloading ? "Preparing…" : "⬇ PDF"}
            </button>
          </>
        ) : (
          <span
            className="rounded-lg border border-slate-200 bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
            title="VDD is auto-drafted by the deploy-prod workflow shortly after release"
          >
            VDD pending…
          </span>
        )}
        {release.vdd_docx_url ? (
          <a
            href={release.vdd_docx_url}
            download={`VDD-${release.tag}.docx`}
            className="rounded-lg border border-sky-600 px-3 py-1.5 text-sm font-semibold text-sky-700 hover:bg-sky-50 dark:text-sky-300 dark:hover:bg-sky-950/30"
          >
            ⬇ DOCX
          </a>
        ) : null}
        <a
          href={release.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          ↗ Release on GitHub
        </a>
      </footer>
    </article>
  );
}

export default function ReleasesPage({ subjectRepo }) {
  const [commits, setCommits] = useState([]);
  const [releases, setReleases] = useState([]);
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
      const [commitsResp, releasesResp] = await Promise.all([
        fetchCommits(subjectRepo, { branch: "main", limit: 20 }),
        fetchReleases(subjectRepo, { limit: 10 }),
      ]);
      if (!isMountedRef.current) return;
      setCommits(commitsResp.items);
      setReleases(releasesResp.items);
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

      {releases.length > 0 ? (
        <div className="mt-2">
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Released versions ({releases.length})
          </h3>
          <div className="flex flex-col gap-4">
            {releases.map((release) => (
              <ReleaseCard key={release.tag} release={release} subjectRepo={subjectRepo} />
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-4">
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Recent builds on main ({commits.length})
        </h3>
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
      </div>
    </section>
  );
}
