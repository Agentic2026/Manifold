import { useEffect, useState } from "react";
import { Bug, Clock, ExternalLink } from "lucide-react";
import { aegisApi, type Vulnerability, type VulnSeverity } from "../api/aegis";
import { cn } from "../lib/utils";

const SEV_CONFIG: Record<
  VulnSeverity,
  { label: string; badge: string; row: string }
> = {
  critical: {
    label: "Critical",
    badge: "bg-compromised/10 text-compromised border border-compromised/30 font-bold",
    row:   "border-l-2 border-compromised",
  },
  high: {
    label: "High",
    badge: "bg-suspicious/15 text-suspicious border border-suspicious/30",
    row:   "border-l-2 border-suspicious",
  },
  medium: {
    label: "Medium",
    badge: "bg-warning/10 text-warning border border-warning/20",
    row:   "border-l-2 border-warning",
  },
  low: {
    label: "Low",
    badge: "bg-primary/10 text-primary border border-primary/20",
    row:   "border-l-2 border-primary",
  },
};

const STATUS_BADGE: Record<Vulnerability["status"], string> = {
  "open":        "bg-surface-alt text-text-muted border border-border",
  "in-progress": "bg-primary/10 text-primary border border-primary/20",
  "resolved":    "bg-healthy/10 text-healthy border border-healthy/20",
};

function SeverityCount({
  severity,
  count,
  active,
  onClick,
}: {
  severity: VulnSeverity;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  const { label, badge } = SEV_CONFIG[severity];
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex flex-col items-center p-4 rounded-xl border transition-all",
        active
          ? "bg-surface-raised border-primary ring-1 ring-primary"
          : "bg-surface-raised border-border hover:border-primary/30",
      )}
    >
      <span className="text-2xl font-bold text-text tabular-nums">{count}</span>
      <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full mt-1", badge)}>
        {label}
      </span>
    </button>
  );
}

export function Vulnerabilities() {
  const [vulns, setVulns] = useState<Vulnerability[]>([]);
  const [filter, setFilter] = useState<VulnSeverity | "all">("all");

  useEffect(() => {
    aegisApi.getVulnerabilities().then(setVulns);
  }, []);

  const counts: Record<VulnSeverity, number> = {
    critical: vulns.filter((v) => v.severity === "critical").length,
    high:     vulns.filter((v) => v.severity === "high").length,
    medium:   vulns.filter((v) => v.severity === "medium").length,
    low:      vulns.filter((v) => v.severity === "low").length,
  };

  const filtered =
    filter === "all" ? vulns : vulns.filter((v) => v.severity === filter);

  // Sort: critical > high > medium > low, then by discoveredAt desc
  const ORDER: VulnSeverity[] = ["critical", "high", "medium", "low"];
  const sorted = [...filtered].sort((a, b) => {
    const si = ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity);
    if (si !== 0) return si;
    return new Date(b.discoveredAt).getTime() - new Date(a.discoveredAt).getTime();
  });

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <header className="flex items-center gap-3 px-6 h-14 border-b border-border bg-surface flex-shrink-0">
        <Bug className="w-5 h-5 text-primary" />
        <h1 className="text-sm font-semibold text-text">Vulnerabilities</h1>
        <span className="text-xs text-text-muted">
          {vulns.filter((v) => v.status === "open").length} open issues across your system
        </span>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-6 space-y-6">
          {/* Severity summary */}
          <div className="grid grid-cols-4 gap-3">
            {(["critical", "high", "medium", "low"] as VulnSeverity[]).map((sev) => (
              <SeverityCount
                key={sev}
                severity={sev}
                count={counts[sev]}
                active={filter === sev}
                onClick={() => setFilter(filter === sev ? "all" : sev)}
              />
            ))}
          </div>

          {/* Table */}
          <div className="bg-surface-raised border border-border rounded-xl overflow-hidden">
            <div className="grid grid-cols-[1fr_auto_auto_auto] gap-0 text-[10px] font-semibold uppercase tracking-wider text-text-muted border-b border-border px-4 py-2.5">
              <span>Vulnerability</span>
              <span className="text-right pr-4">Severity</span>
              <span className="text-right pr-4">Status</span>
              <span className="text-right">Discovered</span>
            </div>

            {sorted.length === 0 ? (
              <div className="text-center py-10 text-sm text-text-muted">
                No vulnerabilities found.
              </div>
            ) : (
              sorted.map((v) => {
                const sev = SEV_CONFIG[v.severity];
                const ts = new Date(v.discoveredAt);
                return (
                  <div
                    key={v.id}
                    className={cn(
                      "grid grid-cols-[1fr_auto_auto_auto] gap-0 items-start px-4 py-3 border-b border-border last:border-0 hover:bg-surface-alt transition-colors",
                      sev.row,
                    )}
                  >
                    <div className="pr-4 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <p className="text-sm font-medium text-text truncate">
                          {v.title}
                        </p>
                        {v.cve && (
                          <span className="flex items-center gap-0.5 text-[10px] font-mono text-primary bg-primary/10 px-1.5 py-0.5 rounded flex-shrink-0">
                            {v.cve}
                            <ExternalLink className="w-2.5 h-2.5" />
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-text-muted leading-relaxed line-clamp-2">
                        {v.description}
                      </p>
                      <p className="text-[10px] font-mono text-text-muted mt-1">
                        {v.affectedNode} · {v.affectedNodeId}
                      </p>
                    </div>
                    <div className="pr-4 flex-shrink-0 pt-0.5">
                      <span className={cn("text-[10px] px-2 py-0.5 rounded-full", sev.badge)}>
                        {sev.label}
                      </span>
                    </div>
                    <div className="pr-4 flex-shrink-0 pt-0.5">
                      <span className={cn("text-[10px] px-2 py-0.5 rounded-full", STATUS_BADGE[v.status])}>
                        {v.status}
                      </span>
                    </div>
                    <div className="flex-shrink-0 pt-0.5">
                      <div className="flex items-center gap-1 text-[10px] text-text-muted whitespace-nowrap">
                        <Clock className="w-2.5 h-2.5" />
                        {ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
