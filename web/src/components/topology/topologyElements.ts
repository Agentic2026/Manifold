/**
 * topologyElements.ts — Convert the Manifold topology API response into
 * Cytoscape.js element definitions with compound (group) nodes and
 * edge display filtering.
 */

import type {
  TopologyNode,
  TopologyGroup,
  TopologyData,
  NodeStatus,
  ServiceType,
} from "../../api/manifold";

// ── Cytoscape element shapes ──────────────────────────────────

export interface CyNodeData {
  id: string;
  label: string;
  serviceId: string;
  status: NodeStatus;
  serviceType: ServiceType;
  parent?: string;        // compound-node grouping
  isGroup?: boolean;      // true for compound parent nodes
  groupKind?: string;
  groupLabel?: string;
  description?: string;
}

export interface CyEdgeData {
  id: string;
  source: string;
  target: string;
  kind: string;
  label: string;
  display: string;        // "visible" | "hidden"
  animated: boolean;
}

export interface CyElement {
  group: "nodes" | "edges";
  data: CyNodeData | CyEdgeData;
  classes?: string;
}

// ── Grouping fallback ─────────────────────────────────────────

/**
 * Derive groups from node IDs when the backend doesn't provide groups.
 * Falls back to compose project prefix (before `__`) or "ungrouped".
 */
export function deriveGroupsFromNodes(
  nodes: TopologyNode[],
): { groups: TopologyGroup[]; nodeGroupMap: Map<string, string> } {
  const map = new Map<string, string>();
  const groupSet = new Map<string, TopologyGroup>();

  for (const n of nodes) {
    if (n.groupId) {
      map.set(n.id, n.groupId);
      if (!groupSet.has(n.groupId)) {
        groupSet.set(n.groupId, {
          id: n.groupId,
          label: n.groupLabel ?? n.groupId,
          kind: n.groupKind ?? "ungrouped",
        });
      }
    } else if (n.id.includes("__")) {
      const project = n.id.split("__")[0] ?? n.id;
      const gid = `proj:${project}`;
      map.set(n.id, gid);
      if (!groupSet.has(gid)) {
        groupSet.set(gid, { id: gid, label: project, kind: "project" });
      }
    }
    // else: ungrouped — no parent
  }

  return { groups: [...groupSet.values()], nodeGroupMap: map };
}

// ── Main conversion ───────────────────────────────────────────

/**
 * Convert a TopologyData payload into a flat array of Cytoscape elements.
 *
 * - Groups become compound (parent) nodes.
 * - Service nodes become child nodes inside their group.
 * - Edges with `display === "hidden"` are tagged with a `hidden` class
 *   but still included so they can be toggled.
 */
export function topologyToElements(data: TopologyData): CyElement[] {
  const elements: CyElement[] = [];

  // Resolve groups — prefer backend-provided, fall back to derived
  let groups = data.groups ?? [];
  let nodeGroupMap: Map<string, string>;

  if (groups.length > 0) {
    nodeGroupMap = new Map<string, string>();
    for (const n of data.nodes) {
      if (n.groupId) nodeGroupMap.set(n.id, n.groupId);
    }
  } else {
    const derived = deriveGroupsFromNodes(data.nodes);
    groups = derived.groups;
    nodeGroupMap = derived.nodeGroupMap;
  }

  // 1. Compound (group) parent nodes
  for (const g of groups) {
    elements.push({
      group: "nodes",
      data: {
        id: g.id,
        label: g.label,
        serviceId: "",
        status: "healthy" as NodeStatus,
        serviceType: "service" as ServiceType,
        isGroup: true,
        groupKind: g.kind,
        groupLabel: g.label,
      },
      classes: `group group-${g.kind}`,
    });
  }

  // 2. Service nodes (children of their group, if any)
  for (const n of data.nodes) {
    const parent = nodeGroupMap.get(n.id);
    elements.push({
      group: "nodes",
      data: {
        id: n.id,
        label: n.label,
        serviceId: n.serviceId,
        status: n.status,
        serviceType: n.type,
        parent,
        description: n.description,
      },
      classes: `service status-${n.status} type-${n.type}`,
    });
  }

  // 3. Edges
  for (const e of data.edges) {
    const display = e.display ?? "visible";
    elements.push({
      group: "edges",
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        kind: e.kind,
        label: e.label,
        display,
        animated: e.animated ?? false,
      },
      classes: [
        `kind-${e.kind}`,
        display === "hidden" ? "hidden-edge" : "",
      ]
        .filter(Boolean)
        .join(" "),
    });
  }

  return elements;
}
