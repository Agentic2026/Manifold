import { useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router";
import { Button } from "../components/Button";
import { PasswordField } from "../components/PasswordField";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "../components/Card";
import { Alert } from "../components/Alert";
import { publicFetch } from "../auth/api";
import type { components } from "../api/openapi";
import { Loader2 } from "lucide-react";

type PasswordResetConfirmBody =
  components["schemas"]["PasswordResetConfirmSchema"];

export function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();

  const [newPassword, setNewPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !newPassword) return;

    setError(null);
    setIsLoading(true);
    try {
      const body: PasswordResetConfirmBody = {
        token,
        new_password: newPassword,
      };
      const res = await publicFetch("/auth/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = res.data as { detail?: string } | null;
        throw new Error(
          (data && typeof data.detail === "string" && data.detail) ||
            "Reset failed. The link may have expired.",
        );
      }
      setSuccess(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Reset failed. The link may have expired.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
        <Card className="w-full max-w-md shadow-lg border-primary/10">
          <CardContent className="py-8">
            <Alert variant="error" data-testid="reset-missing-token">
              Invalid or missing reset link. Please request a new password reset.
            </Alert>
            <div className="mt-4 text-center">
              <Link
                to="/forgot-password"
                className="font-medium text-primary underline-offset-4 hover:underline transition-colors text-sm"
              >
                Request a new reset link
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md shadow-lg border-primary/10">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-bold tracking-tight">
            Set a new password
          </CardTitle>
          <CardDescription>
            Enter your new password below to reset your account
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          {error && (
            <Alert variant="error" data-testid="reset-error">
              {error}
            </Alert>
          )}

          {success ? (
            <>
              <Alert variant="success" data-testid="reset-success">
                Your password has been reset successfully.
              </Alert>
              <Button
                className="w-full"
                onClick={() => navigate("/login")}
                data-testid="reset-login-btn"
              >
                Sign in
              </Button>
            </>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="space-y-4"
              data-testid="reset-form"
            >
              <PasswordField
                id="new-password"
                label="New Password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                disabled={isLoading}
                data-testid="reset-password-input"
                autoComplete="new-password"
                autoFocus
              />
              <Button
                type="submit"
                disabled={isLoading || !newPassword}
                className="w-full"
                data-testid="reset-submit"
              >
                {isLoading && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Reset Password
              </Button>
            </form>
          )}
        </CardContent>
        <CardFooter className="flex flex-col gap-4 text-center pb-8">
          <div className="text-sm text-text-muted">
            Remember your password?{" "}
            <Link
              to="/login"
              className="font-medium text-primary underline-offset-4 hover:underline transition-colors"
            >
              Sign in
            </Link>
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}
