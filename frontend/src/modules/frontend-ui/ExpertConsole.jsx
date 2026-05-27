import { useState } from "react";
import CiPanel from "./CiPanel.jsx";
import ReleaseDashboard from "./ReleaseDashboard.jsx";
import VerdictDashboard from "./VerdictDashboard.jsx";

const TABS = [
  { id: "pipeline", label: "Pipeline" },
  { id: "ci", label: "CI / CD" },
  { id: "console", label: "Expert Console" },
];

export default function ExpertConsole() {
  const [tab, setTab] = useState("console");

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-200 bg-white px-6 py-3 dark:border-slate-800 dark:bg-slate-900">
        <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Expert mode — legacy multi-agent surfaces
        </p>
        <div className="mt-2 inline-flex rounded-full border border-slate-200 bg-slate-50 p-1 text-sm dark:border-slate-700 dark:bg-slate-800">
          {TABS.map((item) => {
            const isActive = item.id === tab;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                aria-pressed={isActive}
                className={`select-none rounded-full px-4 py-1.5 font-medium transition-colors ${
                  isActive
                    ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                    : "text-slate-600 hover:text-slate-800 dark:text-slate-300 dark:hover:text-slate-100"
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "pipeline" && <VerdictDashboard />}
        {tab === "ci" && (
          <div className="mx-auto flex h-full w-full max-w-[1820px] flex-col overflow-hidden px-4 py-4">
            <CiPanel standalone />
          </div>
        )}
        {tab === "console" && <ReleaseDashboard />}
      </div>
    </div>
  );
}
