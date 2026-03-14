import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type NodeProps,
  type EdgeProps,
  type Node,
  type Edge,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  MarkerType,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useState, useCallback } from "react";
import {
  Globe,
  Monitor as MonitorIcon,
  ShieldCheck,
  Zap,
  Bot,
  Database,
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
} from "lucide-react";
import {
  aegisApi,
  type TopologyNode,
  type TopologyEdge,
  type ServiceType,
  type NodeStatus,
} from "../api/aegis";
import { cn } from "../lib/utils";

// ────────────────────────────────────────────────────────────
// Icons per service type
// ────────────────────────────────────────────────────────────

const SERVICE_ICONS: Record<ServiceType, React.ElementType> = {
  gateway:  Globe,
  frontend: MonitorIcon,
  service:  ShieldCheck,
  api:      Zap,
  agent:    Bot,
  database: Database,
};

// ────────────────────────────────────────────────────────────
// Status helpers
// ────────────────────────────────────────────────────────────

const STATUS_BORDER: Record<NodeStatus, string> = {
  healthy:     "border-healthy",
  warning:     "border-suspicious",
  compromised: "border-compromised",
};

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

const STATUS_DOT: Record<NodeStatus, string> = {
  healthy:     "bg-healthy",
  warning:     "bg-suspicious",
  compromised: "bg-compromised animate-pulse",
};

// ────────────────────────────────────────────────────────────
// Custom Node
// ────────────────────────────────────────────────────────────

interface ServiceNodeData {
  label: string;
  serviceId: string;
  status: NodeStatus;
  type: ServiceType;
  [key: string]: unknown;
}

function ServiceNode({ data, selected }: NodeProps) {
  const d = data as ServiceNodeData;
  const Icon = SERVICE_ICONS[d.type] ?? Zap;

  return (
    <div
      className={cn(
        "relative bg-surface-raised border-2 rounded-xl px-3.5 py-2.5 min-w-[148px] shadow-lg",
        "transition-all duration-150",
        STATUS_BORDER[d.status],
        selected
          ? "ring-2 ring-primary ring-offset-2 ring-offset-surface"
          : "hover:shadow-xl",
      )}
    >
      {/* Alert badge for compromised */}
      {d.status === "compromised" && (
        <span className="absolute -top-2 -right-2 flex h-4 w-4 items-center justify-center rounded-full bg-compromised text-white text-[9px] font-bold shadow">
          !
        </span>
      )}

      {/* Header row */}
      <div className="flex items-center gap-2 mb-1">
        <div
          className={cn(
            "p-1 rounded-md flex-shrink-0",
            d.status === "compromised"
              ? "bg-compromised/15"
              : d.status === "warning"
                ? "bg-suspicious/15"
                : "bg-primary/10",
          )}
        >
          <Icon
            className={cn(
              "w-3.5 h-3.5",
              d.status === "compromised"
                ? "text-compromised"
                : d.status === "warning"
                  ? "text-suspicious"
                  : "text-primary",
            )}
          />
        </div>
        <span className="text-[13px] font-semibold text-text leading-tight truncate max-w-[100px]">
          {d.label}
        </span>
      </div>

      {/* ID */}
      <p className="text-[10px] font-mono text-text-muted">{d.serviceId}</p>

      {/* Status dot */}
      <div className="flex items-center gap-1.5 mt-1.5">
        <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", STATUS_DOT[d.status])} />
        <span className={cn("text-[10px] font-medium",
          d.status === "compromised" ? "text-compromised" :
          d.status === "warning" ? "text-suspicious" : "text-healthy"
        )}>
          {STATUS_LABEL[d.status]}
        </span>
      </div>

      {/* Handles */}
      <Handle type="target" position={Position.Left}  />
      <Handle type="target" position={Position.Top}   />
      <Handle type="source" position={Position.Right} />
      <Handle type="source" position={Position.Bottom}/>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// Custom Edge
// ────────────────────────────────────────────────────────────

interface AegisEdgeData {
  kind: "network" | "api";
  label: string;
  [key: string]: unknown;
}

function AegisEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const d = data as AegisEdgeData | undefined;
  const isApi = d?.kind === "api";

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: isApi
            ? "var(--color-primary)"
            : "var(--color-border)",
          strokeWidth: isApi ? 1.5 : 1,
          strokeDasharray: isApi ? "6 3" : undefined,
          opacity: 0.75,
        }}
      />
      {d?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
            className="absolute nodrag nopan"
          >
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-surface-raised border border-border text-text-muted shadow-sm whitespace-nowrap">
              {d.label}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

// ────────────────────────────────────────────────────────────
// Convert API data → React Flow format
// ────────────────────────────────────────────────────────────

function toRFNode(n: TopologyNode): Node {
  return {
    id: n.id,
    type: "serviceNode",
    position: n.position,
    data: {
      label: n.label,
      serviceId: n.serviceId,
      status: n.status,
      type: n.type,
    },
  };
}

function toRFEdge(e: TopologyEdge): Edge {
  return {
    id: e.id,
    source: e.source,
    target: e.target,
    type: "aegisEdge",
    animated: e.animated ?? false,
    markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 },
    data: { kind: e.kind, label: e.label },
  };
}

const NODE_TYPES = { serviceNode: ServiceNode };
const EDGE_TYPES = { aegisEdge: AegisEdge };

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
}: {
  node: TopologyNode;
  onClose: () => void;
  onIsolate: () => void;
  onRevoke: () => void;
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
              <TelCard
                label="Latency"
                value={`${node.telemetry.latencyMs} ms`}
                trend={node.telemetry.latencyMs > 100 ? "up" : "neutral"}
              />
              <TelCard
                label="Error Rate"
                value={`${node.telemetry.errorRate}%`}
                trend={node.telemetry.errorRate > 1 ? "up" : "neutral"}
              />
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
  const [topologyNodes, setTopologyNodes] = useState<TopologyNode[]>([]);
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [notifications, setNotifications] = useState(3);

  // Initial load
  useEffect(() => {
    aegisApi.getTopology().then((data) => {
      setTopologyNodes(data.nodes);
      setRfNodes(data.nodes.map(toRFNode));
      setRfEdges(data.edges.map(toRFEdge));
      setLastUpdated(new Date(data.lastUpdated));
    });
  }, [setRfNodes, setRfEdges]);

  const handleDeepScan = async () => {
    setIsScanning(true);
    const data = await aegisApi.runDeepScan();
    setTopologyNodes(data.nodes);
    setRfNodes(data.nodes.map(toRFNode));
    setRfEdges(data.edges.map(toRFEdge));
    setLastUpdated(new Date(data.lastUpdated));
    setIsScanning(false);
  };

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const found = topologyNodes.find((n) => n.id === node.id);
      setSelectedNode(found ?? null);
    },
    [topologyNodes],
  );

  const handlePaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const handleIsolate = async () => {
    if (!selectedNode) return;
    await aegisApi.isolateNode(selectedNode.id);
    alert(`Entity "${selectedNode.label}" has been isolated.`);
  };

  const handleRevoke = async () => {
    if (!selectedNode) return;
    await aegisApi.revokeRBAC(selectedNode.id);
    alert(`RBAC roles for "${selectedNode.label}" have been revoked.`);
  };

  // Filter nodes by search
  const filteredNodes = rfNodes.map((n) => {
    if (!searchQuery) return { ...n, hidden: false };
    const data = n.data as ServiceNodeData;
    const match =
      data.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
      data.serviceId.toLowerCase().includes(searchQuery.toLowerCase());
    return { ...n, hidden: !match };
  });

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
            <span className="w-1.5 h-1.5 rounded-full bg-monitoring animate-pulse" />
            <span className="text-[11px] font-medium text-monitoring">Monitoring Active</span>
          </div>
          <div className="hidden lg:block">
            <StatusBar nodes={topologyNodes} />
          </div>
        </div>

        {/* Right: search + bell + scan */}
        <div className="flex items-center gap-2">
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
        {/* React Flow */}
        <div className="flex-1 relative">
          <ReactFlow
            nodes={filteredNodes}
            edges={rfEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={NODE_TYPES}
            edgeTypes={EDGE_TYPES}
            onNodeClick={handleNodeClick}
            onPaneClick={handlePaneClick}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.3}
            maxZoom={2}
            defaultEdgeOptions={{
              markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 },
            }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={20}
              size={1}
              color="var(--color-border)"
            />
            <Controls position="bottom-right" />
            <MiniMap
              position="top-right"
              nodeColor={(n) => {
                const d = n.data as ServiceNodeData;
                return d.status === "compromised"
                  ? "var(--color-compromised)"
                  : d.status === "warning"
                    ? "var(--color-suspicious)"
                    : "var(--color-healthy)";
              }}
              maskColor="var(--color-surface-alt)"
            />
            <Legend />
          </ReactFlow>
        </div>

        {/* Inspector panel */}
        {selectedNode && (
          <NodeInspector
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
            onIsolate={() => void handleIsolate()}
            onRevoke={() => void handleRevoke()}
          />
        )}
      </div>
    </div>
  );
}
