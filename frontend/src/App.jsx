import { useEffect, useState } from "react";
import CiPanel from "./modules/frontend-ui/CiPanel.jsx";
import ReleaseDashboard from "./modules/frontend-ui/ReleaseDashboard.jsx";

const TABS = [
  { id: "console", label: "Agent Console" },
  { id: "ci", label: "CI / CD Pipeline" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState("console");
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('theme') === 'dark');

  useEffect(() => {
    const root = document.documentElement;
    if (darkMode) {
      root.classList.add('dark');
      root.style.colorScheme = 'dark';
      localStorage.setItem('theme', 'dark');
    } else {
      root.classList.remove('dark');
      root.style.colorScheme = 'light';
      localStorage.setItem('theme', 'light');
    }
  }, [darkMode]);

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="mx-auto flex w-full max-w-[1820px] shrink-0 items-center justify-between gap-4 px-4 pb-2 pt-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Hitachi Challenge
        </h1>
        <div className="flex items-center gap-3">
          <nav className="relative flex rounded-full border border-slate-200 bg-white p-1 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            {/* Sliding pill that moves under the active tab */}
            <div
              className="absolute inset-y-1 rounded-full bg-slate-900 shadow-sm transition-transform duration-300 ease-in-out dark:bg-slate-100"
              style={{
                left: "4px",
                width: "calc(50% - 4px)",
                transform: activeTab === "ci" ? "translateX(100%)" : "translateX(0)",
              }}
            />
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`relative z-10 flex-1 select-none rounded-full px-4 py-1.5 text-sm font-medium transition-colors duration-200 ${
                  activeTab === tab.id
                    ? "text-white dark:text-slate-900"
                    : "text-slate-600 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
          <button
            type="button"
            onClick={() => setDarkMode((prev) => !prev)}
            className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 shadow-sm hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label="Toggle dark mode"
          >
            {darkMode ? "☀ Light" : "☾ Dark"}
          </button>
        </div>
      </div>

      <hr className="mx-auto w-full max-w-[1820px] shrink-0 border-slate-200 dark:border-slate-700" />

      <div className="min-h-0 flex-1 overflow-hidden">
        {activeTab === "console" ? (
          <ReleaseDashboard />
        ) : (
          <div className="mx-auto flex h-full w-full max-w-[1820px] flex-col overflow-hidden px-4 py-4">
            <CiPanel standalone />
          </div>
        )}
      </div>
    </main>
  );
}
