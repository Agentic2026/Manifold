import { Routes, Route } from "react-router";
import { Layout } from "./components/Layout";
import { AegisLayout } from "./components/AegisLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Landing } from "./pages/Landing";
import { Register } from "./pages/Register";
import { Login } from "./pages/Login";
import { ForgotPassword } from "./pages/ForgotPassword";
import { ResetPassword } from "./pages/ResetPassword";
import { Dashboard } from "./pages/Dashboard";
import { Settings } from "./pages/Settings";
import { Admin } from "./pages/Admin";
import { DemoRealtime } from "./pages/DemoRealtime";
import { SystemMap } from "./pages/SystemMap";
import { LLMInsights } from "./pages/LLMInsights";
import { Vulnerabilities } from "./pages/Vulnerabilities";
import { RBACPolicies } from "./pages/RBACPolicies";
import { AppSettings } from "./pages/AppSettings";

export function App() {
  return (
    <Routes>
      {/* Auth-aware routes */}
      <Route element={<Layout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/register" element={<Register />} />
        <Route path="/login" element={<Login />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <Settings />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute requiredRole="admin">
              <Admin />
            </ProtectedRoute>
          }
        />
        <Route
          path="/demo/realtime"
          element={
            <ProtectedRoute>
              <DemoRealtime />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* AEGIS dashboard routes */}
      <Route element={<AegisLayout />}>
        <Route path="/map" element={<SystemMap />} />
        <Route path="/insights" element={<LLMInsights />} />
        <Route path="/vulnerabilities" element={<Vulnerabilities />} />
        <Route path="/rbac" element={<RBACPolicies />} />
        <Route path="/app-settings" element={<AppSettings />} />
      </Route>
    </Routes>
  );
}
