/**
 * Analysis Service — Unit Tests
 *
 * TEST-101 through TEST-104
 * NOTE: No test for REQ-105 (controlled inconsistency #1)
 */

import { describe, it, expect } from "vitest";
import {
  requirements,
  testCases,
  buildTraceabilityMatrix,
  findUntestedRequirements,
} from "./index.js";

// TEST-101 — Verify requirements registry (REQ-101)
describe("Requirements Registry", () => {
  it("TEST-101: returns all requirements with correct fields", () => {
    expect(requirements.length).toBeGreaterThanOrEqual(1);
    requirements.forEach((req) => {
      expect(req).toHaveProperty("id");
      expect(req).toHaveProperty("description");
      expect(req).toHaveProperty("module");
      expect(req).toHaveProperty("version");
      expect(req.id).toMatch(/^REQ-\d+$/);
    });
  });
});

// TEST-102 — Verify test-case registry (REQ-102)
describe("Test-Case Registry", () => {
  it("TEST-102: every test links to a valid requirement ID", () => {
    const reqIds = new Set(requirements.map((r) => r.id));
    testCases.forEach((tc) => {
      expect(reqIds.has(tc.verifiesReqId)).toBe(true);
    });
  });
});

// TEST-103 — Verify traceability matrix (REQ-103)
describe("Traceability Matrix", () => {
  it("TEST-103: maps every requirement to its linked tests", () => {
    const matrix = buildTraceabilityMatrix();
    expect(matrix.length).toBe(requirements.length);
    matrix.forEach((row) => {
      expect(row).toHaveProperty("requirementId");
      expect(row).toHaveProperty("tests");
      expect(row).toHaveProperty("covered");
    });
    // REQ-101 should be covered (TEST-101 exists)
    const row101 = matrix.find((r) => r.requirementId === "REQ-101");
    expect(row101.covered).toBe(true);
    expect(row101.tests).toContain("TEST-101");
  });
});

// TEST-104 — Verify gap detection (REQ-104)
describe("Gap Detection", () => {
  it("TEST-104: finds requirements with no linked test", () => {
    const gaps = findUntestedRequirements();
    const gapIds = gaps.map((g) => g.id);
    // REQ-105 has no test — should appear in gaps
    expect(gapIds).toContain("REQ-105");
  });
});
