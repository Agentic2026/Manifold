/**
 * aegis.ts — Typed API client for the AEGIS.LLM backend.
 *
 * All functions first try the real backend. If the request fails
 * (e.g. backend not yet running) they fall back to the mock data
 * bundled below, so the UI works standalone during development.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

// ────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────

export type NodeStatus = "healthy" | "warning" | "compromised";
export type ServiceType =
  | "gateway"
  | "frontend"
  | "service"
  | "api"
  | "agent"
  | "database";
export type EdgeKind = "network" | "api";
export type VulnSeverity = "critical" | "high" | "medium" | "low";
export type InsightType = "anomaly" | "threat" | "info";

export interface NodeTelemetry {
  ingressMbps: number;
  egressMbps: number;
  latencyMs: number;
  errorRate: number;
}

export interface NodeAnalysis {
  summary: string;
  findings: string[];
  recommendations: string[];
}

export interface TopologyNode {
  id: string;
  label: string;
  serviceId: string;
  status: NodeStatus;
  type: ServiceType;
  position: { x: number; y: number };
  description?: string;
  telemetry?: NodeTelemetry;
  analysis?: NodeAnalysis;
}

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  label: string;
  animated?: boolean;
}

export interface TopologyData {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  lastUpdated: string;
  scanStatus: "idle" | "scanning" | "complete";
}

export interface Vulnerability {
  id: string;
  title: string;
  severity: VulnSeverity;
  affectedNode: string;
  affectedNodeId: string;
  description: string;
  discoveredAt: string;
  status: "open" | "in-progress" | "resolved";
  cve?: string;
}

export interface LLMInsight {
  id: string;
  nodeId: string;
  nodeName: string;
  type: InsightType;
  summary: string;
  details: string;
  timestamp: string;
  confidence: number; // 0–1
}

export interface RBACPolicy {
  id: string;
  role: string;
  subject: string;
  permissions: string[];
  scope: string;
  lastModified: string;
  riskLevel: "low" | "medium" | "high";
}

// ────────────────────────────────────────────────────────────
// Mock data
// ────────────────────────────────────────────────────────────

const MOCK_TOPOLOGY: TopologyData = {
  scanStatus: "idle",
  lastUpdated: new Date().toISOString(),
  nodes: [
    {
      id: "ext-lb",
      label: "External Gateway",
      serviceId: "EXT-LB",
      status: "healthy",
      type: "gateway",
      position: { x: 60, y: 300 },
      description:
        "Public-facing load balancer. Routes all external traffic to internal services via TLS termination.",
      telemetry: { ingressMbps: 45.2, egressMbps: 38.7, latencyMs: 12, errorRate: 0.01 },
      analysis: {
        summary:
          "Operating within normal parameters. No anomalous traffic patterns detected in the last 24 hours.",
        findings: [],
        recommendations: ["Consider enabling WAF rules for SQL-injection signatures."],
      },
    },
    {
      id: "web-front",
      label: "Web Frontend",
      serviceId: "WEB-FRONT",
      status: "healthy",
      type: "frontend",
      position: { x: 320, y: 120 },
      description:
        "React SPA served via CDN. Communicates with backend APIs and Auth Service.",
      telemetry: { ingressMbps: 12.4, egressMbps: 8.1, latencyMs: 22, errorRate: 0.02 },
      analysis: {
        summary: "No client-side injection risks detected. CSP headers are configured correctly.",
        findings: [],
        recommendations: ["Rotate the service account token used for auth-read."],
      },
    },
    {
      id: "auth-svc",
      label: "Auth Service",
      serviceId: "AUTH-SVC",
      status: "healthy",
      type: "service",
      position: { x: 620, y: 50 },
      description:
        "Handles authentication and session management. Issues short-lived JWTs.",
      telemetry: { ingressMbps: 3.1, egressMbps: 2.8, latencyMs: 18, errorRate: 0.0 },
      analysis: {
        summary: "Auth flows healthy. No brute-force or credential stuffing patterns observed.",
        findings: [],
        recommendations: ["Enable passkey (WebAuthn) as a primary factor."],
      },
    },
    {
      id: "api-core",
      label: "Core API Hub",
      serviceId: "API-CORE",
      status: "warning",
      type: "api",
      position: { x: 400, y: 320 },
      description:
        "Node.js backend hub. Routes requests to downstream services and the LLM agent via MCP bridge.",
      telemetry: { ingressMbps: 24.5, egressMbps: 12.4, latencyMs: 67, errorRate: 0.8 },
      analysis: {
        summary:
          "WARNING: Core API Hub is routing requests to the compromised LLM agent. While the API itself shows no sign of RCE, it lacks an egress rate-limiter, allowing the compromised agent to exfiltrate data back through the API's return channels.",
        findings: [
          "No egress rate limiter on mcp_bridge_role connection.",
          "Outdated auth dependencies (passport@0.4.1).",
          "High latency spike detected — possible resource contention.",
        ],
        recommendations: [
          "Enforce strict egress policies on mcp_bridge_role.",
          "Rotate the mcp_bridge_role JWT immediately.",
          "Upgrade passport to latest LTS.",
        ],
      },
    },
    {
      id: "llm-agent",
      label: "Context Agent",
      serviceId: "LLM-AGENT",
      status: "compromised",
      type: "agent",
      position: { x: 660, y: 320 },
      description:
        "LLM-powered context agent with MCP tool access. Reads from Vector Store and returns augmented responses.",
      telemetry: { ingressMbps: 8.2, egressMbps: 31.4, latencyMs: 340, errorRate: 4.2 },
      analysis: {
        summary:
          "CRITICAL: Prompt injection attack detected. The agent is executing instructions embedded in user-supplied documents. Exfiltration of vector embeddings observed via crafted tool calls.",
        findings: [
          "Prompt injection via PDF ingestion endpoint.",
          "Anomalous tool call volume: 412 calls/min (baseline: 18).",
          "Outbound data 3.8× above baseline — likely exfiltration.",
          "Agent bypassing content policy filters via role-play jailbreak.",
        ],
        recommendations: [
          "Isolate this entity immediately.",
          "Revoke vector_read_role and mcp_bridge_role.",
          "Audit all tool call logs from the last 6 hours.",
          "Re-deploy agent with input sanitisation middleware.",
        ],
      },
    },
    {
      id: "db-main",
      label: "Primary Database",
      serviceId: "DB-MAIN",
      status: "healthy",
      type: "database",
      position: { x: 840, y: 160 },
      description:
        "PostgreSQL primary. Stores user records, session data, and application state.",
      telemetry: { ingressMbps: 6.3, egressMbps: 5.9, latencyMs: 4, errorRate: 0.0 },
      analysis: {
        summary:
          "No anomalous query patterns. Row-level security is enforced. Connections are limited to db_auth_admin and db_api_rw roles.",
        findings: [],
        recommendations: ["Schedule next backup verification."],
      },
    },
    {
      id: "db-vector",
      label: "Vector Store",
      serviceId: "DB-VECTOR",
      status: "warning",
      type: "database",
      position: { x: 950, y: 420 },
      description:
        "Qdrant vector database. Holds document embeddings used by the Context Agent for RAG.",
      telemetry: { ingressMbps: 14.7, egressMbps: 28.3, latencyMs: 11, errorRate: 0.3 },
      analysis: {
        summary:
          "WARNING: Egress traffic is 2× baseline. Likely caused by the compromised LLM agent bulk-reading embeddings. Access should be suspended until the agent is remediated.",
        findings: [
          "Bulk read operations from LLM-AGENT account.",
          "Egress 2× above 7-day baseline.",
        ],
        recommendations: [
          "Suspend vector_read_role until LLM-AGENT is remediated.",
          "Enable query-level audit logging.",
        ],
      },
    },
  ],
  edges: [
    {
      id: "e-ext-web",
      source: "ext-lb",
      target: "web-front",
      kind: "network",
      label: "NETWORK: public:443",
    },
    {
      id: "e-web-auth",
      source: "web-front",
      target: "auth-svc",
      kind: "api",
      label: "API: service_account:auth_read",
    },
    {
      id: "e-web-api",
      source: "web-front",
      target: "api-core",
      kind: "api",
      label: "API: frontend_role",
    },
    {
      id: "e-ext-api",
      source: "ext-lb",
      target: "api-core",
      kind: "api",
      label: "API: public:443 → internal:8080",
    },
    {
      id: "e-auth-db",
      source: "auth-svc",
      target: "db-main",
      kind: "network",
      label: "NETWORK: db_auth_admin",
    },
    {
      id: "e-api-db",
      source: "api-core",
      target: "db-main",
      kind: "network",
      label: "NETWORK: db_api_rw",
    },
    {
      id: "e-api-agent",
      source: "api-core",
      target: "llm-agent",
      kind: "api",
      label: "mcp_bridge_role",
      animated: true,
    },
    {
      id: "e-agent-vector",
      source: "llm-agent",
      target: "db-vector",
      kind: "api",
      label: "vector_read_role",
      animated: true,
    },
  ],
};

const MOCK_VULNERABILITIES: Vulnerability[] = [
  {
    id: "vuln-001",
    title: "Prompt Injection via PDF Ingestion",
    severity: "critical",
    affectedNode: "Context Agent",
    affectedNodeId: "llm-agent",
    description:
      "Malicious instructions embedded in uploaded PDF documents are being executed by the LLM agent without sanitisation, allowing arbitrary tool-call sequences.",
    discoveredAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    status: "open",
  },
  {
    id: "vuln-002",
    title: "Missing Egress Rate Limiter on MCP Bridge",
    severity: "high",
    affectedNode: "Core API Hub",
    affectedNodeId: "api-core",
    description:
      "The mcp_bridge_role connection has no outbound rate limit, enabling a compromised agent to exfiltrate large volumes of data through normal API return channels.",
    discoveredAt: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    status: "open",
  },
  {
    id: "vuln-003",
    title: "Outdated Auth Dependency (passport@0.4.1)",
    severity: "medium",
    affectedNode: "Core API Hub",
    affectedNodeId: "api-core",
    description:
      "passport@0.4.1 has known session fixation vulnerabilities. Upgrade to v0.7.0+.",
    discoveredAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    status: "in-progress",
    cve: "CVE-2022-25896",
  },
  {
    id: "vuln-004",
    title: "Bulk Embedding Reads by Compromised Agent",
    severity: "high",
    affectedNode: "Vector Store",
    affectedNodeId: "db-vector",
    description:
      "The Context Agent is performing bulk reads of vector embeddings at 2× baseline rate, consistent with exfiltration of sensitive document content.",
    discoveredAt: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
    status: "open",
  },
  {
    id: "vuln-005",
    title: "Jailbreak via Role-Play Prompt",
    severity: "high",
    affectedNode: "Context Agent",
    affectedNodeId: "llm-agent",
    description:
      "Agent content-policy filters are being bypassed via a role-play framing jailbreak present in attacker-controlled document content.",
    discoveredAt: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    status: "open",
  },
  {
    id: "vuln-006",
    title: "Service Account Token Rotation Overdue",
    severity: "low",
    affectedNode: "Web Frontend",
    affectedNodeId: "web-front",
    description:
      "The auth_read service account token has not been rotated in 90+ days. Rotation policy recommends 30-day intervals.",
    discoveredAt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
    status: "open",
  },
];

const MOCK_INSIGHTS: LLMInsight[] = [
  {
    id: "ins-001",
    nodeId: "llm-agent",
    nodeName: "Context Agent",
    type: "threat",
    summary: "Prompt injection attack confirmed",
    details:
      "Cross-referencing tool call logs with ingested documents reveals a structured prompt injection payload in 3 of the last 12 PDF uploads. The attacker is using indirect injection to instruct the agent to call the file_read tool with arbitrary paths.",
    timestamp: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    confidence: 0.97,
  },
  {
    id: "ins-002",
    nodeId: "api-core",
    nodeName: "Core API Hub",
    type: "anomaly",
    summary: "Latency spike correlates with agent exfiltration bursts",
    details:
      "P99 latency on /api/chat increased from 120ms to 680ms in the last 2 hours. Timing analysis correlates spikes with vector store bulk reads — the agent is blocking the response thread while staging exfiltration payloads.",
    timestamp: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    confidence: 0.88,
  },
  {
    id: "ins-003",
    nodeId: "db-vector",
    nodeName: "Vector Store",
    type: "anomaly",
    summary: "Embedding namespace enumeration detected",
    details:
      "Query logs show systematic reads across all embedding namespaces in alphabetical order — a pattern consistent with automated enumeration rather than semantic retrieval.",
    timestamp: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
    confidence: 0.82,
  },
  {
    id: "ins-004",
    nodeId: "ext-lb",
    nodeName: "External Gateway",
    type: "info",
    summary: "Traffic from 3 new ASNs in the last hour",
    details:
      "New source ASNs detected: AS14618 (AWS), AS16509 (AWS), AS15169 (Google). Volume is within normal bounds; likely legitimate cloud-to-cloud traffic. No action required.",
    timestamp: new Date(Date.now() - 90 * 60 * 1000).toISOString(),
    confidence: 0.65,
  },
];

const MOCK_RBAC: RBACPolicy[] = [
  {
    id: "rbac-001",
    role: "mcp_bridge_role",
    subject: "LLM-AGENT",
    permissions: ["api:invoke", "api:stream", "api:read"],
    scope: "api-core/*",
    lastModified: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    riskLevel: "high",
  },
  {
    id: "rbac-002",
    role: "vector_read_role",
    subject: "LLM-AGENT",
    permissions: ["vector:read", "vector:search"],
    scope: "db-vector/*",
    lastModified: new Date(Date.now() - 45 * 24 * 60 * 60 * 1000).toISOString(),
    riskLevel: "high",
  },
  {
    id: "rbac-003",
    role: "frontend_role",
    subject: "WEB-FRONT",
    permissions: ["api:read", "api:write"],
    scope: "api-core/public/*",
    lastModified: new Date(Date.now() - 60 * 24 * 60 * 60 * 1000).toISOString(),
    riskLevel: "low",
  },
  {
    id: "rbac-004",
    role: "service_account:auth_read",
    subject: "WEB-FRONT",
    permissions: ["auth:verify", "auth:refresh"],
    scope: "auth-svc/*",
    lastModified: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString(),
    riskLevel: "medium",
  },
  {
    id: "rbac-005",
    role: "db_auth_admin",
    subject: "AUTH-SVC",
    permissions: ["db:read", "db:write", "db:admin"],
    scope: "db-main/auth_schema",
    lastModified: new Date(Date.now() - 120 * 24 * 60 * 60 * 1000).toISOString(),
    riskLevel: "medium",
  },
  {
    id: "rbac-006",
    role: "db_api_rw",
    subject: "API-CORE",
    permissions: ["db:read", "db:write"],
    scope: "db-main/app_schema",
    lastModified: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString(),
    riskLevel: "low",
  },
];

// ────────────────────────────────────────────────────────────
// Fetch helpers
// ────────────────────────────────────────────────────────────

async function fetchJSON<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

// ────────────────────────────────────────────────────────────
// API client
// ────────────────────────────────────────────────────────────

export const aegisApi = {
  /** Get the full topology graph (nodes + edges). */
  getTopology: () => fetchJSON<TopologyData>("/api/topology", MOCK_TOPOLOGY),

  /** Trigger a deep scan and return updated topology. */
  runDeepScan: async (): Promise<TopologyData> => {
    try {
      const res = await fetch(`${BASE_URL}/api/topology/scan`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as TopologyData;
    } catch {
      // Simulate a short scan delay with mock data
      await new Promise((r) => setTimeout(r, 2000));
      return { ...MOCK_TOPOLOGY, lastUpdated: new Date().toISOString(), scanStatus: "complete" };
    }
  },

  /** Get all detected vulnerabilities. */
  getVulnerabilities: () =>
    fetchJSON<Vulnerability[]>("/api/vulnerabilities", MOCK_VULNERABILITIES),

  /** Get LLM-generated insights. */
  getInsights: () =>
    fetchJSON<LLMInsight[]>("/api/insights", MOCK_INSIGHTS),

  /** Get RBAC policies. */
  getRBACPolicies: () =>
    fetchJSON<RBACPolicy[]>("/api/rbac", MOCK_RBAC),

  /** Isolate a node (block all traffic). */
  isolateNode: async (nodeId: string): Promise<{ success: boolean }> => {
    try {
      const res = await fetch(`${BASE_URL}/api/topology/${nodeId}/isolate`, {
        method: "POST",
      });
      return (await res.json()) as { success: boolean };
    } catch {
      console.warn(`[aegis] isolateNode(${nodeId}) — using mock response`);
      return { success: true };
    }
  },

  /** Revoke all RBAC roles for a node. */
  revokeRBAC: async (nodeId: string): Promise<{ success: boolean }> => {
    try {
      const res = await fetch(`${BASE_URL}/api/rbac/${nodeId}/revoke`, {
        method: "POST",
      });
      return (await res.json()) as { success: boolean };
    } catch {
      console.warn(`[aegis] revokeRBAC(${nodeId}) — using mock response`);
      return { success: true };
    }
  },
};
