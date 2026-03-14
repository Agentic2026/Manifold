import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ResetPassword } from "./ResetPassword";

// Mock auth api
const mockPublicFetch = vi.fn();
vi.mock("../auth/api", () => ({
  publicFetch: (...args: unknown[]) => mockPublicFetch(...args),
}));

// Mock react-router with useSearchParams support
const mockSearchParams = new URLSearchParams();
const mockNavigate = vi.fn();
vi.mock("react-router", () => ({
  useNavigate: () => mockNavigate,
  useSearchParams: () => [mockSearchParams],
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

describe("ResetPassword page", () => {
  beforeEach(() => {
    mockPublicFetch.mockReset();
    mockNavigate.mockReset();
    // Clear any previous params
    mockSearchParams.delete("token");
  });

  it("shows missing-token error when no token is present", () => {
    render(<ResetPassword />);
    expect(screen.getByTestId("reset-missing-token")).toBeInTheDocument();
    expect(
      screen.getByText("Request a new reset link"),
    ).toBeInTheDocument();
  });

  it("renders the reset form when a token is in query params", () => {
    mockSearchParams.set("token", "abc123");
    render(<ResetPassword />);
    expect(screen.getByText("Set a new password")).toBeInTheDocument();
    expect(screen.getByTestId("reset-password-input")).toBeInTheDocument();
    expect(screen.getByTestId("reset-submit")).toBeInTheDocument();
  });

  it("uses the shared PasswordField for new password entry", () => {
    mockSearchParams.set("token", "abc123");
    render(<ResetPassword />);
    const input = screen.getByTestId("reset-password-input");
    expect(input).toHaveAttribute("type", "password");
    expect(
      screen.getByRole("button", { name: "Show password" }),
    ).toBeInTheDocument();
  });

  it("submits with the correct token and password", async () => {
    mockSearchParams.set("token", "abc123");
    mockPublicFetch.mockResolvedValue({
      ok: true,
      status: 200,
      data: { user_id: "u1", device_id: "d1", role: "user" },
    });

    render(<ResetPassword />);
    const input = screen.getByTestId("reset-password-input");
    fireEvent.change(input, { target: { value: "newPassword123" } });
    fireEvent.click(screen.getByTestId("reset-submit"));

    await waitFor(() => {
      expect(mockPublicFetch).toHaveBeenCalledWith(
        "/auth/password-reset/confirm",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            token: "abc123",
            new_password: "newPassword123",
          }),
        }),
      );
    });
  });

  it("shows success message after successful reset", async () => {
    mockSearchParams.set("token", "abc123");
    mockPublicFetch.mockResolvedValue({
      ok: true,
      status: 200,
      data: { user_id: "u1", device_id: "d1", role: "user" },
    });

    render(<ResetPassword />);
    const input = screen.getByTestId("reset-password-input");
    fireEvent.change(input, { target: { value: "newPassword123" } });
    fireEvent.click(screen.getByTestId("reset-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("reset-success")).toBeInTheDocument();
    });

    // Should show a sign-in button after success
    expect(screen.getByTestId("reset-login-btn")).toBeInTheDocument();
  });

  it("shows error message on failed reset", async () => {
    mockSearchParams.set("token", "expired-token");
    mockPublicFetch.mockResolvedValue({
      ok: false,
      status: 400,
      data: { detail: "Token expired" },
    });

    render(<ResetPassword />);
    const input = screen.getByTestId("reset-password-input");
    fireEvent.change(input, { target: { value: "newPassword123" } });
    fireEvent.click(screen.getByTestId("reset-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("reset-error")).toBeInTheDocument();
      expect(screen.getByText("Token expired")).toBeInTheDocument();
    });
  });
});
