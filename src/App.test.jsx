import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "./App.jsx";

beforeEach(() => {
  global.fetch = vi.fn(async (input, init = {}) => {
    const url = String(input);
    const method = String(init.method || "GET").toUpperCase();

    if (url.endsWith("/datasets/custom-sets") && method === "GET") {
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [] }),
      };
    }

    if (url.endsWith("/agents/validate") && method === "POST") {
      const body = JSON.parse(String(init.body || "{}"));
      return {
        ok: true,
        status: 200,
        json: async () => ({
          exists: true,
          adapter_kind:
            body.agent === "agent4" ? body.source_adapter_kind || "apcs_doc_bundle" : "structured_dataset",
          missing_optional: [],
          present_optional: [],
          notes: [],
          resolved_dataset_root: body.dataset_root,
        }),
      };
    }

    if (url.endsWith("/agents/scenarios") && method === "POST") {
      const body = JSON.parse(String(init.body || "{}"));
      return {
        ok: true,
        status: 200,
        json: async () => ({
          items:
            body.agent === "agent4"
              ? [{ scenario_id: "APCS-S4-001", release_id: "APCS-REL-1.1.0" }]
              : [{ scenario_id: "P5V2-001", release_id: "P5-REL-2.1.0" }],
          resolved_dataset_root: body.dataset_root,
        }),
      };
    }

    if (url.endsWith("/agents/run") && method === "POST") {
      const body = JSON.parse(String(init.body || "{}"));
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          mode: "single",
          payload: {
            scenario_id: body.scenario_id || (body.agent === "agent4" ? "APCS-S4-001" : "P5V2-001"),
            release_id: body.agent === "agent4" ? "REL-2026.04.01" : "P5-REL-2.1.0",
            decision: "GO",
            confidence: "high",
            decision_type: "deterministic",
            reasons: [
              {
                title: "All hard release gates passed",
                detail: "No blocking evidence was found.",
                rule_code: null,
                evidence: [],
              },
            ],
            evidence: [],
            summary: "GO recommended.",
            human_action: "Ready for human review.",
            policy_version: body.agent === "agent4" ? "phase4-policy-v1" : "phase5-policy-v1",
            timestamp_utc: "2026-04-20T16:40:00Z",
            rule_findings: {
              triggered_rule_codes: [],
              findings: [],
            },
            schema_validation: {
              valid: true,
              errors: [],
            },
          },
          diagnostics: {
            schema_error_detected: false,
            label_mismatch_detected: false,
          },
        }),
      };
    }

    return {
      ok: true,
      status: 200,
      json: async () => ({}),
    };
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

it("renders the heading", () => {
  render(<App />);
  expect(
    screen.getByRole("heading", { name: /hitachi challenge/i })
  ).toBeInTheDocument();
});

it("does not render the demo button or helper text", () => {
  render(<App />);
  expect(
    screen.queryByText(/simple demo page for ci\/cd testing/i)
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /demo button/i })
  ).not.toBeInTheDocument();
});

it("renders the release dashboard section", () => {
  render(<App />);
  expect(
    screen.getByRole("heading", { name: /backend-native release workflow/i })
  ).toBeInTheDocument();
});
