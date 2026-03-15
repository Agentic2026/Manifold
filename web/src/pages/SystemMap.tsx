import { useEffect, useState, useCallback, useMemo } from "react";
import {
  X,
  Play,
  Bell,
  Search,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Clock,
  ChevronRight,
  RefreshCw,
  BrainCircuit,
  Network,
  Layers,
} from "lucide-react";
import {
  manifoldApi,
  type TopologyNode,
  type TopologyData,
  type TopologyGroup,
  type NodeStatus,
} from "../api/manifold";
import { cn } from "../lib/utils";
import { TopologyGraph } from "../components/topology/TopologyGraph";
import { useToast } from "../context/ToastContext";
import { useChat } from "../context/ChatContext";

// ────────────────────────────────────────────────────────────
// Status helpers
// ────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<NodeStatus, string> = {
  healthy:     "Secure",
  warning:     "Warning",
  compromised: "Compromised",
};

const STATUS_BADGE: Record<NodeStatus, string> = {
  healthy:
    "bg-healthy/10 text-healthy border border-healthy/20",
  warning:
    "bg-suspicious/10 text-suspicious border border-suspicious/20",
  compromised:
    "bg-compromised/10 text-compromised border border-compromised/20",
};

// ────────────────────────────────────────────────────────────
// Telemetry card
// ────────────────────────────────────────────────────────────

function TelCard({
  label,
  value,
  trend,
}: {
  label: string;
  value: string;
  trend?: "up" | "down" | "neutral";
}) {
  return (
    <div className="bg-surface-alt rounded-lg p-2.5 border border-border">
      <p className="text-[10px] text-text-muted mb-1">{label}</p>
      <div className="flex items-end justify-between gap-1">
        <span className="text-sm font-semibold text-text tabular-nums">{value}</span>
        {trend === "up" && <TrendingUp className="w-3 h-3 text-compromised" />}
        {trend === "down" && <TrendingDown className="w-3 h-3 text-healthy" />}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// Inspector panel
// ────────────────────────────────────────────────────────────

function NodeInspector({
  node,
  onClose,
  onIsolate,
  onRevoke,
  onAskAI,
}: {
  node: TopologyNode;
  onClose: () => void;
  onIsolate: () => void;
  onRevoke: () => void;
  onAskAI: () => void;
}) {
  return (
    <aside className="w-80 flex-shrink-0 flex flex-col border-l border-border bg-surface overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          Inspector
        </span>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-surface-alt transition-colors text-text-muted hover:text-text"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Identity */}
        <div>
          <div className="flex items-start justify-between gap-2 mb-1">
            <h2 className="text-base font-semibold text-text leading-tight">
              {node.label}
            </h2>
            <span
              className={cn(
                "text-[10px] px-2 py-0.5 rounded-full font-semibold flex-shrink-0 mt-0.5",
                STATUS_BADGE[node.status],
              )}
            >
              {STATUS_LABEL[node.status]}
            </span>
          </div>
          <p className="text-xs font-mono text-text-muted">ID: {node.serviceId}</p>
          {node.description && (
            <p className="mt-2 text-xs text-text-muted leading-relaxed">
              {node.description}
            </p>
          )}
        </div>

        {/* Telemetry */}
        {node.telemetry && (
          <div>
            <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2">
              Live Telemetry
            </p>
            <div className="grid grid-cols-2 gap-2">
              <TelCard
                label="Ingress"
                value={`${node.telemetry.ingressMbps} MB/s`}
                trend={node.status === "compromised" ? "up" : "neutral"}
              />
              <TelCard
                label="Egress"
                value={`${node.telemetry.egressMbps} MB/s`}
                trend={
                  node.status === "compromised"
                    ? "up"
                    : node.status === "warning"
                      ? "up"
                      : "neutral"
                }
              />
              {node.telemetry.latencyMs != null && (
                <TelCard
                  label="Latency"
                  value={`${node.telemetry.latencyMs} ms`}
                  trend={node.telemetry.latencyMs > 100 ? "up" : "neutral"}
                />
              )}
              {node.telemetry.errorRate != null && (
                <TelCard
                  label="Error Rate"
                  value={`${node.telemetry.errorRate}%`}
                  trend={node.telemetry.errorRate > 1 ? "up" : "neutral"}
                />
              )}
              {node.telemetry.lastSeen && (
                <TelCard
                  label="Last Seen"
                  value={(() => { try { return new Date(node.telemetry!.lastSeen!).toLocaleTimeString(); } catch { return "—"; } })()}
                />
              )}
            </div>
          </div>
        )}

        {/* LLM Analysis */}
        {node.analysis && (
          <div>
            <p className="text-[10px] font-semibold text-primary uppercase tracking-wider mb-2">
              LLM Security Analysis
            </p>
            <div
              className={cn(
                "rounded-lg p-3 text-xs leading-relaxed border",
                node.status === "compromised"
                  ? "bg-compromised/5 border-compromised/20 text-text"
                  : node.status === "warning"
                    ? "bg-suspicious/5 border-suspicious/20 text-text"
                    : "bg-surface-alt border-border text-text-muted",
              )}
            >
              {node.analysis.summary}
            </div>

            {node.analysis.findings.length > 0 && (
              <ul className="mt-2 space-y-1.5">
                {node.analysis.findings.map((f, i) => (
                  <li key={i} className="flex gap-2 text-xs text-text-muted">
                    <AlertTriangle className="w-3 h-3 text-suspicious flex-shrink-0 mt-0.5" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            )}

            {node.analysis.recommendations.length > 0 && (
              <div className="mt-3">
                <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">
                  Recommendations
                </p>
                <ul className="space-y-1">
                  {node.analysis.recommendations.map((r, i) => (
                    <li key={i} className="flex gap-2 text-xs text-text-muted">
                      <ChevronRight className="w-3 h-3 text-primary flex-shrink-0 mt-0.5" />
                      <span>{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="p-4 border-t border-border flex-shrink-0 space-y-2">
        <button
          onClick={onAskAI}
          className="w-full py-2 rounded-lg text-sm font-semibold bg-primary text-white hover:bg-primary-hover transition-colors flex items-center justify-center gap-2"
        >
          <BrainCircuit className="w-3.5 h-3.5" />
          Ask AI About This Node
        </button>
        <button
          onClick={onIsolate}
          className="w-full py-2 rounded-lg text-sm font-semibold bg-compromised text-white hover:bg-compromised/90 transition-colors"
        >
          Isolate Entity
        </button>
        <button
          onClick={onRevoke}
          className="w-full py-2 rounded-lg text-sm font-semibold bg-surface-alt border border-border text-text hover:bg-surface transition-colors"
        >
          Revoke RBAC
        </button>
      </div>
    </aside>
  );
}

// ────────────────────────────────────────────────────────────
// Legend
// ────────────────────────────────────────────────────────────

function Legend() {
  return (
    <div className="absolute bottom-4 left-4 z-10 bg-surface-raised border border-border rounded-xl p-3 shadow-lg text-xs space-y-1.5">
      <p className="font-semibold text-text-muted uppercase tracking-wider text-[10px] mb-2">
        Legend
      </p>
      {[
        { color: "bg-healthy",     label: "Secure / Healthy"    },
        { color: "bg-suspicious",  label: "Warning / Suspicious" },
        { color: "bg-compromised", label: "Compromised"          },
      ].map(({ color, label }) => (
        <div key={label} className="flex items-center gap-2 text-text-muted">
          <span className={cn("w-2 h-2 rounded-full flex-shrink-0", color)} />
          {label}
        </div>
      ))}
      <div className="border-t border-border pt-1.5 mt-1.5 space-y-1">
        <div className="flex items-center gap-2 text-text-muted">
          <span className="w-4 border-t border-border" />
          Network Edge
        </div>
        <div className="flex items-center gap-2 text-text-muted">
          <span className="w-4 border-t border-dashed border-primary" />
          API / MCP Edge
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// Status summary bar
// ────────────────────────────────────────────────────────────

function StatusBar({ nodes }: { nodes: TopologyNode[] }) {
  const healthy     = nodes.filter((n) => n.status === "healthy").length;
  const warning     = nodes.filter((n) => n.status === "warning").length;
  const compromised = nodes.filter((n) => n.status === "compromised").length;

  return (
    <div className="flex items-center gap-4 text-xs">
      <span className="flex items-center gap-1.5 text-healthy font-medium">
        <span className="w-1.5 h-1.5 rounded-full bg-healthy" />
        {healthy} healthy
      </span>
      <span className="flex items-center gap-1.5 text-suspicious font-medium">
        <span className="w-1.5 h-1.5 rounded-full bg-suspicious" />
        {warning} warning
      </span>
      <span className="flex items-center gap-1.5 text-compromised font-medium">
        <span className="w-1.5 h-1.5 rounded-full bg-compromised animate-pulse" />
        {compromised} compromised
      </span>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// Main page
// ────────────────────────────────────────────────────────────

export function SystemMap() {
  const [topologyData, setTopologyData] = useState<TopologyData | null>(null);
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [dataSource, setDataSource] = useState<"live" | "offline" | "empty">("live");
  const [searchQuery, setSearchQuery] = useState("");
  const [focusedGroupId, setFocusedGroupId] = useState<string | null>(null);
  const [notifications, setNotifications] = useState(3);
  const { addToast } = useToast();
  const { setNodeContext, setIsOpen: setChatOpen } = useChat();

  // Derive available groups for the group selector
  const groupList: TopologyGroup[] = useMemo(() => {
    if (!topologyData) return [];
    return topologyData.groups ?? [];
  }, [topologyData]);

  // Sync selected node to chat context
  useEffect(() => {
    if (selectedNode) {
      setNodeContext({
        nodeId: selectedNode.id,
        nodeName: selectedNode.label,
        status: selectedNode.status,
      });
    }
  }, [selectedNode, setNodeContext]);

  const loadTopology = useCallback((data: TopologyData) => {
    setTopologyData(data);
    setLastUpdated(new Date(data.lastUpdated));
  }, []);

  const fetchTopology = useCallback(async () => {
    const data = await manifoldApi.getTopology();
    if (data) {
      loadTopology(data);
      setDataSource(data.nodes.length > 0 ? "live" : "empty");
    } else {
      setDataSource("offline");
    }
  }, [loadTopology]);

  // Initial load + periodic live refresh every 12 seconds
  useEffect(() => {
    const timer = setTimeout(fetchTopology, 0);
    const interval = setInterval(fetchTopology, 12_000);
    return () => {
      clearTimeout(timer);
      clearInterval(interval);
    };
  }, [fetchTopology]);

  const handleDeepScan = async () => {
    setIsScanning(true);
    const data = await manifoldApi.runDeepScan();
    if (data) {
      loadTopology(data);
    }
    setIsScanning(false);
    addToast({ title: "Deep scan complete", description: "Topology updated with latest findings.", variant: "info" });
  };

  const handleNodeSelect = useCallback(
    (nodeId: string | null) => {
      if (!nodeId) {
        setSelectedNode(null);
        return;
      }
      const found = topologyData?.nodes.find((n) => n.id === nodeId);
      setSelectedNode(found ?? null);
    },
    [topologyData],
  );

  const handleIsolate = async () => {
    if (!selectedNode) return;
    await manifoldApi.isolateNode(selectedNode.id);
    addToast({
      title: `"${selectedNode.label}" isolated`,
      description: "All network traffic has been blocked for this entity.",
      variant: "warning",
    });
  };

  const handleRevoke = async () => {
    if (!selectedNode) return;
    await manifoldApi.revokeRBAC(selectedNode.id);
    addToast({
      title: `RBAC revoked for "${selectedNode.label}"`,
      description: "All role bindings have been removed.",
      variant: "success",
    });
  };

  const handleAskAI = () => {
    setChatOpen(true);
  };

  const topologyNodes = topologyData?.nodes ?? [];

  return (
    <div className="flex flex-col h-full">
      {/* ── Page header ─────────────────────────────────── */}
      <header className="flex items-center justify-between px-5 h-14 border-b border-border bg-surface/90 backdrop-blur-md flex-shrink-0">
        {/* Left: title + status */}
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-sm font-semibold text-text">System Map</h1>
            {lastUpdated && (
              <p className="text-[10px] text-text-muted flex items-center gap-1">
                <Clock className="w-2.5 h-2.5" />
                Updated {lastUpdated.toLocaleTimeString()}
              </p>
            )}
          </div>
          <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-monitoring/10 border border-monitoring/20">
            <span className={cn("w-1.5 h-1.5 rounded-full", dataSource === "live" ? "bg-monitoring animate-pulse" : dataSource === "empty" ? "bg-suspicious" : "bg-text-muted")} />
            <span className={cn("text-[11px] font-medium", dataSource === "live" ? "text-monitoring" : dataSource === "empty" ? "text-suspicious" : "text-text-muted")}>
              {dataSource === "live" ? "Live" : dataSource === "empty" ? "Waiting for data" : "Offline"}
            </span>
          </div>
          <div className="hidden lg:block">
            <StatusBar nodes={topologyNodes} />
          </div>
        </div>

        {/* Right: group selector + search + bell + scan */}
        <div className="flex items-center gap-2">
          {/* Group selector */}
          {groupList.length > 0 && (
            <div className="relative hidden sm:flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-text-muted" />
              <select
                value={focusedGroupId ?? ""}
                onChange={(e) => setFocusedGroupId(e.target.value || null)}
                className="py-1.5 pl-1 pr-6 text-xs bg-surface-alt border border-border rounded-lg text-text focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
              >
                <option value="">All groups</option>
                {groupList.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.label}{g.kind !== "ungrouped" ? ` (${g.kind})` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="relative hidden sm:block">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
            <input
              type="text"
              placeholder="Search nodes, IPs, policies…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-3 py-1.5 text-xs bg-surface-alt border border-border rounded-lg text-text placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary w-52"
            />
          </div>

          <button
            className="relative p-2 rounded-lg hover:bg-surface-alt transition-colors text-text-muted hover:text-text"
            onClick={() => setNotifications(0)}
          >
            <Bell className="w-4 h-4" />
            {notifications > 0 && (
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-compromised" />
            )}
          </button>

          <button
            onClick={() => void handleDeepScan()}
            disabled={isScanning}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
              isScanning
                ? "bg-primary/20 text-primary cursor-not-allowed"
                : "bg-primary text-white hover:bg-primary-hover",
            )}
          >
            {isScanning ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5" />
            )}
            {isScanning ? "Scanning…" : "Run Deep Scan"}
          </button>
        </div>
      </header>

      {/* ── Canvas + Inspector ───────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Cytoscape Graph */}
        <div className="flex-1 relative">
          {/* Empty-state overlay */}
          {topologyNodes.length === 0 && (dataSource === "live" || dataSource === "empty") && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-surface/80 backdrop-blur-sm">
              <Network className="w-12 h-12 text-text-muted/40" />
              <p className="text-sm font-medium text-text-muted">No services discovered yet</p>
              <p className="text-xs text-text-muted/60 max-w-sm text-center">
                Add the Manifold monitoring service to your existing Docker Compose stack and redeploy.
                Services will appear here automatically as telemetry is ingested.
              </p>
            </div>
          )}
          {topologyNodes.length === 0 && dataSource === "offline" && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-surface/80 backdrop-blur-sm">
              <AlertTriangle className="w-12 h-12 text-suspicious/60" />
              <p className="text-sm font-medium text-text-muted">Backend unavailable</p>
              <p className="text-xs text-text-muted/60 max-w-sm text-center">
                Cannot connect to the Manifold API. The system will retry automatically.
              </p>
            </div>
          )}
          {topologyData && (
            <TopologyGraph
              data={topologyData}
              searchQuery={searchQuery}
              selectedNodeId={selectedNode?.id ?? null}
              onNodeSelect={handleNodeSelect}
              focusedGroupId={focusedGroupId}
            />
          )}
          <Legend />
        </div>

        {/* Inspector panel */}
        {selectedNode && (
          <NodeInspector
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
            onIsolate={() => void handleIsolate()}
            onRevoke={() => void handleRevoke()}
            onAskAI={handleAskAI}
          />
        )}
      </div>
    </div>
  );
}
