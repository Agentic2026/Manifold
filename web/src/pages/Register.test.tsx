import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Register } from "./Register";

// Mock auth context
vi.mock("../auth", () => ({
  useAuth: () => ({
    registerPasskey: vi.fn(),
  }),
}));

// Mock react-router navigate
vi.mock("react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({
    children,
    to,
    ...rest
  }: {
    children: React.ReactNode;
    to: string;
    className?: string;
  }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

describe("Register page", () => {
  it("renders Display Name label", () => {
    render(<Register />);
    expect(screen.getByLabelText("Display Name")).toBeInTheDocument();
    expect(screen.queryByLabelText("Username")).not.toBeInTheDocument();
  });

  it("has display name input with correct testid", () => {
    render(<Register />);
    const input = screen.getByTestId("register-display-name");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("type", "text");
  });

  it("enforces maxLength on display name input", () => {
    render(<Register />);
    const input = screen.getByTestId("register-display-name");
    expect(input).toHaveAttribute("maxLength", "200");
  });

  it("uses name autocomplete for display name", () => {
    render(<Register />);
    const input = screen.getByTestId("register-display-name");
    expect(input).toHaveAttribute("autoComplete", "name");
  });

  it("renders a passkey register button", () => {
    render(<Register />);
    expect(screen.getByTestId("register-submit")).toBeInTheDocument();
    expect(screen.getByText("Register with Passkey")).toBeInTheDocument();
  });

  it("does not render email or password inputs", () => {
    render(<Register />);
    expect(
      screen.queryByTestId("register-email-input"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("register-password-input"),
    ).not.toBeInTheDocument();
  });

  it("does not have a password submit button", () => {
    render(<Register />);
    expect(
      screen.queryByTestId("register-password-btn"),
    ).not.toBeInTheDocument();
  });
});
