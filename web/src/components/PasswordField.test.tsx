import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PasswordField } from "./PasswordField";

describe("PasswordField", () => {
  it("renders as password input by default", () => {
    render(<PasswordField data-testid="pw" />);
    const input = screen.getByTestId("pw");
    expect(input).toHaveAttribute("type", "password");
  });

  it("toggles to text when visibility button is clicked", () => {
    render(<PasswordField data-testid="pw" />);
    const input = screen.getByTestId("pw");
    const toggle = screen.getByRole("button", { name: "Show password" });

    fireEvent.click(toggle);
    expect(input).toHaveAttribute("type", "text");
    expect(
      screen.getByRole("button", { name: "Hide password" }),
    ).toBeInTheDocument();
  });

  it("toggles back to password on second click", () => {
    render(<PasswordField data-testid="pw" />);
    const input = screen.getByTestId("pw");
    const toggle = screen.getByRole("button", { name: "Show password" });

    fireEvent.click(toggle);
    expect(input).toHaveAttribute("type", "text");

    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(input).toHaveAttribute("type", "password");
  });

  it("has aria-pressed=false by default and true when visible", () => {
    render(<PasswordField data-testid="pw" />);
    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(toggle);
    expect(
      screen.getByRole("button", { name: "Hide password" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("uses type=button so it does not submit forms", () => {
    render(<PasswordField data-testid="pw" />);
    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toHaveAttribute("type", "button");
  });

  it("prevents default on pointerdown to preserve input focus", () => {
    render(<PasswordField data-testid="pw" />);
    const toggle = screen.getByRole("button", { name: "Show password" });
    const event = new MouseEvent("pointerdown", {
      bubbles: true,
      cancelable: true,
    });
    const prevented = !toggle.dispatchEvent(event);
    expect(prevented).toBe(true);
  });

  it("renders a label when provided", () => {
    render(<PasswordField label="Secret" data-testid="pw" />);
    expect(screen.getByLabelText("Secret")).toBeInTheDocument();
  });

  it("sets spellCheck to false", () => {
    render(<PasswordField data-testid="pw" />);
    const input = screen.getByTestId("pw");
    expect(input).toHaveAttribute("spellCheck", "false");
  });

  it("sets aria-invalid and aria-describedby when error is present", () => {
    render(<PasswordField data-testid="pw" id="test" error="bad password" />);
    const input = screen.getByTestId("pw");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", "test-error");
    expect(screen.getByText("bad password")).toBeInTheDocument();
  });

  it("disables the toggle button when input is disabled", () => {
    render(<PasswordField data-testid="pw" disabled />);
    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toBeDisabled();
  });
});
