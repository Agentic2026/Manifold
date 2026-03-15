/**
 * topologyElements.ts — Convert the Manifold topology API response into
 * Cytoscape.js element definitions with compound (group) nodes and
 * edge display filtering.
 *
 * Supports two rendering modes:
 * - **Overview** (`focusedGroupId === null`): nuanced edge visibility from backend
 * - **Focused** (`focusedGroupId === "<id>"`): show internal edges for
 *   the selected group, dim unrelated groups/edges
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
  inferredSubtype: string | null;
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

// ── Edge class helpers ────────────────────────────────────────

/**
 * Compute CSS classes for an edge in overview mode (no group focused).
 * Uses the backend-provided `display` field and `inferredSubtype`.
 */
function overviewEdgeClasses(
  kind: string,
  display: string,
  inferredSubtype: string | null,
): string {
  const classes: string[] = [`kind-${kind}`];

  if (display === "hidden") {
    classes.push("hidden-edge");
  } else if (kind === "inferred" && inferredSubtype === "shared_network") {
    classes.push("inferred-network");
  } else if (kind === "inferred" && inferredSubtype === "same_project") {
    classes.push("inferred-project");
  }

  return classes.filter(Boolean).join(" ");
}

/**
 * Compute CSS classes for an edge in focused-group mode.
 *
 * - Edges fully inside the focused group → visible (with subtype styling)
 * - Cross-group edges touching the focused group → visible
 * - All other edges → dimmed
 */
function focusedEdgeClasses(
  kind: string,
  inferredSubtype: string | null,
  sourceGroup: string | undefined,
  targetGroup: string | undefined,
  focusedGroupId: string,
): string {
  const classes: string[] = [`kind-${kind}`];

  const srcInGroup = sourceGroup === focusedGroupId;
  const tgtInGroup = targetGroup === focusedGroupId;

  if (srcInGroup && tgtInGroup) {
    // Internal edge for focused group — always visible
    if (kind === "inferred" && inferredSubtype === "same_project") {
      classes.push("inferred-project");
    } else if (kind === "inferred" && inferredSubtype === "shared_network") {
      classes.push("inferred-network");
    }
  } else if (srcInGroup || tgtInGroup) {
    // Cross-group edge touching focused group — visible
  } else {
    // Unrelated edge — dimmed
    classes.push("focus-dimmed");
  }

  return classes.filter(Boolean).join(" ");
}

// ── Main conversion ───────────────────────────────────────────

/**
 * Convert a TopologyData payload into a flat array of Cytoscape elements.
 *
 * - Groups become compound (parent) nodes.
 * - Service nodes become child nodes inside their group.
 * - Edge visibility depends on the rendering mode (overview vs focused).
 *
 * @param focusedGroupId - When set, enables focused-group rendering.
 */
export function topologyToElements(
  data: TopologyData,
  focusedGroupId?: string | null,
): CyElement[] {
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

  const isFocused = !!focusedGroupId;

  // 1. Compound (group) parent nodes
  for (const g of groups) {
    const dimmed = isFocused && g.id !== focusedGroupId;
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
      classes: [
        "group",
        `group-${g.kind}`,
        dimmed ? "focus-dimmed" : "",
      ].filter(Boolean).join(" "),
    });
  }

  // 2. Service nodes (children of their group, if any)
  for (const n of data.nodes) {
    const parent = nodeGroupMap.get(n.id);
    const dimmed = isFocused && parent !== focusedGroupId;
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
      classes: [
        "service",
        `status-${n.status}`,
        `type-${n.type}`,
        dimmed ? "focus-dimmed" : "",
      ].filter(Boolean).join(" "),
    });
  }

  // 3. Edges
  for (const e of data.edges) {
    const display = e.display ?? "visible";
    const inferredSubtype = e.inferredSubtype ?? null;
    const sourceGroup = nodeGroupMap.get(e.source);
    const targetGroup = nodeGroupMap.get(e.target);

    const edgeClasses = isFocused
      ? focusedEdgeClasses(e.kind, inferredSubtype, sourceGroup, targetGroup, focusedGroupId!)
      : overviewEdgeClasses(e.kind, display, inferredSubtype);

    elements.push({
      group: "edges",
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        kind: e.kind,
        label: e.label,
        display,
        inferredSubtype,
        animated: e.animated ?? false,
      },
      classes: edgeClasses,
    });
  }

  return elements;
}
