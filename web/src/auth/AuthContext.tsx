import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import {
  ensureDeviceKeyMaterial,
  getDeviceIdentity,
  setDeviceIdentity,
  clearDeviceAuthorization,
} from "./deviceKey";
import { clearCachedToken } from "./token";
import { publicFetch } from "./api";
import {
  toCreateOptions,
  toGetOptions,
  serializeCreateResponse,
  serializeGetResponse,
} from "./webauthn";
import { useNavigate } from "react-router";
import type { components } from "../api/openapi";

// ---------------------------------------------------------------------------
// Types derived from the generated OpenAPI schema
// ---------------------------------------------------------------------------

/** Backend auth response shape (passkey finish / add finish). */
type PasskeyFinishResponse = components["schemas"]["PasskeyFinishResponse"];

/** Passkey register start response. */
type PasskeyRegisterStartResponse =
  components["schemas"]["PasskeyRegisterStartResponse"];

/** Passkey login start response. */
type PasskeyLoginStartResponse =
  components["schemas"]["PasskeyLoginStartResponse"];

// ---------------------------------------------------------------------------
// Auth state
// ---------------------------------------------------------------------------

interface User {
  id: string;
  role: string;
  scopes: string[];
}

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  userId: string | null;
  deviceId: string | null;
  role: string | null;
  displayName: string | null;
  user: User | null;
}

interface AuthContextType extends AuthState {
  loginPasskey: () => Promise<void>;
  registerPasskey: (displayName: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

/** Extract display_name from a passkey auth response. */
function extractDisplayName(data: PasskeyFinishResponse): string | null {
  return data.display_name ?? null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    userId: null,
    deviceId: null,
    role: null,
    displayName: null,
    user: null,
  });
  const navigate = useNavigate();

  // Check existing device identity on mount and rehydrate from backend
  useEffect(() => {
    getDeviceIdentity()
      .then(async (identity) => {
        if (!identity) {
          setState((s) => ({ ...s, isLoading: false }));
          return;
        }
        try {
          const { apiFetch } = await import("./api");
          const res = await apiFetch<{
            user_id: string;
            device_id: string;
            role: string;
            scopes: string[];
            display_name: string | null;
            email: string | null;
          }>("/auth/session");
          if (res.ok) {
            setState({
              isAuthenticated: true,
              isLoading: false,
              userId: res.data.user_id,
              deviceId: res.data.device_id,
              role: res.data.role,
              displayName: res.data.display_name,
              user: { id: res.data.user_id, role: res.data.role, scopes: res.data.scopes },
            });
          } else {
            // Stale identity
            clearCachedToken();
            await clearDeviceAuthorization();
            setState((s) => ({ ...s, isLoading: false }));
          }
        } catch {
          // Network error or AuthError - fall back to stored identity
          setState({
            isAuthenticated: true,
            isLoading: false,
            userId: identity.userId,
            deviceId: identity.deviceId,
            role: "user",
            displayName: null,
            user: { id: identity.userId, role: "user", scopes: [] },
          });
        }
      })
      .catch(() => setState((s) => ({ ...s, isLoading: false })));
  }, []);

  const updateState = (
    userId: string,
    deviceId: string,
    role: string = "user",
    displayName: string | null = null,
  ) => {
    setDeviceIdentity(deviceId, userId);
    setState({
      isAuthenticated: true,
      isLoading: false,
      userId,
      deviceId,
      role,
      displayName,
      user: { id: userId, role, scopes: [] },
    });
  };

  const loginPasskey = useCallback(async () => {
    const keyMaterial = await ensureDeviceKeyMaterial();
    const startRes = await publicFetch<PasskeyLoginStartResponse>(
      "/auth/passkey/login/start",
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    );
    if (!startRes.ok) throw new Error("Login start failed");

    const getOptions = toGetOptions(
      startRes.data.options as unknown as Parameters<typeof toGetOptions>[0],
    );
    const credential = (await navigator.credentials.get(
      getOptions,
    )) as PublicKeyCredential | null;
    if (!credential) throw new Error("Login cancelled");

    const finishRes = await publicFetch<PasskeyFinishResponse>(
      "/auth/passkey/login/finish",
      {
        method: "POST",
        body: JSON.stringify({
          flow_id: startRes.data.flow_id,
          credential: serializeGetResponse(credential),
          device_public_key_jwk: keyMaterial.publicJwk,
          device_label: navigator.userAgent.slice(0, 64),
        }),
      },
    );
    if (!finishRes.ok) throw new Error("Login finish failed");

    updateState(
      finishRes.data.user_id,
      finishRes.data.device_id,
      finishRes.data.role,
      extractDisplayName(finishRes.data),
    );
  }, []);



  const registerPasskey = useCallback(async (displayName: string) => {
    const keyMaterial = await ensureDeviceKeyMaterial();
    const startRes = await publicFetch<PasskeyRegisterStartResponse>(
      "/auth/passkey/register/start",
      {
        method: "POST",
        body: JSON.stringify({ display_name: displayName }),
      },
    );
    if (!startRes.ok) throw new Error("Registration start failed");

    const createOptions = toCreateOptions(
      startRes.data.options as unknown as Parameters<
        typeof toCreateOptions
      >[0],
    );
    const credential = (await navigator.credentials.create(
      createOptions,
    )) as PublicKeyCredential | null;
    if (!credential) throw new Error("Credential creation cancelled");

    const finishRes = await publicFetch<PasskeyFinishResponse>(
      "/auth/passkey/register/finish",
      {
        method: "POST",
        body: JSON.stringify({
          flow_id: startRes.data.flow_id,
          credential: serializeCreateResponse(credential),
          device_public_key_jwk: keyMaterial.publicJwk,
          device_label: navigator.userAgent.slice(0, 64),
        }),
      },
    );
    if (!finishRes.ok) throw new Error("Registration finish failed");

    updateState(
      finishRes.data.user_id,
      finishRes.data.device_id,
      finishRes.data.role,
      extractDisplayName(finishRes.data),
    );
  }, []);


  const logout = useCallback(async () => {
    clearCachedToken();
    await clearDeviceAuthorization();
    setState({
      isAuthenticated: false,
      isLoading: false,
      userId: null,
      deviceId: null,
      role: null,
      displayName: null,
      user: null,
    });
    navigate("/");
  }, [navigate]);

  return (
    <AuthContext.Provider
      value={{
        ...state,
        loginPasskey,
        registerPasskey,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
