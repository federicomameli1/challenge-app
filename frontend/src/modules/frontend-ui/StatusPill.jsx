const TONES = {
  go: {
    label: "GO",
    emoji: "✓",
    classes:
      "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-700/60 dark:bg-emerald-950/50 dark:text-emerald-300",
  },
  hold: {
    label: "HOLD",
    emoji: "⏸",
    classes:
      "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700/60 dark:bg-amber-950/50 dark:text-amber-300",
  },
  blocker: {
    label: "Blocker",
    emoji: "✗",
    classes:
      "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-700/60 dark:bg-rose-950/50 dark:text-rose-300",
  },
  warning: {
    label: "Warning",
    emoji: "!",
    classes:
      "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700/60 dark:bg-amber-950/50 dark:text-amber-300",
  },
  info: {
    label: "Info",
    emoji: "i",
    classes:
      "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-600/60 dark:bg-slate-900 dark:text-slate-300",
  },
  healthy: {
    label: "Healthy",
    emoji: "✓",
    classes:
      "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-700/60 dark:bg-emerald-950/50 dark:text-emerald-300",
  },
  degraded: {
    label: "Degraded",
    emoji: "▲",
    classes:
      "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-700/60 dark:bg-rose-950/50 dark:text-rose-300",
  },
  outofsync: {
    label: "OutOfSync",
    emoji: "↻",
    classes:
      "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700/60 dark:bg-amber-950/50 dark:text-amber-300",
  },
  pending: {
    label: "Pending",
    emoji: "…",
    classes:
      "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-600/60 dark:bg-slate-900 dark:text-slate-300",
  },
  draft: {
    label: "Draft",
    emoji: "✎",
    classes:
      "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-600/60 dark:bg-slate-900 dark:text-slate-300",
  },
};

export default function StatusPill({ tone, label, emoji }) {
  const key = String(tone || "info").toLowerCase().replace(/[^a-z]/g, "");
  const config = TONES[key] || TONES.info;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${config.classes}`}
    >
      <span aria-hidden>{emoji ?? config.emoji}</span>
      <span>{label ?? config.label}</span>
    </span>
  );
}
