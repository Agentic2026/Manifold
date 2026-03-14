import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useAuth } from "../auth";
import { Button } from "../components/Button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "../components/Card";
import { Alert } from "../components/Alert";
import { Fingerprint, Loader2 } from "lucide-react";

export function Login() {
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { loginPasskey } = useAuth();
  const navigate = useNavigate();

  const handlePasskeyLogin = async () => {
    setError(null);
    setIsLoading(true);
    try {
      await loginPasskey();
      navigate("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Passkey login failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md shadow-lg border-primary/10">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-bold tracking-tight">
            Welcome back
          </CardTitle>
          <CardDescription>Login to your account</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          {error && (
            <Alert variant="error" data-testid="login-error">
              {error}
            </Alert>
          )}

          <Button
            onClick={handlePasskeyLogin}
            disabled={isLoading}
            className="w-full h-12 text-base font-semibold"
            size="lg"
            data-testid="login-submit"
          >
            {isLoading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Fingerprint className="mr-2 h-5 w-5" />
            )}
            Sign in with Passkey
          </Button>
        </CardContent>
        <CardFooter className="flex flex-col gap-4 text-center pb-8">
          <div className="text-sm text-text-muted">
            Don't have an account?{" "}
            <Link
              to="/register"
              className="font-medium text-primary underline-offset-4 hover:underline transition-colors"
            >
              Sign up
            </Link>
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}
