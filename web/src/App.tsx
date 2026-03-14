import { Routes, Route, Navigate } from "react-router";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { ForgotPassword } from "./pages/ForgotPassword";
import { ResetPassword } from "./pages/ResetPassword";
import { SystemMap } from "./pages/SystemMap";
import { LLMInsights } from "./pages/LLMInsights";
import { Vulnerabilities } from "./pages/Vulnerabilities";
import { RBACPolicies } from "./pages/RBACPolicies";
import { AppSettings } from "./pages/AppSettings";

export function App() {
  return (
    <Routes>
      {/* Public auth routes — rendered standalone (no sidebar) */}
      <Route path="/login"           element={<Login />} />
      <Route path="/register"        element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password"  element={<ResetPassword />} />

      {/* Protected AEGIS routes — wrapped in sidebar Layout */}
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/"                element={<SystemMap />} />
        <Route path="/insights"        element={<LLMInsights />} />
        <Route path="/vulnerabilities" element={<Vulnerabilities />} />
        <Route path="/rbac"            element={<RBACPolicies />} />
        <Route path="/settings"        element={<AppSettings />} />
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
