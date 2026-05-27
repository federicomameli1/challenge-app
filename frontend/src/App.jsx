import { useEffect, useMemo, useState } from "react";
import ExpertConsole from "./modules/frontend-ui/ExpertConsole.jsx";
import HomePage from "./modules/frontend-ui/HomePage.jsx";
import PRReviewPage from "./modules/frontend-ui/PRReviewPage.jsx";
import PlaceholderPage from "./modules/frontend-ui/PlaceholderPage.jsx";
import ReleasesPage from "./modules/frontend-ui/ReleasesPage.jsx";
import Sidebar from "./modules/frontend-ui/Sidebar.jsx";
import TicketsPage from "./modules/frontend-ui/TicketsPage.jsx";

const DEFAULT_SUBJECT_REPO = "federicomameli1/wayside-monitor";

const THEME_OPTIONS = ["light", "dark", "system"];

function readStoredTheme() {
  const stored = localStorage.getItem("theme");
  return THEME_OPTIONS.includes(stored) ? stored : "system";
}

function systemPrefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(theme) {
  const root = document.documentElement;
  const isDark = theme === "dark" || (theme === "system" && systemPrefersDark());
  root.classList.toggle("dark", isDark);
  root.style.colorScheme = isDark ? "dark" : "light";
}

export default function App() {
  const [activeView, setActiveView] = useState("home");
  const [expertMode, setExpertMode] = useState(false);
  const [subjectRepo] = useState(DEFAULT_SUBJECT_REPO);
  const [theme, setTheme] = useState(readStoredTheme);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    if (theme !== "system") return undefined;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const themeMeta = useMemo(() => {
    if (theme === "light") return { label: "☀ Light", next: "dark" };
    if (theme === "dark") return { label: "☾ Dark", next: "system" };
    return { label: "✦ System", next: "light" };
  }, [theme]);

  const view = expertMode ? "console" : activeView;

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 text-slate-900 transition-theme duration-200 dark:bg-slate-950 dark:text-slate-100">
      <Sidebar
        activeView={activeView}
        onChange={(next) => {
          setActiveView(next);
          if (expertMode) setExpertMode(false);
        }}
        subjectRepo={subjectRepo}
        expertMode={expertMode}
        onToggleExpert={() => setExpertMode((value) => !value)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-6 py-3 transition-theme duration-200 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="text-base font-semibold text-slate-700 dark:text-slate-200">
            {view === "home" && "Home"}
            {view === "pulls" && "PR Review"}
            {view === "releases" && "Releases"}
            {view === "health" && "Health"}
            {view === "tickets" && "Tickets"}
            {view === "console" && "Expert mode"}
          </h2>
          <button
            type="button"
            onClick={() => setTheme(themeMeta.next)}
            className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 shadow-sm transition-theme duration-200 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            aria-label={`Theme: ${theme}. Click to switch to ${themeMeta.next}.`}
            title={`Theme: ${theme} → ${themeMeta.next}`}
          >
            {themeMeta.label}
          </button>
        </header>

        <main className="min-h-0 flex-1 overflow-auto">
          {view === "home" && (
            <HomePage subjectRepo={subjectRepo} onNavigate={setActiveView} />
          )}
          {view === "pulls" && <PRReviewPage subjectRepo={subjectRepo} />}
          {view === "releases" && <ReleasesPage subjectRepo={subjectRepo} />}
          {view === "health" && (
            <PlaceholderPage
              title="Cluster Health"
              hint="Will surface ArgoCD app status for mgmt / test / prod via the notifications webhook (Phase E)."
            />
          )}
          {view === "tickets" && <TicketsPage subjectRepo={subjectRepo} />}
          {view === "console" && <ExpertConsole />}
        </main>
      </div>
    </div>
  );
}
