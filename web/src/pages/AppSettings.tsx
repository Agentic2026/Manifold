import { useState } from "react";
import { Settings, Monitor, Sun, Moon, Save } from "lucide-react";
import {
  applyThemePreference,
  readThemePreference,
  type ThemePreference,
} from "../theme";
import { cn } from "../lib/utils";

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-surface-raised border border-border rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h2 className="text-sm font-semibold text-text">{title}</h2>
        {description && (
          <p className="text-xs text-text-muted mt-0.5">{description}</p>
        )}
      </div>
      <div className="px-5 py-4 space-y-4">{children}</div>
    </div>
  );
}

function Field({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-6">
      <div className="flex-1">
        <p className="text-sm font-medium text-text">{label}</p>
        {description && (
          <p className="text-xs text-text-muted mt-0.5">{description}</p>
        )}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

const THEMES: { value: ThemePreference; label: string; icon: React.ElementType }[] =
  [
    { value: "system", label: "System", icon: Monitor },
    { value: "light",  label: "Light",  icon: Sun     },
    { value: "dark",   label: "Dark",   icon: Moon    },
  ];

export function AppSettings() {
  const [theme, setTheme] = useState<ThemePreference>(() =>
    typeof window === "undefined" ? "system" : readThemePreference(),
  );
  const [apiUrl, setApiUrl] = useState(
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "",
  );
  const [scanInterval, setScanInterval] = useState("5");
  const [alertOnCompromise, setAlertOnCompromise] = useState(true);
  const [alertOnWarning, setAlertOnWarning] = useState(true);
  const [saved, setSaved] = useState(false);

  const handleTheme = (pref: ThemePreference) => {
    setTheme(pref);
    applyThemePreference(pref);
  };

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <header className="flex items-center gap-3 px-6 h-14 border-b border-border bg-surface flex-shrink-0">
        <Settings className="w-5 h-5 text-primary" />
        <h1 className="text-sm font-semibold text-text">Settings</h1>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-6 py-6 space-y-5">
          {/* Appearance */}
          <Section
            title="Appearance"
            description="Control how AEGIS.LLM looks across all sessions."
          >
            <Field
              label="Theme"
              description="Choose a colour scheme or follow your system preference."
            >
              <div className="flex rounded-lg border border-border overflow-hidden">
                {THEMES.map(({ value, label, icon: Icon }) => (
                  <button
                    key={value}
                    onClick={() => handleTheme(value)}
                    className={cn(
                      "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
                      theme === value
                        ? "bg-primary text-white"
                        : "bg-surface-raised text-text-muted hover:text-text hover:bg-surface-alt",
                    )}
                  >
                    <Icon className="w-3 h-3" />
                    {label}
                  </button>
                ))}
              </div>
            </Field>
          </Section>

          {/* Backend */}
          <Section
            title="Backend Connection"
            description="Configure how the dashboard connects to the AEGIS API."
          >
            <Field
              label="API Base URL"
              description="Leave blank to use the Vite dev proxy (/api). In production, set VITE_API_BASE_URL."
            >
              <input
                type="url"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                placeholder="https://api.your-aegis.internal"
                className="w-64 px-3 py-1.5 text-xs bg-surface-alt border border-border rounded-lg text-text placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </Field>

            <Field
              label="Deep Scan Interval"
              description="How often to automatically run a deep scan (minutes). Set 0 to disable."
            >
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="0"
                  max="60"
                  value={scanInterval}
                  onChange={(e) => setScanInterval(e.target.value)}
                  className="w-20 px-3 py-1.5 text-xs bg-surface-alt border border-border rounded-lg text-text focus:outline-none focus:ring-1 focus:ring-primary text-right"
                />
                <span className="text-xs text-text-muted">min</span>
              </div>
            </Field>
          </Section>

          {/* Alerts */}
          <Section
            title="Alerts & Notifications"
            description="Choose which security events trigger in-app notifications."
          >
            <Field label="Alert on Compromised Node" description="Node status changes to 'compromised'.">
              <Toggle value={alertOnCompromise} onChange={setAlertOnCompromise} />
            </Field>
            <Field label="Alert on Warning" description="Node status changes to 'warning'.">
              <Toggle value={alertOnWarning} onChange={setAlertOnWarning} />
            </Field>
          </Section>

          {/* Save */}
          <div className="flex justify-end">
            <button
              onClick={handleSave}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all",
                saved
                  ? "bg-healthy text-white"
                  : "bg-primary text-white hover:bg-primary-hover",
              )}
            >
              <Save className="w-4 h-4" />
              {saved ? "Saved!" : "Save settings"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Toggle({
  value,
  onChange,
}: {
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      role="switch"
      aria-checked={value}
      onClick={() => onChange(!value)}
      className={cn(
        "relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors",
        value ? "bg-primary" : "bg-border",
      )}
    >
      <span
        className={cn(
          "inline-block h-4 w-4 rounded-full bg-white shadow transition-transform mt-0.5",
          value ? "translate-x-4.5" : "translate-x-0.5",
        )}
      />
    </button>
  );
}
