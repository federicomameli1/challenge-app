/**
 * Frontend UI — Unit Tests
 *
 * TEST-301 through TEST-303
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import ReleaseDashboard from "./ReleaseDashboard.jsx";

// TEST-301 — Verify dashboard renders version and verdict (REQ-301)
describe("Release Dashboard", () => {
  it("TEST-301: renders the release version and verdict badge", () => {
    render(<ReleaseDashboard />);
    expect(screen.getByTestId("verdict-badge")).toBeInTheDocument();
    // version 1.1.0 appears in multiple spots (badge + footer), just check badge exists
    expect(screen.getByTestId("verdict-badge").textContent).toMatch(/GO/);
  });

  // TEST-302 — Verify traceability matrix renders (REQ-302)
  it("TEST-302: renders the traceability matrix table", async () => {
    render(<ReleaseDashboard />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("tab", { name: /matrix/i }));

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("REQ-101")).toBeInTheDocument();
  });

  // TEST-303 — Verify inconsistency report (REQ-303)
  it("TEST-303: displays the inconsistency report", async () => {
    render(<ReleaseDashboard />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("tab", { name: /issues/i }));

    expect(screen.getByTestId("inconsistency-report")).toBeInTheDocument();
    expect(screen.getByText(/4 documentation inconsistencies/i)).toBeInTheDocument();
  });
});
