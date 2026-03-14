/**
 * Compile-time type assertions for generated OpenAPI types.
 *
 * If the backend schema drifts (routes removed, shapes changed) these
 * assertions will cause a TypeScript compilation error, catching drift
 * before it reaches production.
 *
 * These types are also re-exported for use in app code.
 */

import type { components, paths } from "./openapi";

// ── Library-supplied types ────────────────────────────────────────────────

/** Response body for GET /auth/passkeys */
export type PasskeyListResponse = components["schemas"]["PasskeyListResponse"];

/** Single passkey info object */
export type PasskeyInfo = components["schemas"]["PasskeyInfo"];

/** Response body for PATCH /auth/passkeys/{key_id} */
export type PasskeyRenameResponse =
  components["schemas"]["PasskeyRenameResponse"];

/** Response body for POST /auth/passkey/register/finish (and login/finish) */
export type PasskeyFinishResponse =
  components["schemas"]["PasskeyFinishResponse"];

/** Response body for POST /auth/register and /auth/login */
export type DeviceBindingResponse =
  components["schemas"]["DeviceBindingResponse"];

/** Request body for POST /auth/register */
export type RegisterRequest = components["schemas"]["RegisterRequest"];

/** Request body for POST /auth/login */
export type LoginRequest = components["schemas"]["LoginRequest"];

// ── User-defined (demo) types ─────────────────────────────────────────────

/** Response body for GET /demo/ping */
export type PingResponse = components["schemas"]["PingResponse"];

/** Request body for POST /demo/echo */
export type EchoRequest = components["schemas"]["EchoRequest"];

/** Response body for POST /demo/echo */
export type EchoResponse = components["schemas"]["EchoResponse"];

// ── Path-level assertions (ensure routes exist in the schema) ─────────────

type _AssertPasskeysGet = paths["/auth/passkeys"]["get"];
type _AssertPasskeysPatch = paths["/auth/passkeys/{key_id}"]["patch"];
type _AssertDemoEchoPost = paths["/demo/echo"]["post"];
type _AssertDemoPingGet = paths["/demo/ping"]["get"];
type _AssertDemoSseGet = paths["/demo/sse"]["get"];

// Password auth routes
type _AssertRegisterPost = paths["/auth/register"]["post"];
type _AssertLoginPost = paths["/auth/login"]["post"];

// Passkey auth routes
type _AssertPasskeyRegisterStartPost =
  paths["/auth/passkey/register/start"]["post"];
type _AssertPasskeyRegisterFinishPost =
  paths["/auth/passkey/register/finish"]["post"];
type _AssertPasskeyLoginStartPost =
  paths["/auth/passkey/login/start"]["post"];
type _AssertPasskeyLoginFinishPost =
  paths["/auth/passkey/login/finish"]["post"];

// Suppress "declared but never read" – they exist purely for the type check.
export type {
  _AssertPasskeysGet,
  _AssertPasskeysPatch,
  _AssertDemoEchoPost,
  _AssertDemoPingGet,
  _AssertDemoSseGet,
  _AssertRegisterPost,
  _AssertLoginPost,
  _AssertPasskeyRegisterStartPost,
  _AssertPasskeyRegisterFinishPost,
  _AssertPasskeyLoginStartPost,
  _AssertPasskeyLoginFinishPost,
};
