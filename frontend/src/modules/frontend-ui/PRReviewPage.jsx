import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  approvePull,
  fetchPulls,
  rejectPull,
} from "./dashboardApi.js";
import StatusPill from "./StatusPill.jsx";

const REFRESH_INTERVAL_MS = 30_000;

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

function ConfirmApproveDialog({ pr, busy, onConfirm, onCancel }) {
  if (!pr) return null;
  const verdict = pr.last_review?.verdict || null;
  const isHold = verdict === "HOLD";
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm px-4"
    >
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          Approve & merge PR #{pr.number}?
        </h2>
        {isHold ? (
          <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200">
            <strong>Heads up:</strong> Verdict returned <strong>HOLD</strong> on this PR. You can still
            approve and merge — the LLM is advisory — but read the report carefully first.
          </div>
        ) : null}
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          This submits a GitHub <strong>APPROVE</strong> review and merges the
          PR via the API (squash merge). The action cannot be undone — make
          sure you have read the verdict and the report.
        </p>
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
            onClick={onConfirm}
            disabled={busy}
            className="rounded-lg border border-emerald-600 bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy ? "Approving…" : "Approve & merge"}
          </button>
        </div>
      </div>
    </div>
  );
}

function RejectDialog({ pr, busy, onConfirm, onCancel }) {
  const [body, setBody] = useState("");
  useEffect(() => {
    setBody("");
  }, [pr?.number]);
  if (!pr) return null;
  const canSubmit = body.trim().length >= 3;
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm px-4"
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          Request changes on PR #{pr.number}
        </h2>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          A reason is required by GitHub for REQUEST_CHANGES reviews.
        </p>
        <textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          rows={5}
          placeholder="Explain what needs to change before this PR can be merged…"
          className="mt-3 w-full resize-vertical rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
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
            onClick={() => onConfirm(body.trim())}
            disabled={busy || !canSubmit}
            className="rounded-lg border border-rose-600 bg-rose-600 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-50"
          >
            {busy ? "Submitting…" : "Request changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

function PRCard({ pr, onApprove, onReject }) {
  const [expanded, setExpanded] = useState(false);
  const review = pr.last_review;
  const verdict = review?.verdict || null;
  const summary = review?.summary || (review ? "" : "Awaiting Verdict review…");

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-theme duration-200 dark:border-slate-700 dark:bg-slate-900">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold text-slate-900 dark:text-slate-100">
            <span className="text-slate-500 dark:text-slate-400">#{pr.number} · </span>
            {pr.title || "(no title)"}
          </h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            by <span className="font-medium text-slate-700 dark:text-slate-300">{pr.author || "unknown"}</span>
            {" · "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] dark:bg-slate-800">{pr.branch}</code>
            {" → "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] dark:bg-slate-800">{pr.base}</code>
            {" · "}
            <span title={pr.updated_at}>{timeAgo(pr.updated_at)}</span>
          </p>
        </div>
        <StatusPill tone={verdictTone(verdict)} label={verdict || "PENDING"} />
      </header>

      <p className="mt-3 text-sm leading-relaxed text-slate-700 dark:text-slate-200">
        {summary}
      </p>

      {review?.body_markdown ? (
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
{review.body_markdown}
            </pre>
          ) : null}
        </div>
      ) : null}

      <footer className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => onApprove(pr)}
          disabled={!verdict}
          title={
            verdict
              ? "Submit a GitHub APPROVE review and merge this PR"
              : "Waiting for Verdict review to complete before approval is allowed"
          }
          className="rounded-lg border border-emerald-600 bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:border-emerald-300 disabled:bg-emerald-300 disabled:hover:bg-emerald-300 dark:disabled:border-emerald-900/60 dark:disabled:bg-emerald-900/60 dark:disabled:text-emerald-200/60"
        >
          Approve &amp; merge
        </button>
        <button
          type="button"
          onClick={() => onReject(pr)}
          className="rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-sm font-semibold text-rose-700 hover:bg-rose-50 dark:border-rose-700/60 dark:bg-slate-900 dark:text-rose-300 dark:hover:bg-rose-950/30"
        >
          Request changes
        </button>
        <a
          href={pr.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          ↗ Open on GitHub
        </a>
        {!verdict ? (
          <span className="ml-auto text-xs italic text-slate-500 dark:text-slate-400">
            Approve is locked until Verdict review completes.
          </span>
        ) : null}
      </footer>
    </article>
  );
}

export default function PRReviewPage({ subjectRepo }) {
  const [pulls, setPulls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);

  const [approveTarget, setApproveTarget] = useState(null);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    try {
      const data = await fetchPulls(subjectRepo, "open");
      if (!isMountedRef.current) return;
      setPulls(data.items);
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

  const handleApprove = useCallback(async () => {
    if (!approveTarget) return;
    setActionBusy(true);
    setActionMessage(null);
    try {
      const result = await approvePull(approveTarget.number, {
        repo: subjectRepo,
        body: "Approved via Verdict.",
        merge: true,
      });
      const merged = result?.merged;
      const selfSkipped = result?.review_state === "SELF_REVIEW_SKIPPED";
      let text;
      if (merged && selfSkipped) {
        text = `PR #${approveTarget.number} merged (self-review skipped — GitHub forbids approving your own PR).`;
      } else if (merged) {
        text = `PR #${approveTarget.number} approved and merged.`;
      } else {
        text = `PR #${approveTarget.number} ${selfSkipped ? "" : "approved"}. Merge could not complete: ${result?.message || "see GitHub"}`;
      }
      setActionMessage({ kind: "success", text });
      setApproveTarget(null);
      await load();
    } catch (exc) {
      setActionMessage({ kind: "error", text: exc?.message || String(exc) });
    } finally {
      setActionBusy(false);
    }
  }, [approveTarget, load, subjectRepo]);

  const handleReject = useCallback(
    async (body) => {
      if (!rejectTarget) return;
      setActionBusy(true);
      setActionMessage(null);
      try {
        await rejectPull(rejectTarget.number, {
          repo: subjectRepo,
          body,
        });
        setActionMessage({
          kind: "success",
          text: `Changes requested on PR #${rejectTarget.number}.`,
        });
        setRejectTarget(null);
        await load();
      } catch (exc) {
        setActionMessage({ kind: "error", text: exc?.message || String(exc) });
      } finally {
        setActionBusy(false);
      }
    },
    [rejectTarget, load, subjectRepo]
  );

  const counts = useMemo(() => {
    const go = pulls.filter((p) => p.last_review?.verdict === "GO").length;
    const hold = pulls.filter((p) => p.last_review?.verdict === "HOLD").length;
    const pending = pulls.length - go - hold;
    return { total: pulls.length, go, hold, pending };
  }, [pulls]);

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-6 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            PR Review
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {subjectRepo} · {counts.total} open
            {counts.total > 0 ? (
              <span>
                {" "}· {counts.go} GO · {counts.hold} HOLD · {counts.pending} pending
              </span>
            ) : null}
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

      {loading && pulls.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading pull requests…</p>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-700/60 dark:bg-rose-950/40 dark:text-rose-300"
        >
          Failed to load pull requests: {error}
        </div>
      ) : null}

      {!loading && !error && pulls.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
          No open pull requests on {subjectRepo}.
        </p>
      ) : null}

      <div className="flex flex-col gap-4">
        {pulls.map((pr) => (
          <PRCard
            key={pr.number}
            pr={pr}
            onApprove={setApproveTarget}
            onReject={setRejectTarget}
          />
        ))}
      </div>

      <ConfirmApproveDialog
        pr={approveTarget}
        busy={actionBusy}
        onConfirm={handleApprove}
        onCancel={() => setApproveTarget(null)}
      />
      <RejectDialog
        pr={rejectTarget}
        busy={actionBusy}
        onConfirm={handleReject}
        onCancel={() => setRejectTarget(null)}
      />
    </section>
  );
}
