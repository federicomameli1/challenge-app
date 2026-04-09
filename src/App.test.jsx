import { render, screen } from "@testing-library/react";
import App from "./App.jsx";

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
    screen.getByRole("heading", { name: /agent operations console/i })
  ).toBeInTheDocument();
});
