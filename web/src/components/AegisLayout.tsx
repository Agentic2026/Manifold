import { Outlet, NavLink } from "react-router";
import {
  Shield,
  Network,
  BrainCircuit,
  Bug,
  KeyRound,
  Settings,
  Monitor,
  Sun,
  Moon,
  ChevronRight,
  LogOut,
} from "lucide-react";
import { useState, useEffect, useCallback } from "react";
import {
  applyEffectiveThemeForPreference,
  applyThemePreference,
  getEffectiveTheme,
  readThemePreference,
  subscribeToSystemThemeChanges,
  type ThemePreference,
} from "../theme";
import { cn } from "../lib/utils";
import { ToastProvider } from "../context/ToastContext";
import { ToastContainer } from "./Toast";
import { ChatProvider } from "../context/ChatContext";
import { AIChatPanel } from "./AIChatPanel";
import { SecurityGauge } from "./SecurityGauge";
import { aegisApi } from "../api/aegis";
import { useAuth } from "../auth";

const NAV_ITEMS = [
  { href: "/",                label: "System Map",      icon: Network       },
  { href: "/insights",        label: "LLM Insights",    icon: BrainCircuit  },
  { href: "/vulnerabilities", label: "Vulnerabilities", icon: Bug           },
  { href: "/rbac",            label: "RBAC Policies",   icon: KeyRound      },
];

const THEME_CYCLE: ThemePreference[] = ["system", "light", "dark"];

function ThemeToggle({
  preference,
  effectiveTheme,
  onCycle,
}: {
  preference: ThemePreference;
  effectiveTheme: "light" | "dark";
  onCycle: () => void;
}) {
  const label =
    preference === "system"
      ? `System (${effectiveTheme})`
      : preference === "light"
        ? "Light"
        : "Dark";
  const Icon =
    preference === "system" ? Monitor : effectiveTheme === "dark" ? Moon : Sun;

  return (
    <button
      onClick={onCycle}
      className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-text-muted hover:bg-surface hover:text-text transition-colors group"
      aria-label={`Theme: ${label}. Click to cycle.`}
    >
      <Icon className="w-4 h-4 flex-shrink-0" />
      <span className="flex-1 text-left">{label}</span>
      <ChevronRight className="w-3 h-3 opacity-0 group-hover:opacity-40 transition-opacity" />
    </button>
  );
}

export function AegisLayout() {
  const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
    typeof window === "undefined" ? "system" : readThemePreference(),
  );
  const [systemIsDark, setSystemIsDark] = useState(() =>
    typeof window === "undefined"
      ? false
      : getEffectiveTheme("system") === "dark",
  );
  const [securityScore, setSecurityScore] = useState<{
    score: number;
    breakdown: { label: string; impact: number }[];
  } | null>(null);

  const { logout } = useAuth();

  const handleLogout = useCallback(async () => {
    await logout();
  }, [logout]);

  // Fetch security score from backend on mount and periodically
  useEffect(() => {
    const fetchScore = () => {
      aegisApi.getSecurityScore().then(setSecurityScore).catch(() => {
        // Score fetch may fail when backend is unavailable; silently retry on next interval
      });
    };
    const timer = setTimeout(fetchScore, 0);
    const interval = setInterval(fetchScore, 15_000);
    return () => {
      clearTimeout(timer);
      clearInterval(interval);
    };
  }, []);
  const effectiveTheme: "light" | "dark" =
    themePreference === "system"
      ? systemIsDark
        ? "dark"
        : "light"
      : themePreference;

  useEffect(() => {
    applyThemePreference(themePreference);
    if (themePreference !== "system") return;
    return subscribeToSystemThemeChanges(() => {
      const effective = applyEffectiveThemeForPreference("system");
      setSystemIsDark(effective === "dark");
    });
  }, [themePreference]);

  useEffect(() => {
    const onPreferenceChange = () => {
      const pref = readThemePreference();
      setThemePreference(pref);
      if (pref === "system") {
        setSystemIsDark(getEffectiveTheme("system") === "dark");
      }
    };
    window.addEventListener("theme-preference-change", onPreferenceChange);
    return () =>
      window.removeEventListener("theme-preference-change", onPreferenceChange);
  }, []);

  const cycleTheme = () => {
    const idx = THEME_CYCLE.indexOf(themePreference);
    const next = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length] ?? "system";
    setThemePreference(next);
    applyThemePreference(next);
  };

  return (
    <ToastProvider>
    <ChatProvider>
    <div className="flex h-screen overflow-hidden bg-surface">
      {/* ── Sidebar ───────────────────────────────────────── */}
      <aside className="w-56 flex-shrink-0 flex flex-col border-r border-border bg-surface-alt">
        {/* Brand */}
        <div className="flex items-center gap-2.5 px-4 h-14 border-b border-border flex-shrink-0">
          <div className="p-1.5 rounded-lg bg-primary/10">
            <Shield className="w-5 h-5 text-primary" />
          </div>
          <div className="leading-none">
            <span className="font-bold text-sm text-text tracking-tight">
              AEGIS
            </span>
            <span className="text-xs text-text-muted ml-1 font-mono">.LLM</span>
          </div>
        </div>

        {/* Security Gauge */}
        {securityScore && (
          <div className="border-b border-border">
            <SecurityGauge
              score={securityScore.score}
              breakdown={securityScore.breakdown}
            />
          </div>
        )}

        {/* Nav */}
        <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
          <p className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-widest text-text-muted">
            Monitor
          </p>
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
            <NavLink
              key={href}
              to={href}
              end={href === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-text-muted hover:bg-surface hover:text-text",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    className={cn(
                      "w-4 h-4 flex-shrink-0",
                      isActive ? "text-primary" : "text-text-muted",
                    )}
                  />
                  {label}
                </>
              )}
            </NavLink>
          ))}

          <div className="pt-3">
            <p className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-widest text-text-muted">
              Configure
            </p>
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-text-muted hover:bg-surface hover:text-text",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Settings
                    className={cn(
                      "w-4 h-4 flex-shrink-0",
                      isActive ? "text-primary" : "text-text-muted",
                    )}
                  />
                  Settings
                </>
              )}
            </NavLink>
          </div>
        </nav>

        {/* Footer */}
        <div className="px-2 py-3 border-t border-border flex-shrink-0 space-y-0.5">
          <ThemeToggle
            preference={themePreference}
            effectiveTheme={effectiveTheme}
            onCycle={cycleTheme}
          />
          <button
            onClick={() => void handleLogout()}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-text-muted hover:bg-surface hover:text-text transition-colors"
            data-testid="nav-logout"
          >
            <LogOut className="w-4 h-4 flex-shrink-0" />
            <span className="flex-1 text-left">Logout</span>
          </button>
          <p className="px-3 pt-2 text-[10px] text-text-muted/60">
            v0.1.0 · hackathon build
          </p>
        </div>
      </aside>

      {/* ── Main ──────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <Outlet />
      </main>

      {/* Floating overlays */}
      <AIChatPanel />
      <ToastContainer />
    </div>
    </ChatProvider>
    </ToastProvider>
  );
}
