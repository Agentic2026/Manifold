/**
 * Canonical API base URL for all frontend → backend requests.
 *
 * Resolution order:
 *  1. VITE_API_BASE_URL env var (set at build time or via .env)
 *  2. "/api" — the path the reverse proxy exposes in production
 *
 * Trailing slashes are stripped so callers can safely write
 *   `${API_BASE}/some/path` without producing double slashes.
 */
export const API_BASE = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "/api"
).replace(/\/+$/, "");
