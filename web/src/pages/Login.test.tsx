import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Login } from "./Login";

// Mock auth context
vi.mock("../auth", () => ({
  useAuth: () => ({
    loginPasskey: vi.fn(),
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
  it("renders a passkey sign-in button", () => {
    render(<Login />);
    expect(screen.getByTestId("login-submit")).toBeInTheDocument();
    expect(screen.getByText("Sign in with Passkey")).toBeInTheDocument();
  });

  it("does not render email or password inputs", () => {
    render(<Login />);
    expect(screen.queryByTestId("login-email-input")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("login-password-input"),
    ).not.toBeInTheDocument();
  });

  it("does not have a password submit button", () => {
    render(<Login />);
    expect(
      screen.queryByTestId("login-password-btn"),
    ).not.toBeInTheDocument();
  });

  it("links to the register page", () => {
    render(<Login />);
    const link = screen.getByText("Sign up");
    expect(link).toHaveAttribute("href", "/register");
  });
});
