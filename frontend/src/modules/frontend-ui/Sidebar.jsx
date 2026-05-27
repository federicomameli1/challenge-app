const NAV_ITEMS = [
  { id: "home", label: "Home", icon: "◇" },
  { id: "pulls", label: "Approvals", icon: "↪" },
  { id: "releases", label: "Releases", icon: "▲" },
  { id: "health", label: "Health", icon: "♥" },
  { id: "tickets", label: "Tickets", icon: "◉" },
];

export default function Sidebar({
  activeView,
  onChange,
  subjectRepo,
  expertMode,
  onToggleExpert,
}) {
  return (
    <aside
      className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white px-3 py-4 transition-theme duration-200 dark:border-slate-800 dark:bg-slate-900"
      aria-label="Primary navigation"
    >
      <div className="px-2 pb-4">
        <h1 className="text-xl font-semibold tracking-tight text-emerald-700 dark:text-emerald-400">
          Verdict
        </h1>
      </div>

      <nav className="flex flex-col gap-0.5" data-testid="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const isActive = activeView === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onChange(item.id)}
              aria-current={isActive ? "page" : undefined}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                isActive
                  ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              <span aria-hidden className="w-4 text-base leading-none">
                {item.icon}
              </span>
              <span className="font-medium">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-800/60">
        <p className="font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Project
        </p>
        <p className="mt-1 truncate text-sm font-medium text-slate-800 dark:text-slate-100" title={subjectRepo}>
          {subjectRepo}
        </p>
      </div>

      <div className="mt-auto pt-4">
        <button
          type="button"
          onClick={onToggleExpert}
          aria-pressed={expertMode}
          className={`flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
            expertMode
              ? "border-slate-300 bg-slate-900 text-white dark:border-slate-600 dark:bg-slate-100 dark:text-slate-900"
              : "border-slate-200 bg-white text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          }`}
          title="Toggle the legacy multi-agent dashboard"
        >
          <span className="flex items-center gap-2">
            <span aria-hidden>⚙</span>
            <span className="font-medium">Expert mode</span>
          </span>
          <span className="text-xs uppercase tracking-wide opacity-80">
            {expertMode ? "on" : "off"}
          </span>
        </button>
      </div>
    </aside>
  );
}
