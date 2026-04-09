import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect } from "vitest";
import ReleaseDashboard from "./ReleaseDashboard.jsx";

describe("Release Dashboard", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders agent operations console", () => {
    render(<ReleaseDashboard />);
    expect(screen.getByTestId("agent-console")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /agent operations console/i })).toBeInTheDocument();
  });

  it("defaults to GO for Agent 4 with GO documents", () => {
    render(<ReleaseDashboard />);
    expect(screen.getByTestId("decision-badge").textContent).toMatch(/GO/);
  });

  it("switching to HOLD documents yields HOLD decision", async () => {
    render(<ReleaseDashboard />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /hold documents/i }));
    expect(screen.getByTestId("decision-badge").textContent).toMatch(/HOLD/);
  });

  it("switching to Agent 5 still renders reasons and signal table", async () => {
    render(<ReleaseDashboard />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /agent 5/i }));

    expect(screen.getByTestId("reasons-panel")).toBeInTheDocument();
    expect(screen.getByTestId("signal-table")).toBeInTheDocument();
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

    expect(
      screen.queryByRole("button", { name: /disposable set/i })
    ).not.toBeInTheDocument();
  });
});
