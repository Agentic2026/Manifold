import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ForgotPassword } from "./ForgotPassword";

// Mock auth api
const mockPublicFetch = vi.fn();
vi.mock("../auth/api", () => ({
  publicFetch: (...args: unknown[]) => mockPublicFetch(...args),
}));

// Mock react-router
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

describe("ForgotPassword page", () => {
  beforeEach(() => {
    mockPublicFetch.mockReset();
  });

  it("renders the forgot password form", () => {
    render(<ForgotPassword />);
    expect(screen.getByText("Reset your password")).toBeInTheDocument();
    expect(screen.getByTestId("forgot-email-input")).toBeInTheDocument();
    expect(screen.getByTestId("forgot-submit")).toBeInTheDocument();
  });

  it("has an email input with correct attributes", () => {
    render(<ForgotPassword />);
    const input = screen.getByTestId("forgot-email-input");
    expect(input).toHaveAttribute("type", "email");
    expect(input).toHaveAttribute("autoComplete", "email");
  });

  it("shows success message after submission", async () => {
    mockPublicFetch.mockResolvedValue({
      ok: true,
      status: 200,
      data: { message: "ok" },
    });

    render(<ForgotPassword />);
    const input = screen.getByTestId("forgot-email-input");
    fireEvent.change(input, { target: { value: "test@example.com" } });
    fireEvent.click(screen.getByTestId("forgot-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("forgot-success")).toBeInTheDocument();
    });
  });

  it("calls the password-reset/request endpoint with trimmed email", async () => {
    mockPublicFetch.mockResolvedValue({
      ok: true,
      status: 200,
      data: { message: "ok" },
    });

    render(<ForgotPassword />);
    const input = screen.getByTestId("forgot-email-input");
    fireEvent.change(input, { target: { value: "  test@example.com  " } });
    fireEvent.click(screen.getByTestId("forgot-submit"));

    await waitFor(() => {
      expect(mockPublicFetch).toHaveBeenCalledWith(
        "/auth/password-reset/request",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ email: "test@example.com" }),
        }),
      );
    });
  });

  it("does not leak account existence on network error", async () => {
    mockPublicFetch.mockRejectedValue(new Error("Network error"));

    render(<ForgotPassword />);
    const input = screen.getByTestId("forgot-email-input");
    fireEvent.change(input, { target: { value: "nobody@example.com" } });
    fireEvent.click(screen.getByTestId("forgot-submit"));

    await waitFor(() => {
      // Should still show success, not error
      expect(screen.getByTestId("forgot-success")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("forgot-error")).not.toBeInTheDocument();
  });

  it("links back to the login page", () => {
    render(<ForgotPassword />);
    const link = screen.getByText("Sign in");
    expect(link).toHaveAttribute("href", "/login");
  });
});
