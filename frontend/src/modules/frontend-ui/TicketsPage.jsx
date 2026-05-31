import { useCallback, useEffect, useRef, useState } from "react";
import { createIssue, fetchIssues, updateIssue } from "./dashboardApi.js";

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

function colorIsLight(hex) {
  if (!hex || hex.length < 6) return false;
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  // YIQ perceptual luminance
  return (r * 299 + g * 587 + b * 114) / 1000 > 145;
}

function LabelChip({ label }) {
  const bg = label.color ? `#${label.color}` : "#94a3b8";
  const fg = colorIsLight(label.color || "") ? "#0f172a" : "#ffffff";
  return (
    <span
      className="inline-flex items-center rounded-full border border-transparent px-2 py-0.5 text-[11px] font-semibold"
      style={{ backgroundColor: bg, color: fg }}
      title={label.description || label.name}
    >
      {label.name}
    </span>
  );
}

function CreateIssueDialog({ open, busy, onCancel, onSubmit }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [labelsRaw, setLabelsRaw] = useState("");

  useEffect(() => {
    if (open) {
      setTitle("");
      setBody("");
      setLabelsRaw("");
    }
  }, [open]);

  if (!open) return null;
  const canSubmit = title.trim().length >= 3;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm px-4"
    >
      <div className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          New ticket
        </h2>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Opens an Issue on the subject repository via the GitHub API.
        </p>

        <label className="mt-4 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Title
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Short, specific summary…"
          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
        />

        <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Description (optional, markdown)
        </label>
        <textarea
          rows={6}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="What is the problem? Steps to reproduce, expected vs actual, refs to REQ-WMS-XXX…"
          className="mt-1 w-full resize-vertical rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
        />

        <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Labels (optional, comma-separated)
        </label>
        <input
          type="text"
          value={labelsRaw}
          onChange={(e) => setLabelsRaw(e.target.value)}
          placeholder="bug, p1, regression"
          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
        />

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() =>
              onSubmit({
                title: title.trim(),
                body: body.trim() || null,
                labels: labelsRaw
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            disabled={!canSubmit || busy}
            className="rounded-lg border border-emerald-600 bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy ? "Creating…" : "Create ticket"}
          </button>
        </div>
      </div>
    </div>
  );
}

function IssueCard({ issue, onClose, onReopen }) {
  const [expanded, setExpanded] = useState(false);
  const isClosed = issue.state === "closed";
  return (
    <article className={`rounded-2xl border p-5 shadow-sm transition-theme duration-200 ${isClosed ? "border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/60" : "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"}`}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold text-slate-900 dark:text-slate-100">
            <span className="text-slate-500 dark:text-slate-400">
              #{issue.number} ·{" "}
            </span>
            {issue.title || "(no title)"}
          </h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            by{" "}
            <span className="font-medium text-slate-700 dark:text-slate-300">
              {issue.author || "unknown"}
            </span>
            {" · "}
            <span title={issue.updated_at}>{timeAgo(issue.updated_at)}</span>
            {issue.comments > 0 ? ` · ${issue.comments} comments` : null}
            {issue.assignees && issue.assignees.length > 0
              ? ` · assigned to ${issue.assignees.join(", ")}`
              : null}
          </p>
          {issue.labels && issue.labels.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {issue.labels.map((lbl) => (
                <LabelChip key={lbl.name} label={lbl} />
              ))}
            </div>
          ) : null}
        </div>
      </header>

      {issue.body ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-800 dark:text-emerald-300 dark:hover:text-emerald-200"
          >
            <span aria-hidden>{expanded ? "▾" : "▸"}</span>
            <span>{expanded ? "Hide description" : "Show description"}</span>
          </button>
          {expanded ? (
            <pre className="mt-3 max-h-[280px] overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs leading-relaxed text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200">
{issue.body}
            </pre>
          ) : null}
        </div>
      ) : null}

      <footer className="mt-4 flex flex-wrap items-center gap-2">
        {!isClosed ? (
          <button
            type="button"
            onClick={() => onClose(issue)}
            className="rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-sm font-semibold text-rose-700 hover:bg-rose-50 dark:border-rose-700/60 dark:bg-slate-900 dark:text-rose-300 dark:hover:bg-rose-950/30"
          >
            Close ticket
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onReopen(issue)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Reopen
          </button>
        )}
        <a
          href={issue.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          ↗ Open on GitHub
        </a>
      </footer>
    </article>
  );
}

export default function TicketsPage({ subjectRepo }) {
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);
  const [showClosed, setShowClosed] = useState(false);
  const [closedIssues, setClosedIssues] = useState([]);
  const [closedLoading, setClosedLoading] = useState(false);

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    try {
      const data = await fetchIssues(subjectRepo, { state: "open" });
      if (!isMountedRef.current) return;
      setIssues(data.items);
      setError(null);
      setRefreshedAt(new Date());
    } catch (exc) {
      if (!isMountedRef.current) return;
      setError(exc?.message || String(exc));
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [subjectRepo]);

  const loadClosed = useCallback(async () => {
    setClosedLoading(true);
    try {
      const data = await fetchIssues(subjectRepo, { state: "closed" });
      if (!isMountedRef.current) return;
      setClosedIssues(data.items);
    } catch {
      // non-critical — closed section fails silently
    } finally {
      if (isMountedRef.current) setClosedLoading(false);
    }
  }, [subjectRepo]);

  useEffect(() => {
    if (showClosed) loadClosed();
  }, [showClosed, loadClosed]);

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

  const handleCreate = useCallback(
    async (payload) => {
      setActionBusy(true);
      setActionMessage(null);
      try {
        const created = await createIssue({ repo: subjectRepo, ...payload });
        setActionMessage({
          kind: "success",
          text: `Ticket #${created.number} created.`,
        });
        setCreateOpen(false);
        await load();
      } catch (exc) {
        setActionMessage({ kind: "error", text: exc?.message || String(exc) });
      } finally {
        setActionBusy(false);
      }
    },
    [subjectRepo, load]
  );

  const handleClose = useCallback(
    async (issue) => {
      setActionBusy(true);
      setActionMessage(null);
      try {
        await updateIssue(issue.number, {
          repo: subjectRepo,
          state: "closed",
          state_reason: "completed",
        });
        setActionMessage({ kind: "success", text: `Ticket #${issue.number} closed.` });
        await load();
        if (showClosed) await loadClosed();
      } catch (exc) {
        setActionMessage({ kind: "error", text: exc?.message || String(exc) });
      } finally {
        setActionBusy(false);
      }
    },
    [subjectRepo, load, loadClosed, showClosed]
  );

  const handleReopen = useCallback(
    async (issue) => {
      setActionBusy(true);
      setActionMessage(null);
      try {
        await updateIssue(issue.number, { repo: subjectRepo, state: "open" });
        setActionMessage({ kind: "success", text: `Ticket #${issue.number} reopened.` });
        await load();
        await loadClosed();
      } catch (exc) {
        setActionMessage({ kind: "error", text: exc?.message || String(exc) });
      } finally {
        setActionBusy(false);
      }
    },
    [subjectRepo, load, loadClosed]
  );

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-6 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Tickets
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {subjectRepo} · {issues.length} open
            {showClosed && closedIssues.length > 0 ? ` · ${closedIssues.length} closed` : ""}
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
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="rounded-lg border border-emerald-600 bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
          >
            + New ticket
          </button>
        </div>
      </header>

      {actionMessage ? (
        <div
          role="status"
          className={`rounded-lg border px-3 py-2 text-sm ${
            actionMessage.kind === "success"
              ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-700/60 dark:bg-emerald-950/40 dark:text-emerald-300"
              : "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-700/60 dark:bg-rose-950/40 dark:text-rose-300"
          }`}
        >
          {actionMessage.text}
        </div>
      ) : null}

      {loading && issues.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading tickets…</p>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-700/60 dark:bg-rose-950/40 dark:text-rose-300"
        >
          Failed to load tickets: {error}
        </div>
      ) : null}

      {!loading && !error && issues.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
          No open tickets on {subjectRepo}.
        </p>
      ) : null}

      <div className="flex flex-col gap-4">
        {issues.map((issue) => (
          <IssueCard key={issue.number} issue={issue} onClose={handleClose} onReopen={handleReopen} />
        ))}
      </div>

      <div className="mt-2">
        <button
          type="button"
          onClick={() => setShowClosed((v) => !v)}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
        >
          <span aria-hidden>{showClosed ? "▾" : "▸"}</span>
          {showClosed ? "Hide closed tickets" : "Show closed tickets"}
        </button>

        {showClosed ? (
          <div className="mt-3 flex flex-col gap-3">
            {closedLoading ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">Loading closed tickets…</p>
            ) : closedIssues.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No closed tickets.</p>
            ) : (
              closedIssues.map((issue) => (
                <IssueCard key={issue.number} issue={issue} onClose={handleClose} onReopen={handleReopen} />
              ))
            )}
          </div>
        ) : null}
      </div>

      <CreateIssueDialog
        open={createOpen}
        busy={actionBusy}
        onCancel={() => setCreateOpen(false)}
        onSubmit={handleCreate}
      />
    </section>
  );
}
