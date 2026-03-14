import { useEffect, useState } from "react";
import {
  BrainCircuit,
  AlertTriangle,
  Info,
  TrendingUp,
  Clock,
  ChevronRight,
} from "lucide-react";
import { aegisApi, type LLMInsight, type InsightType } from "../api/aegis";
import { cn } from "../lib/utils";

const TYPE_CONFIG: Record<
  InsightType,
  { label: string; icon: React.ElementType; badge: string }
> = {
  threat: {
    label: "Threat",
    icon: AlertTriangle,
    badge: "bg-compromised/10 text-compromised border border-compromised/20",
  },
  anomaly: {
    label: "Anomaly",
    icon: TrendingUp,
    badge: "bg-suspicious/10 text-suspicious border border-suspicious/20",
  },
  info: {
    label: "Info",
    icon: Info,
    badge: "bg-primary/10 text-primary border border-primary/20",
  },
};

function ConfidencePill({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 90 ? "bg-compromised" : pct >= 75 ? "bg-suspicious" : "bg-primary";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-border rounded-full overflow-hidden">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-text-muted tabular-nums">{pct}%</span>
    </div>
  );
}

function InsightCard({ insight }: { insight: LLMInsight }) {
  const [expanded, setExpanded] = useState(false);
  const { label, icon: Icon, badge } = TYPE_CONFIG[insight.type];
  const ts = new Date(insight.timestamp);

  return (
    <div className="bg-surface-raised border border-border rounded-xl overflow-hidden">
      <button
        className="w-full text-left p-4"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-surface-alt flex-shrink-0 mt-0.5">
            <Icon className="w-4 h-4 text-text-muted" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className={cn("text-[10px] px-2 py-0.5 rounded-full font-semibold", badge)}>
                {label}
              </span>
              <span className="text-[10px] text-text-muted font-mono">
                {insight.nodeName}
              </span>
            </div>
            <p className="text-sm font-semibold text-text mb-1">{insight.summary}</p>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1 text-[10px] text-text-muted">
                <Clock className="w-2.5 h-2.5" />
                {ts.toLocaleTimeString()} · {ts.toLocaleDateString()}
              </div>
              <ConfidencePill value={insight.confidence} />
            </div>
          </div>
          <ChevronRight
            className={cn(
              "w-4 h-4 text-text-muted flex-shrink-0 transition-transform mt-1",
              expanded && "rotate-90",
            )}
          />
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-border">
          <p className="text-xs text-text-muted leading-relaxed pt-3">
            {insight.details}
          </p>
        </div>
      )}
    </div>
  );
}

export function LLMInsights() {
  const [insights, setInsights] = useState<LLMInsight[]>([]);
  const [filter, setFilter] = useState<InsightType | "all">("all");

  useEffect(() => {
    aegisApi.getInsights().then(setInsights);
  }, []);

  const filtered =
    filter === "all" ? insights : insights.filter((i) => i.type === filter);

  const counts = {
    threat:  insights.filter((i) => i.type === "threat").length,
    anomaly: insights.filter((i) => i.type === "anomaly").length,
    info:    insights.filter((i) => i.type === "info").length,
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <header className="flex items-center gap-3 px-6 h-14 border-b border-border bg-surface flex-shrink-0">
        <BrainCircuit className="w-5 h-5 text-primary" />
        <h1 className="text-sm font-semibold text-text">LLM Insights</h1>
        <span className="text-xs text-text-muted">
          AI-generated analysis of agent behaviour and security posture
        </span>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-3">
            {(["threat", "anomaly", "info"] as const).map((type) => {
              const { label, icon: Icon, badge } = TYPE_CONFIG[type];
              return (
                <button
                  key={type}
                  onClick={() => setFilter(filter === type ? "all" : type)}
                  className={cn(
                    "flex items-center gap-3 p-4 rounded-xl border text-left transition-all",
                    filter === type
                      ? "bg-surface-raised border-primary ring-1 ring-primary"
                      : "bg-surface-raised border-border hover:border-primary/30",
                  )}
                >
                  <div className={cn("p-2 rounded-lg", badge.split(" ")[0])}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-xl font-bold text-text tabular-nums">
                      {counts[type]}
                    </p>
                    <p className="text-xs text-text-muted">{label}s</p>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Insights list */}
          <div className="space-y-3">
            {filtered.length === 0 ? (
              <div className="text-center py-12 text-text-muted text-sm">
                No insights to display.
              </div>
            ) : (
              filtered.map((insight) => (
                <InsightCard key={insight.id} insight={insight} />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
