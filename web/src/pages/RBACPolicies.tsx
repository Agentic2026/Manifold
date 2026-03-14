import { useEffect, useState } from "react";
import { KeyRound, Clock, AlertTriangle, ShieldCheck } from "lucide-react";
import { aegisApi, type RBACPolicy } from "../api/aegis";
import { cn } from "../lib/utils";

const RISK_CONFIG: Record<
  RBACPolicy["riskLevel"],
  { label: string; badge: string }
> = {
  high: {
    label: "High Risk",
    badge: "bg-compromised/10 text-compromised border border-compromised/20",
  },
  medium: {
    label: "Medium",
    badge: "bg-suspicious/10 text-suspicious border border-suspicious/20",
  },
  low: {
    label: "Low",
    badge: "bg-healthy/10 text-healthy border border-healthy/20",
  },
};

function PolicyRow({ policy }: { policy: RBACPolicy }) {
  const risk = RISK_CONFIG[policy.riskLevel];
  const modified = new Date(policy.lastModified);
  const daysSince = Math.floor(
    (Date.now() - modified.getTime()) / (1000 * 60 * 60 * 24),
  );

  return (
    <div
      className={cn(
        "grid grid-cols-[auto_1fr_auto_auto] gap-0 items-center px-4 py-3.5 border-b border-border last:border-0 hover:bg-surface-alt transition-colors",
        policy.riskLevel === "high" && "border-l-2 border-compromised",
        policy.riskLevel === "medium" && "border-l-2 border-suspicious",
        policy.riskLevel === "low" && "border-l-2 border-healthy",
      )}
    >
      {/* Icon */}
      <div className="pr-3">
        {policy.riskLevel === "high" ? (
          <AlertTriangle className="w-4 h-4 text-compromised" />
        ) : (
          <ShieldCheck className="w-4 h-4 text-healthy" />
        )}
      </div>

      {/* Details */}
      <div className="min-w-0 pr-4">
        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
          <p className="text-sm font-semibold text-text font-mono">{policy.role}</p>
          <span className="text-[10px] text-text-muted">→</span>
          <p className="text-xs text-text-muted font-mono">{policy.subject}</p>
        </div>
        <p className="text-[10px] text-text-muted font-mono mb-1">{policy.scope}</p>
        <div className="flex flex-wrap gap-1">
          {policy.permissions.map((perm) => (
            <span
              key={perm}
              className="text-[9px] px-1.5 py-0.5 rounded bg-surface-alt border border-border text-text-muted font-mono"
            >
              {perm}
            </span>
          ))}
        </div>
      </div>

      {/* Risk */}
      <div className="pr-4 flex-shrink-0">
        <span className={cn("text-[10px] px-2 py-0.5 rounded-full", risk.badge)}>
          {risk.label}
        </span>
      </div>

      {/* Modified */}
      <div className="flex-shrink-0 text-right">
        <div className="flex items-center gap-1 text-[10px] text-text-muted">
          <Clock className="w-2.5 h-2.5" />
          {daysSince}d ago
        </div>
        {daysSince > 60 && (
          <p className="text-[9px] text-suspicious mt-0.5">Rotation overdue</p>
        )}
      </div>
    </div>
  );
}

export function RBACPolicies() {
  const [policies, setPolicies] = useState<RBACPolicy[]>([]);
  const [filter, setFilter] = useState<RBACPolicy["riskLevel"] | "all">("all");

  useEffect(() => {
    aegisApi.getRBACPolicies().then(setPolicies);
  }, []);

  const counts = {
    high:   policies.filter((p) => p.riskLevel === "high").length,
    medium: policies.filter((p) => p.riskLevel === "medium").length,
    low:    policies.filter((p) => p.riskLevel === "low").length,
  };

  const filtered =
    filter === "all" ? policies : policies.filter((p) => p.riskLevel === filter);

  // Sort: high > medium > low
  const ORDER: RBACPolicy["riskLevel"][] = ["high", "medium", "low"];
  const sorted = [...filtered].sort(
    (a, b) => ORDER.indexOf(a.riskLevel) - ORDER.indexOf(b.riskLevel),
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <header className="flex items-center gap-3 px-6 h-14 border-b border-border bg-surface flex-shrink-0">
        <KeyRound className="w-5 h-5 text-primary" />
        <h1 className="text-sm font-semibold text-text">RBAC Policies</h1>
        <span className="text-xs text-text-muted">
          {counts.high} high-risk role binding{counts.high !== 1 ? "s" : ""} detected
        </span>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-6 space-y-6">
          {/* Filter chips */}
          <div className="flex items-center gap-2">
            {(["all", "high", "medium", "low"] as const).map((level) => (
              <button
                key={level}
                onClick={() => setFilter(level)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium border transition-all",
                  filter === level
                    ? "bg-primary text-white border-primary"
                    : "bg-surface-raised border-border text-text-muted hover:text-text hover:border-primary/30",
                )}
              >
                {level === "all"
                  ? `All (${policies.length})`
                  : `${level.charAt(0).toUpperCase() + level.slice(1)} (${counts[level]})`}
              </button>
            ))}
          </div>

          {/* Policy table */}
          <div className="bg-surface-raised border border-border rounded-xl overflow-hidden">
            <div className="grid grid-cols-[auto_1fr_auto_auto] gap-0 text-[10px] font-semibold uppercase tracking-wider text-text-muted border-b border-border px-4 py-2.5">
              <span className="pr-3" />
              <span>Role / Subject / Scope</span>
              <span className="pr-4 text-right">Risk</span>
              <span className="text-right">Modified</span>
            </div>

            {sorted.length === 0 ? (
              <div className="text-center py-10 text-sm text-text-muted">
                No policies found.
              </div>
            ) : (
              sorted.map((policy) => <PolicyRow key={policy.id} policy={policy} />)
            )}
          </div>

          {/* Warning callout */}
          {counts.high > 0 && (
            <div className="flex gap-3 p-4 rounded-xl bg-compromised/5 border border-compromised/20">
              <AlertTriangle className="w-5 h-5 text-compromised flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-text mb-1">
                  High-risk bindings detected
                </p>
                <p className="text-xs text-text-muted leading-relaxed">
                  The <span className="font-mono text-text">mcp_bridge_role</span> and{" "}
                  <span className="font-mono text-text">vector_read_role</span> bindings
                  are assigned to the compromised{" "}
                  <span className="font-mono text-text">LLM-AGENT</span>. Immediate
                  revocation is recommended.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
