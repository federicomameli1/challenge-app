/**
 * Release API — Unit Tests
 *
 * TEST-201, TEST-202, TEST-203
 * NOTE: TEST-202 intentionally references v1.0.0 (controlled inconsistency #2)
 */

import { describe, it, expect } from "vitest";
import { evaluateRelease } from "./index.js";

// TEST-201 — Verify structured evaluation (REQ-201)
describe("Release Evaluation", () => {
  it("TEST-201: returns structured result for a given version", () => {
    const result = evaluateRelease("1.1.0");
    expect(result).toHaveProperty("version", "1.1.0");
    expect(result).toHaveProperty("coverage");
    expect(result).toHaveProperty("verdict");
    expect(result).toHaveProperty("blockers");
    expect(result).toHaveProperty("totalRequirements");
    expect(result).toHaveProperty("totalTests");
  });
});

// TEST-202 — Verify coverage score (REQ-202)
// ⚠️ Controlled inconsistency #2: this test was written for v1.0.0
//    but the module is now at v1.1.0
describe("Coverage Score (written for release-api v1.0.0)", () => {
  it("TEST-202: coverage is a number between 0 and 100", () => {
    const result = evaluateRelease("1.0.0"); // outdated version reference
    expect(result.coverage).toBeGreaterThanOrEqual(0);
    expect(result.coverage).toBeLessThanOrEqual(100);
  });
});

// TEST-203 — Verify GO/NO-GO verdict (REQ-203)
describe("Verdict Logic", () => {
  it("TEST-203: verdict is either GO or NO-GO", () => {
    const result = evaluateRelease("1.1.0");
    expect(["GO", "NO-GO"]).toContain(result.verdict);
  });
});
