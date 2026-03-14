import { Routes, Route } from "react-router";
import { Layout } from "./components/Layout";
import { SystemMap } from "./pages/SystemMap";
import { LLMInsights } from "./pages/LLMInsights";
import { Vulnerabilities } from "./pages/Vulnerabilities";
import { RBACPolicies } from "./pages/RBACPolicies";
import { AppSettings } from "./pages/AppSettings";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/"                element={<SystemMap />}      />
        <Route path="/insights"        element={<LLMInsights />}    />
        <Route path="/vulnerabilities" element={<Vulnerabilities />} />
        <Route path="/rbac"            element={<RBACPolicies />}   />
        <Route path="/settings"        element={<AppSettings />}    />
      </Route>
    </Routes>
  );
}
