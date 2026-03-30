/**
 * Frontend UI Module — v1.2.0
 *
 * React component that renders the Release Decision Dashboard.
 * Three tabs: Traceability Matrix, Evaluation, Inconsistencies.
 *
 * Dependencies: release-api@^1.1.0
 */

import { useState } from "react";
import { evaluateRelease } from "../release-api/index.js";

const TABS = ["Matrix", "Evaluation", "Issues"];

export default function ReleaseDashboard() {
  const [activeTab, setActiveTab] = useState("Evaluation");
  const evaluation = evaluateRelease("1.1.0");

  return (
    <section className="mx-auto max-w-4xl px-6 py-12">
      <h2 className="mb-1 text-2xl font-semibold tracking-tight">
        Release Decision Dashboard
      </h2>
      <p className="mb-6 text-sm text-slate-500">
        Release Evaluation Tool — analysis-service v1.0.3 · release-api v1.1.0 · frontend-ui v1.2.0
      </p>

      {/* ── Tab bar ──────────────────────────────────── */}
      <nav className="mb-6 flex gap-1 rounded-lg bg-slate-200 p-1" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition ${
              activeTab === tab
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {tab}
          </button>
        ))}
      </nav>

      {/* ── Tab content ──────────────────────────────── */}
      {activeTab === "Matrix" && <MatrixView matrix={evaluation.matrix} />}
      {activeTab === "Evaluation" && <EvaluationView evaluation={evaluation} />}
      {activeTab === "Issues" && <IssuesView evaluation={evaluation} />}
    </section>
  );
}

/* ── Evaluation Tab (REQ-301) ──────────────────────────────────────── */
function EvaluationView({ evaluation }) {
  const isGo = evaluation.verdict === "GO";
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <span
          data-testid="verdict-badge"
          className={`rounded-full px-4 py-1.5 text-sm font-bold tracking-wide ${
            isGo
              ? "bg-emerald-100 text-emerald-700"
              : "bg-red-100 text-red-700"
          }`}
        >
          {evaluation.verdict}
        </span>
        <span className="text-sm text-slate-500">
          Version <strong>{evaluation.version}</strong>
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Stat label="Coverage" value={`${evaluation.coverage}%`} />
        <Stat label="Requirements" value={evaluation.totalRequirements} />
        <Stat label="Tests" value={evaluation.totalTests} />
      </div>

      {evaluation.blockers.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="mb-2 text-sm font-semibold text-amber-800">
            Blockers ({evaluation.blockers.length})
          </h3>
          <ul className="space-y-1 text-sm text-amber-700">
            {evaluation.blockers.map((b, i) => (
              <li key={i}>
                <span className="mr-1 font-mono text-xs uppercase text-amber-500">
                  [{b.severity}]
                </span>
                {b.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 text-center">
      <p className="text-2xl font-semibold text-slate-900">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}

/* ── Matrix Tab (REQ-302) ──────────────────────────────────────────── */
function MatrixView({ matrix }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm" role="table">
        <thead>
          <tr className="border-b border-slate-200 text-xs uppercase text-slate-400">
            <th className="py-2 pr-3">Req ID</th>
            <th className="py-2 pr-3">Description</th>
            <th className="py-2 pr-3">Module</th>
            <th className="py-2 pr-3">Tests</th>
            <th className="py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {matrix.map((row) => (
            <tr
              key={row.requirementId}
              className={`border-b border-slate-100 ${
                !row.covered ? "bg-red-50" : ""
              }`}
            >
              <td className="py-2 pr-3 font-mono text-xs">{row.requirementId}</td>
              <td className="py-2 pr-3">{row.description}</td>
              <td className="py-2 pr-3 text-slate-500">{row.module}</td>
              <td className="py-2 pr-3 font-mono text-xs">
                {row.tests.length > 0 ? row.tests.join(", ") : (
                  <span className="text-red-500">—</span>
                )}
              </td>
              <td className="py-2">
                {row.covered ? (
                  <span className="text-emerald-600">✓ covered</span>
                ) : (
                  <span className="font-medium text-red-600">✗ gap</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Issues Tab (REQ-303) ──────────────────────────────────────────── */
function IssuesView({ evaluation }) {
  const issues = [
    { id: 1, type: "Untested Requirement", detail: "REQ-105 (Detect version mismatches) has no corresponding test case", severity: "critical" },
    { id: 2, type: "Outdated Test Target", detail: "TEST-202 references release-api v1.0.0 but current version is v1.1.0", severity: "warning" },
    { id: 3, type: "Partial Implementation", detail: "REQ-105 is partially implemented — only checks major version number", severity: "major" },
    { id: 4, type: "VDD Version Mismatch", detail: "VDD summary references analysis-service v1.0.1 instead of current v1.0.3", severity: "info" },
  ];

  const severityColors = {
    critical: "bg-red-100 text-red-700",
    major: "bg-orange-100 text-orange-700",
    warning: "bg-amber-100 text-amber-700",
    info: "bg-blue-100 text-blue-700",
  };

  return (
    <div className="space-y-3" data-testid="inconsistency-report">
      <p className="text-sm text-slate-500">
        {issues.length} documentation inconsistencies detected
      </p>
      {issues.map((issue) => (
        <div
          key={issue.id}
          className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-4"
        >
          <span
            className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${
              severityColors[issue.severity]
            }`}
          >
            {issue.severity}
          </span>
          <div>
            <p className="text-sm font-medium text-slate-900">{issue.type}</p>
            <p className="text-sm text-slate-500">{issue.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
