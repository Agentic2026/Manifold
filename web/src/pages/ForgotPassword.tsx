import { useState } from "react";
import { Link } from "react-router";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
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

type PasswordResetRequestBody =
  components["schemas"]["PasswordResetRequestSchema"];
type MessageResponse = components["schemas"]["MessageResponse"];

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedEmail = email.trim();
    if (!trimmedEmail) return;

    setError(null);
    setIsLoading(true);
    try {
      const body: PasswordResetRequestBody = { email: trimmedEmail };
      const res = await publicFetch<MessageResponse>(
        "/auth/password-reset/request",
        {
          method: "POST",
          body: JSON.stringify(body),
        },
      );
      if (!res.ok) {
        throw new Error("Request failed");
      }
      setSubmitted(true);
    } catch {
      // Show a generic success-like message to avoid leaking account existence.
      // The backend already returns the same response regardless, but we handle
      // network errors gracefully too.
      setSubmitted(true);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md shadow-lg border-primary/10">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-bold tracking-tight">
            Reset your password
          </CardTitle>
          <CardDescription>
            Enter your email and we'll send you a reset link
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          {error && (
            <Alert variant="error" data-testid="forgot-error">
              {error}
            </Alert>
          )}

          {submitted ? (
            <Alert variant="success" data-testid="forgot-success">
              If an account exists for that email, a password reset link has been
              sent. Please check your inbox.
            </Alert>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="space-y-4"
              data-testid="forgot-form"
            >
              <Input
                id="email"
                label="Email"
                type="email"
                placeholder="m@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
                data-testid="forgot-email-input"
                autoComplete="email"
                autoCapitalize="none"
                autoFocus
              />
              <Button
                type="submit"
                disabled={isLoading || !email.trim()}
                className="w-full"
                data-testid="forgot-submit"
              >
                {isLoading && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Send Reset Link
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
