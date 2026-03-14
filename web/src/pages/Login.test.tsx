import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Login } from "./Login";

// Mock auth context
vi.mock("../auth", () => ({
  useAuth: () => ({
    loginPasskey: vi.fn(),
    loginPassword: vi.fn(),
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

describe("Login page", () => {
  it("renders Email label instead of Username", () => {
    render(<Login />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.queryByLabelText("Username")).not.toBeInTheDocument();
  });

  it("has email input with correct type and testid", () => {
    render(<Login />);
    const input = screen.getByTestId("login-email-input");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("type", "email");
  });

  it("uses email autocomplete for the email field", () => {
    render(<Login />);
    const input = screen.getByTestId("login-email-input");
    expect(input).toHaveAttribute("autoComplete", "email");
  });

  it("does not have a username input", () => {
    render(<Login />);
    expect(screen.queryByTestId("login-username-input")).not.toBeInTheDocument();
  });

  it("uses the shared PasswordField component for the password input", () => {
    render(<Login />);
    const input = screen.getByTestId("login-password-input");
    expect(input).toHaveAttribute("type", "password");
    // The PasswordField renders a visibility toggle button
    expect(
      screen.getByRole("button", { name: "Show password" }),
    ).toBeInTheDocument();
  });

  it("has distinct passkey and password submit elements", () => {
    render(<Login />);
    expect(screen.getByTestId("login-submit")).toBeInTheDocument();
    expect(screen.getByTestId("login-password-btn")).toBeInTheDocument();
  });

  it("links to the forgot-password page", () => {
    render(<Login />);
    const link = screen.getByText("Forgot password?");
    expect(link).toHaveAttribute("href", "/forgot-password");
  });
});
