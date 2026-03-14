import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Fingerprint,
  Plus,
  Trash2,
  AlertCircle,
  Pencil,
  Check,
  X,
  Loader2,
  Monitor,
  Moon,
  Sun,
  Shield,
} from "lucide-react";
import { apiFetch } from "../auth";
import { toCreateOptions, serializeCreateResponse } from "../auth/webauthn";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/Card";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { Input } from "../components/Input";
import { Badge } from "../components/Badge";
import api from "../api/client";
import type { PasskeyInfo } from "../api/types";
import {
  applyThemePreference,
  readThemePreference,
  type ThemePreference,
} from "../theme";
import { cn } from "../lib/utils";

const MAX_NAME_LENGTH = 64;

function PasskeyName({
  passkey,
  onRenamed,
}: {
  passkey: PasskeyInfo;
  onRenamed: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(passkey.name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = () => {
    setDraft(passkey.name ?? "");
    setError(null);
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    setError(null);
  };

  const save = async () => {
    const trimmed = draft.trim();
    if (trimmed.length > MAX_NAME_LENGTH) {
      setError(`Name must be ${MAX_NAME_LENGTH} characters or fewer`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await apiFetch(`/auth/passkeys/${passkey.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: trimmed || null }),
      });
      if (!res.ok) {
        const data = res.data as { detail?: string };
        throw new Error(data.detail ?? "Rename failed");
      }
      setEditing(false);
      onRenamed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <div className="flex flex-col gap-2" data-testid="passkey-rename-form">
        <div className="flex items-center gap-2">
          <Input
            data-testid="passkey-name-input"
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={MAX_NAME_LENGTH}
            className="h-8 w-48"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") cancel();
            }}
          />
          <Button
            size="icon"
            variant="ghost"
            data-testid="passkey-name-save"
            onClick={save}
            disabled={saving}
            className="h-8 w-8 text-success hover:text-success hover:bg-success/10"
            aria-label="Save name"
          >
            <Check className="w-4 h-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            data-testid="passkey-name-cancel"
            onClick={cancel}
            className="h-8 w-8 text-text-muted hover:text-text"
            aria-label="Cancel rename"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
        {error && (
          <span
            className="text-xs text-danger block"
            data-testid="passkey-rename-error"
          >
            {error}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 group">
      <span className="font-medium" data-testid="passkey-name">
        {passkey.name || "Unnamed passkey"}
      </span>
      {!passkey.revoked_at && (
        <Button
          size="icon"
          variant="ghost"
          data-testid="passkey-edit-btn"
          onClick={startEdit}
          className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
          aria-label="Edit passkey name"
        >
          <Pencil className="w-3 h-3" />
        </Button>
      )}
    </div>
  );
}

export function Settings() {
  const queryClient = useQueryClient();
  const [addLoading, setAddLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastPasskeyError, setLastPasskeyError] = useState<string | null>(null);
  const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
    readThemePreference(),
  );

  const { data: passkeys, isLoading } = useQuery<PasskeyInfo[]>({
    queryKey: ["passkeys"],
    queryFn: async () => {
      const { data, error } = await api.GET("/auth/passkeys");
      if (error) throw new Error("Failed to load passkeys");
      return data.passkeys;
    },
  });

  const revokeMutation = useMutation({
    mutationFn: async (passkeyId: string) => {
      setLastPasskeyError(null);
      const res = await apiFetch(`/auth/passkeys/${passkeyId}/revoke`, {
        method: "POST",
      });
      if (!res.ok) {
        const data = res.data as {
          error?: string;
          detail?: string | { code?: string; message?: string };
        };
        const detail = data.detail;
        if (
          data.error === "LAST_PASSKEY" ||
          (typeof detail === "string" && detail.includes("LAST_PASSKEY")) ||
          (typeof detail === "object" && detail?.code === "LAST_PASSKEY")
        ) {
          throw new Error("LAST_PASSKEY");
        }
        const msg =
          typeof detail === "string"
            ? detail
            : (detail as { message?: string })?.message || "Revoke failed";
        throw new Error(msg);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["passkeys"] });
    },
    onError: (err: Error) => {
      if (err.message === "LAST_PASSKEY") {
        setLastPasskeyError(
          "Cannot revoke your last active passkey. Add another passkey first to maintain account access.",
        );
      } else {
        setError(err.message);
      }
    },
  });

  const handleAddPasskey = async () => {
    setAddLoading(true);
    setError(null);
    try {
      const startRes = await apiFetch<{
        options: Record<string, unknown>;
        flow_id: string;
      }>("/auth/passkey/add/start", { method: "POST" });
      if (!startRes.ok) throw new Error("Failed to start passkey addition");

      const createOptions = toCreateOptions(
        startRes.data.options as unknown as Parameters<
          typeof toCreateOptions
        >[0],
      );
      const credential = (await navigator.credentials.create(
        createOptions,
      )) as PublicKeyCredential | null;
      if (!credential) throw new Error("Passkey creation cancelled");

      const finishRes = await apiFetch("/auth/passkey/add/finish", {
        method: "POST",
        body: JSON.stringify({
          flow_id: startRes.data.flow_id,
          credential: serializeCreateResponse(credential),
        }),
      });
      if (!finishRes.ok) throw new Error("Failed to add passkey");

      queryClient.invalidateQueries({ queryKey: ["passkeys"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add passkey");
    } finally {
      setAddLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-text-muted mt-2">
          Manage your account settings and preferences.
        </p>
      </div>

      {error && (
        <Alert variant="error" data-testid="settings-error">
          {error}
        </Alert>
      )}
      {lastPasskeyError && (
        <Alert variant="warning" data-testid="last-passkey-error">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{lastPasskeyError}</span>
          </div>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>
            Customize how the application looks properly.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4 max-w-lg">
            {(["light", "dark", "system"] as const).map((option) => (
              <label
                key={option}
                className={cn(
                  "cursor-pointer rounded-xl border-2 p-4 hover:bg-surface-alt transition-all",
                  themePreference === option
                    ? "border-primary bg-primary/5"
                    : "border-border",
                )}
              >
                <input
                  type="radio"
                  name="theme-preference"
                  value={option}
                  checked={themePreference === option}
                  onChange={() => {
                    setThemePreference(option);
                    applyThemePreference(option);
                  }}
                  className="sr-only"
                />
                <div className="flex flex-col items-center gap-2">
                  {option === "light" && <Sun className="w-6 h-6" />}
                  {option === "dark" && <Moon className="w-6 h-6" />}
                  {option === "system" && <Monitor className="w-6 h-6" />}
                  <span className="text-sm font-medium capitalize">
                    {option}
                  </span>
                </div>
              </label>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div className="space-y-1">
            <CardTitle>Security</CardTitle>
            <CardDescription>
              Manage your passkeys and access methods.
            </CardDescription>
          </div>
          <Button
            onClick={handleAddPasskey}
            disabled={addLoading}
            data-testid="add-passkey-btn"
          >
            {addLoading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Plus className="mr-2 h-4 w-4" />
            )}
            Add Passkey
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : passkeys && passkeys.length > 0 ? (
            <div className="space-y-4">
              {passkeys.map((passkey) => (
                <div
                  key={passkey.id}
                  className="flex items-center justify-between p-4 rounded-xl border border-border bg-surface-alt/30"
                  data-testid="passkey-item"
                >
                  <div className="flex items-center gap-4">
                    <div className="p-2 bg-surface rounded-lg border border-border">
                      <Fingerprint className="w-6 h-6 text-primary" />
                    </div>
                    <div>
                      <PasskeyName
                        passkey={passkey}
                        onRenamed={() =>
                          queryClient.invalidateQueries({
                            queryKey: ["passkeys"],
                          })
                        }
                      />
                      <div className="flex items-center gap-2 text-xs text-text-muted mt-1">
                        <span className="font-mono">
                          {passkey.id.slice(0, 8)}...
                        </span>
                        <span>•</span>
                        <span>
                          Created{" "}
                          {new Date(passkey.created_at).toLocaleDateString()}
                        </span>
                        {passkey.revoked_at && (
                          <Badge variant="destructive" className="ml-2">
                            Revoked
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  {!passkey.revoked_at && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-danger hover:text-danger hover:bg-danger/10"
                      onClick={() => revokeMutation.mutate(passkey.id)}
                      disabled={revokeMutation.isPending}
                      data-testid="revoke-passkey-btn"
                    >
                      <Trash2 className="w-4 h-4 mr-2" />
                      Revoke
                    </Button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 border border-dashed border-border rounded-xl">
              <Shield className="w-12 h-12 text-text-muted mx-auto mb-4" />
              <h3 className="text-lg font-medium">No passkeys found</h3>
              <p className="text-text-muted max-w-sm mx-auto mt-2">
                Add a passkey to enable secure, passwordless authentication for
                your account.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
