import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import ReleaseDashboard from "./ReleaseDashboard.jsx";

describe("Release Dashboard", () => {
  let backendSets;

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
          id: `SET_CUSTOM_${String(body.label || "set").toLowerCase().replace(/[^a-z0-9]+/g, "_")}`,
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

  it("renders agent operations console", () => {
    render(<ReleaseDashboard />);
    expect(screen.getByTestId("agent-console")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /agent operations console/i })).toBeInTheDocument();
  });

  it("defaults to GO for Agent 4 with GO documents", () => {
    render(<ReleaseDashboard />);
    expect(screen.getByTestId("agent-status-agent4").textContent).toMatch(/GO/);
  });

  it("switching to HOLD documents yields HOLD decision", async () => {
    render(<ReleaseDashboard />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /hold documents/i }));
    expect(screen.getByTestId("agent-status-agent4").textContent).toMatch(/HOLD/);
  });

  it("renders separate signal summaries for both agents", async () => {
    render(<ReleaseDashboard />);

    expect(screen.getByTestId("reasons-panel")).toBeInTheDocument();
    expect(screen.getByTestId("signal-table")).toBeInTheDocument();
    expect(screen.getByTestId("signal-summary-agent4")).toBeInTheDocument();
    expect(screen.getByTestId("signal-summary-agent5")).toBeInTheDocument();
    expect(screen.getByTestId("agent-status-agent4")).toBeInTheDocument();
    expect(screen.getByTestId("agent-status-agent5")).toBeInTheDocument();
  });

  it("creates a custom set from uploaded documents", async () => {
    render(<ReleaseDashboard />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/set name/i), "My Custom Set");

    const fileInput = screen.getByLabelText(/upload documents/i);
    const file = new File(
      ["Subject: Test\nResult: PASS\nNo blocking issues remain."],
      "custom.txt",
      { type: "text/plain" }
    );
    await user.upload(fileInput, file);

    expect(screen.getByText(/1 file\(s\) selected/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /save set/i }));

    expect(
      await screen.findByRole("button", { name: /my custom set/i })
    ).toBeInTheDocument();
  });

  it("deletes the selected custom set", async () => {
    render(<ReleaseDashboard />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/set name/i), "Disposable Set");
    const fileInput = screen.getByLabelText(/upload documents/i);
    const file = new File(["Result: PASS"], "temp.txt", { type: "text/plain" });
    await user.upload(fileInput, file);
    await user.click(screen.getByRole("button", { name: /save set/i }));

    expect(
      await screen.findByRole("button", { name: /disposable set/i })
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /delete selected set/i })
    );

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /disposable set/i })
      ).not.toBeInTheDocument();
    });
  });
});
