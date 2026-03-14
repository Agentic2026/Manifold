import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useAuth } from "../auth";
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
import { Fingerprint, Loader2 } from "lucide-react";

const DISPLAY_NAME_MAX_LENGTH = 200;

export function Register() {
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { registerPasskey } = useAuth();
  const navigate = useNavigate();

  const handlePasskeyRegister = async () => {
    const trimmedName = displayName.trim();
    if (!trimmedName) return;
    setError(null);
    setIsLoading(true);
    try {
      await registerPasskey(trimmedName);
      navigate("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Passkey registration failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md shadow-lg border-primary/10">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-bold tracking-tight">
            Create an account
          </CardTitle>
          <CardDescription>
            Enter your name and register with a passkey
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          {error && (
            <Alert variant="error" data-testid="register-error">
              {error}
            </Alert>
          )}

          <div className="space-y-4">
            <Input
              id="displayName"
              label="Display Name"
              type="text"
              placeholder="Jane Doe"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              disabled={isLoading}
              data-testid="register-display-name"
              autoComplete="name"
              maxLength={DISPLAY_NAME_MAX_LENGTH}
              autoFocus
            />

            <Button
              onClick={handlePasskeyRegister}
              disabled={isLoading || !displayName.trim()}
              className="w-full h-12 text-base font-semibold"
              size="lg"
              data-testid="register-submit"
            >
              {isLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Fingerprint className="mr-2 h-5 w-5" />
              )}
              Register with Passkey
            </Button>
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-4 text-center pb-8">
          <div className="text-sm text-text-muted">
            Already have an account?{" "}
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
