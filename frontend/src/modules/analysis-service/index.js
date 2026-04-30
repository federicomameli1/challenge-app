/**
 * Analysis Service Module — v1.0.3
 *
 * Stateless module that maintains requirements and test-case registries
 * and provides traceability / gap-analysis functions.
 *
 * Dependencies: none (leaf module)
 */

// ── Requirements Registry (REQ-101) ─────────────────────────────────
export const requirements = [
  { id: "REQ-101", module: "analysis-service", version: "1.0.3", description: "Maintain requirements registry", status: "implemented" },
  { id: "REQ-102", module: "analysis-service", version: "1.0.3", description: "Maintain test-case registry", status: "implemented" },
  { id: "REQ-103", module: "analysis-service", version: "1.0.3", description: "Build traceability matrix", status: "implemented" },
  { id: "REQ-104", module: "analysis-service", version: "1.0.3", description: "Detect untested requirements", status: "implemented" },
  { id: "REQ-105", module: "analysis-service", version: "1.0.3", description: "Detect version mismatches", status: "partially-implemented" },
  { id: "REQ-201", module: "release-api",      version: "1.1.0", description: "Return evaluation for a version", status: "implemented" },
  { id: "REQ-202", module: "release-api",      version: "1.1.0", description: "Compute coverage score", status: "implemented" },
  { id: "REQ-203", module: "release-api",      version: "1.1.0", description: "Return GO/NO-GO verdict", status: "implemented" },
  { id: "REQ-301", module: "frontend-ui",      version: "1.2.0", description: "Render version and verdict", status: "implemented" },
  { id: "REQ-302", module: "frontend-ui",      version: "1.2.0", description: "Render traceability matrix", status: "implemented" },
  { id: "REQ-303", module: "frontend-ui",      version: "1.2.0", description: "Show inconsistency report", status: "implemented" },
];

// ── Test-Case Registry (REQ-102) ─────────────────────────────────────
// NOTE: REQ-105 intentionally has NO test (controlled inconsistency #1)
// NOTE: TEST-202 targets v1.0.0 instead of v1.1.0 (controlled inconsistency #2)
export const testCases = [
  { id: "TEST-101", verifiesReqId: "REQ-101", targetVersion: "1.0.3", description: "Verify requirements registry returns all entries" },
  { id: "TEST-102", verifiesReqId: "REQ-102", targetVersion: "1.0.3", description: "Verify test-case registry links to valid req IDs" },
  { id: "TEST-103", verifiesReqId: "REQ-103", targetVersion: "1.0.3", description: "Verify traceability matrix maps reqs to tests" },
  { id: "TEST-104", verifiesReqId: "REQ-104", targetVersion: "1.0.3", description: "Verify gap detection finds untested requirements" },
  // no TEST for REQ-105 — controlled inconsistency #1
  { id: "TEST-201", verifiesReqId: "REQ-201", targetVersion: "1.1.0", description: "Verify evaluation returns structured result" },
  { id: "TEST-202", verifiesReqId: "REQ-202", targetVersion: "1.0.0", description: "Verify coverage score calculation" },  // ⚠️ outdated version
  { id: "TEST-203", verifiesReqId: "REQ-203", targetVersion: "1.1.0", description: "Verify GO/NO-GO verdict logic" },
  { id: "TEST-301", verifiesReqId: "REQ-301", targetVersion: "1.2.0", description: "Verify dashboard renders version and verdict" },
  { id: "TEST-302", verifiesReqId: "REQ-302", targetVersion: "1.2.0", description: "Verify matrix table renders" },
  { id: "TEST-303", verifiesReqId: "REQ-303", targetVersion: "1.2.0", description: "Verify inconsistency report displays issues" },
];

// ── Traceability Matrix (REQ-103) ────────────────────────────────────
export function buildTraceabilityMatrix() {
  return requirements.map((req) => {
    const linkedTests = testCases.filter((t) => t.verifiesReqId === req.id);
    return {
      requirementId: req.id,
      description: req.description,
      module: req.module,
      status: req.status,
      tests: linkedTests.map((t) => t.id),
      covered: linkedTests.length > 0,
    };
  });
}

// ── Gap Detection (REQ-104) ──────────────────────────────────────────
export function findUntestedRequirements() {
  const testedReqIds = new Set(testCases.map((t) => t.verifiesReqId));
  return requirements.filter((r) => !testedReqIds.has(r.id));
}

// ── Version-Mismatch Detection (REQ-105 — partially implemented) ────
// Controlled inconsistency #3: only checks MAJOR version, ignores minor/patch
export function detectVersionMismatches() {
  return testCases
    .map((test) => {
      const req = requirements.find((r) => r.id === test.verifiesReqId);
      if (!req) return null;
      const testMajor = test.targetVersion.split(".")[0];
      const reqMajor = req.version.split(".")[0];
      // BUG: only compares major — misses minor/patch drift (e.g. 1.0.0 vs 1.1.0)
      if (testMajor !== reqMajor) {
        return { testId: test.id, reqId: req.id, expected: req.version, actual: test.targetVersion };
      }
      return null;
    })
    .filter(Boolean);
}

// ── Aggregate Report ─────────────────────────────────────────────────
export function getAnalysisReport() {
  return {
    matrix: buildTraceabilityMatrix(),
    untestedRequirements: findUntestedRequirements(),
    versionMismatches: detectVersionMismatches(),
    totalRequirements: requirements.length,
    totalTests: testCases.length,
  };
}
