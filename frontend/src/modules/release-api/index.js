/**
 * Release API Module — v1.1.0
 *
 * Service layer that evaluates release-readiness by aggregating
 * analysis results and applying go/no-go rules.
 *
 * Dependencies: analysis-service@^1.0.0
 */

import { getAnalysisReport } from "../analysis-service/index.js";

/**
 * Evaluate whether a given version is ready for release.
 * REQ-201: Return structured evaluation
 * REQ-202: Compute coverage score
 * REQ-203: Return GO/NO-GO verdict
 */
export function evaluateRelease(version) {
  const report = getAnalysisReport();

  // REQ-202 — coverage = tested requirements / total requirements
  const coveredCount = report.matrix.filter((r) => r.covered).length;
  const coverage = Math.round((coveredCount / report.totalRequirements) * 100);

  // REQ-203 — collect blockers
  const blockers = [];

  if (report.untestedRequirements.length > 0) {
    report.untestedRequirements.forEach((req) => {
      blockers.push({
        type: "untested-requirement",
        severity: req.status === "partially-implemented" ? "critical" : "major",
        message: `${req.id} ("${req.description}") has no test coverage`,
      });
    });
  }

  if (report.versionMismatches.length > 0) {
    report.versionMismatches.forEach((m) => {
      blockers.push({
        type: "version-mismatch",
        severity: "warning",
        message: `${m.testId} targets v${m.actual} but ${m.reqId} is at v${m.expected}`,
      });
    });
  }

  const hasCriticalBlockers = blockers.some((b) => b.severity === "critical");

  // REQ-203 — GO if coverage >= 80% and no critical blockers
  const verdict = coverage >= 80 && !hasCriticalBlockers ? "GO" : "NO-GO";

  return {
    version,
    coverage,
    verdict,
    blockers,
    totalRequirements: report.totalRequirements,
    totalTests: report.totalTests,
    matrix: report.matrix,
  };
}
