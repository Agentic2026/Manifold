import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Register } from "./Register";

// Mock auth context
vi.mock("../auth", () => ({
  useAuth: () => ({
    registerPasskey: vi.fn(),
    registerPassword: vi.fn(),
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
  it("renders Display Name label instead of Username", () => {
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

  it("has email input for password registration", () => {
    render(<Register />);
    const input = screen.getByTestId("register-email-input");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("type", "email");
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

  it("uses the shared PasswordField component for the password input", () => {
    render(<Register />);
    const input = screen.getByTestId("register-password-input");
    expect(input).toHaveAttribute("type", "password");
    expect(
      screen.getByRole("button", { name: "Show password" }),
    ).toBeInTheDocument();
  });

  it("has distinct passkey and password submit elements", () => {
    render(<Register />);
    expect(screen.getByTestId("register-submit")).toBeInTheDocument();
    expect(screen.getByTestId("register-password-btn")).toBeInTheDocument();
  });
});
