import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ReleaseDashboard from "./ReleaseDashboard.jsx";

const AGENT5_SCENARIOS = [
  { scenario_id: "P5V2-001", release_id: "P5-REL-2.1.0" },
  { scenario_id: "P5V2-003", release_id: "P5-REL-2.1.0" },
  { scenario_id: "P5V2-007", release_id: "P5-REL-2.1.0" },
  { scenario_id: "P5V2-008", release_id: "P5-REL-2.1.0" },
  { scenario_id: "P5V2-024", release_id: "P5-REL-2.1.0" },
];

function buildAgentPayload(agent, decision, scenarioId) {
  const phase = agent === "agent4" ? "Phase 4" : "Phase 5";
  const ruleCode =
    agent === "agent4"
      ? "critical_service_unhealthy"
      : "critical_defect_open";
  const summary =
    decision === "GO"
      ? `${phase} cleared with no hard gate triggered.`
      : `${phase} blocked because a hard gate was triggered.`;

  return {
    scenario_id: scenarioId,
    release_id: agent === "agent4" ? "REL-2026.04.01" : "P5-REL-2.1.0",
    decision,
    confidence: decision === "GO" ? "high" : "medium",
    decision_type: "deterministic",
    reasons:
      decision === "GO"
        ? [
            {
              title: "All hard release gates passed",
              detail: "No blocking evidence was found in the selected dataset.",
              rule_code: null,
              evidence: [],
            },
          ]
        : [
            {
              title: "Blocking evidence detected",
              detail: "A hard gate remains unresolved in the selected dataset.",
              rule_code: ruleCode,
              evidence: [
                {
                  file_path: `${scenarioId}.txt`,
                  line_start: 12,
                  snippet: "Blocking issue still unresolved.",
                },
              ],
            },
          ],
    evidence:
      decision === "GO"
        ? []
        : [
            {
              file_path: `${scenarioId}.txt`,
              line_start: 12,
              snippet: "Blocking issue still unresolved.",
            },
          ],
    summary,
    human_action:
      decision === "GO"
        ? "Ready for human review."
        : "Resolve blockers before promotion.",
    policy_version: agent === "agent4" ? "phase4-policy-v1" : "phase5-policy-v1",
    timestamp_utc: "2026-04-20T16:40:00Z",
    rule_findings: {
      triggered_rule_codes: decision === "GO" ? [] : [ruleCode],
      findings: [
        {
          code: ruleCode,
          triggered: decision !== "GO",
          reason:
            decision === "GO"
              ? "No blocker matched the rule."
              : "Blocking condition matched the rule.",
          evidence:
            decision === "GO"
              ? []
              : [
                  {
                    file_path: `${scenarioId}.txt`,
                    line_start: 12,
                    snippet: "Blocking issue still unresolved.",
                  },
                ],
        },
      ],
    },
    coverage_metrics:
      agent === "agent5"
        ? {
            reason_evidence_coverage: 1,
            triggered_rules_count: decision === "GO" ? 0 : 1,
          }
        : undefined,
    cross_phase_continuity_flags:
      agent === "agent5"
        ? {
            agent4_context_present: true,
            continuity_hold: decision !== "GO",
          }
        : undefined,
    missing_artifacts: agent === "agent5" && decision !== "GO" ? ["agent4_context.json"] : [],
    schema_validation: {
      valid: true,
      errors: [],
    },
  };
}

function buildEvaluateAllResponse(agent) {
  const predictions =
    agent === "agent4"
      ? [
          buildAgentPayload("agent4", "GO", "APCS-S4-001"),
          buildAgentPayload("agent4", "HOLD", "APCS-S4-002"),
        ]
      : [
          buildAgentPayload("agent5", "GO", "P5V2-001"),
          buildAgentPayload("agent5", "HOLD", "P5V2-003"),
        ];

  return {
    ok: true,
    mode: "evaluate_all",
    payload: {
      summary: {
        total_scenarios: predictions.length,
        schema_validity_rate: 1,
        evaluated_scenarios: predictions.length,
        matched: predictions.length,
        accuracy: 1,
      },
      predictions,
      rows: predictions.map((item) => ({
        scenario_id: item.scenario_id,
        expected_decision: item.decision,
        predicted_decision: item.decision,
        match: true,
      })),
    },
    diagnostics: {
      schema_error_detected: false,
      label_mismatch_detected: false,
    },
  };
}

describe("Release Dashboard", () => {
  let backendSets;

  async function renderDashboard() {
    render(<ReleaseDashboard />);
    await screen.findByRole("heading", { name: /backend-native release workflow/i });
  }

  beforeEach(() => {
    localStorage.clear();
    backendSets = [];

    global.fetch = vi.fn(async (input, init = {}) => {
      const url = String(input);
      const method = String(init.method || "GET").toUpperCase();

      if (url.endsWith("/datasets/custom-sets") && method === "GET") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: backendSets }),
        };
      }

      if (url.endsWith("/datasets/custom-sets") && method === "POST") {
        const body = JSON.parse(String(init.body || "{}"));
        const created = {
          id: `SET_CUSTOM_${String(body.label || "set")
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "_")}`,
          label: body.label,
          source: "custom",
          persisted: true,
          documents: (body.documents || []).map((doc) => ({
            name: doc.name,
            filePath: `Dataset/Test_Sets/temp/${doc.name}`,
            text: doc.text,
          })),
          backend: {
            agent4: {
              datasetRoot: "challenge-app/Dataset/Test_Sets/temp",
              sourceAdapterKind: "apcs_doc_bundle",
              scenarioId: "APCS-S4-001",
            },
          },
        };
        backendSets = [...backendSets, created];
        return {
          ok: true,
          status: 200,
          json: async () => created,
        };
      }

      if (url.includes("/datasets/custom-sets/") && method === "DELETE") {
        const setId = decodeURIComponent(url.split("/").pop() || "");
        backendSets = backendSets.filter((set) => set.id !== setId);
        return {
          ok: true,
          status: 200,
          json: async () => ({ ok: true, id: setId }),
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
        const items =
          body.agent === "agent4"
            ? [{ scenario_id: "APCS-S4-001", release_id: "APCS-REL-1.1.0" }]
            : AGENT5_SCENARIOS;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items,
            resolved_dataset_root: body.dataset_root,
          }),
        };
      }

      if (url.endsWith("/agents/run") && method === "POST") {
        const body = JSON.parse(String(init.body || "{}"));

        if (body.evaluate_all) {
          return {
            ok: true,
            status: 200,
            json: async () => buildEvaluateAllResponse(body.agent),
          };
        }

        if (body.agent === "agent4") {
          const isHold = String(body.dataset_root || "").includes("HOLD");
          return {
            ok: true,
            status: 200,
            json: async () => ({
              ok: true,
              mode: "single",
              payload: {
                ...buildAgentPayload(
                  "agent4",
                  isHold ? "HOLD" : "GO",
                  body.scenario_id || "APCS-S4-001"
                ),
                evaluation: body.check_label
                  ? {
                      label_check_performed: true,
                      expected_decision: isHold ? "HOLD" : "GO",
                      actual_decision: isHold ? "HOLD" : "GO",
                      match: true,
                    }
                  : undefined,
              },
              diagnostics: {
                schema_error_detected: false,
                label_mismatch_detected: false,
              },
            }),
          };
        }

        const holdScenarios = new Set(["P5V2-003", "P5V2-007", "P5V2-024"]);
        const scenarioId = body.scenario_id || "P5V2-001";
        const decision = holdScenarios.has(scenarioId) ? "HOLD" : "GO";
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ok: true,
            mode: "single",
            payload: buildAgentPayload("agent5", decision, scenarioId),
            diagnostics: {
              schema_error_detected: false,
              label_mismatch_detected: false,
            },
          }),
        };
      }

      if (url.endsWith("/brain/run") && method === "POST") {
        const body = JSON.parse(String(init.body || "{}"));
        const agent4Decision = String(body.agent4_dataset_root || "").includes("HOLD")
          ? "HOLD"
          : "GO";
        const agent5Decision = ["P5V2-003", "P5V2-007", "P5V2-024"].includes(
          body.agent5_scenario_id
        )
          ? "HOLD"
          : "GO";

        return {
          ok: true,
          status: 200,
          json: async () => ({
            ok: true,
            payload: {
              run_id: "brain-test-run",
              status: "success",
              duration_ms: 42,
              stages: {
                agent4: {
                  status: "success",
                  decision: agent4Decision,
                  payload: buildAgentPayload(
                    "agent4",
                    agent4Decision,
                    body.agent4_scenario_id || "APCS-S4-001"
                  ),
                },
                agent5: {
                  status: "success",
                  decision: agent5Decision,
                  payload: buildAgentPayload(
                    "agent5",
                    agent5Decision,
                    body.agent5_scenario_id || "P5V2-001"
                  ),
                },
              },
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

  it("renders the backend-native console with human-readable analyst names", async () => {
    await renderDashboard();

    expect(screen.getByTestId("agent-console")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /release readiness analyst/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /test evidence analyst/i })
    ).toBeInTheDocument();
  });

  it("bootstraps GO status for the default GO dataset", async () => {
    await renderDashboard();

    await waitFor(() => {
      expect(screen.getByTestId("agent-status-agent4").textContent).toMatch(/GO/);
    });
  });

  it("defaults to the LLM report mode for the demo", async () => {
    await renderDashboard();

    expect(screen.getByLabelText(/enable llm report/i)).toBeChecked();
    expect(screen.getByText(/recommended for the demo/i)).toBeInTheDocument();
  });

  it("switching to HOLD documents refreshes the baseline decision", async () => {
    await renderDashboard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /hold documents/i }));

    await waitFor(() => {
      expect(screen.getByTestId("agent-status-agent4").textContent).toMatch(/HOLD/);
    });
  });

  it("renders status summaries for both analysts", async () => {
    await renderDashboard();

    expect(screen.getByTestId("reasons-panel")).toBeInTheDocument();
    expect(screen.getByTestId("signal-table")).toBeInTheDocument();
    expect(screen.getByTestId("signal-summary-agent4")).toBeInTheDocument();
    expect(screen.getByTestId("signal-summary-agent5")).toBeInTheDocument();
  });

  it("lets you switch current result with arrow controls", async () => {
    await renderDashboard();
    const user = userEvent.setup();

    expect(screen.getByTestId("current-result-analyst-name")).toHaveTextContent(
      /release readiness analyst/i
    );

    await user.click(screen.getByRole("button", { name: /show next analyst result/i }));

    expect(screen.getByTestId("current-result-analyst-name")).toHaveTextContent(
      /test evidence analyst/i
    );
  });

  it("creates and deletes a custom set", async () => {
    await renderDashboard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /upload document dataset/i }));

    await user.type(screen.getByLabelText(/dataset name/i), "My Custom Dataset");

    const fileInput = screen.getByLabelText(/upload documents/i);
    const file = new File(
      ["Subject: Test\nResult: PASS\nNo blocking issues remain."],
      "custom.txt",
      { type: "text/plain" }
    );
    await user.upload(fileInput, file);

    expect(screen.getByText(/1 file\(s\) selected/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /save dataset/i }));

    expect(
      await screen.findByRole("button", { name: /my custom dataset/i })
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /delete selected dataset/i })
    );

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /my custom dataset/i })
      ).not.toBeInTheDocument();
    });
  });

  it("runs the full workflow through the brain endpoint", async () => {
    await renderDashboard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /run full workflow/i }));

    expect(await screen.findByText(/^Last orchestration$/i)).toBeInTheDocument();
    expect(screen.getByText(/status:/i)).toBeInTheDocument();
  });
});
