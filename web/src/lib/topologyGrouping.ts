/**
 * topologyGrouping.ts — Pure functions for transforming flat topology data
 * into grouped overview nodes and focused subgraph views.
 *
 * These helpers are consumed by the SystemMap page to implement the
 * two-level group-aware graph experience.
 */

import type {
  TopologyNode,
  TopologyEdge,
  TopologyGroup,
  NodeStatus,
} from "../api/manifold";

// ────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────

export type ViewMode = "overview" | "focused";

/** Aggregate health counts displayed on an overview group node. */
export interface GroupHealthCounts {
  healthy: number;
  warning: number;
  compromised: number;
  total: number;
}

/** Shape of a group node in overview mode. */
export interface OverviewGroupNode {
  id: string;
  kind: string;
  label: string;
  nodeIds: string[];
  health: GroupHealthCounts;
}

/** An edge between two groups in overview mode. */
export interface OverviewGroupEdge {
  id: string;
  sourceGroupId: string;
  targetGroupId: string;
  label: string;
  kind: string;
}

/** Data for a focused-group subgraph. */
export interface FocusedGroupData {
  nodes: TopologyNode[];
  /** Internal edges (both endpoints inside the group). */
  internalEdges: TopologyEdge[];
  /** Cross-group edges that touch this group (for optional faint display). */
  crossGroupEdges: TopologyEdge[];
}

// ────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────

function buildNodeGroupMap(nodes: TopologyNode[]): Map<string, string> {
  const m = new Map<string, string>();
  for (const n of nodes) {
    m.set(n.id, n.groupId ?? "ungrouped");
  }
  return m;
}

function countHealth(nodes: TopologyNode[]): GroupHealthCounts {
  const counts: GroupHealthCounts = { healthy: 0, warning: 0, compromised: 0, total: nodes.length };
  for (const n of nodes) {
    const s = n.status as NodeStatus;
    if (s === "compromised") counts.compromised++;
    else if (s === "warning") counts.warning++;
    else counts.healthy++;
  }
  return counts;
}

// ────────────────────────────────────────────────────────────
// Overview mode
// ────────────────────────────────────────────────────────────

/**
 * Build group-level overview nodes from the flat topology.
 * Each group gets aggregate health counts.
 */
export function buildOverviewGroups(
  nodes: TopologyNode[],
  groups: TopologyGroup[],
): OverviewGroupNode[] {
  const nodeMap = new Map(nodes.map(n => [n.id, n]));

  return groups.map(g => {
    const members = g.nodeIds
      .map(id => nodeMap.get(id))
      .filter((n): n is TopologyNode => n !== undefined);
    return {
      id: g.id,
      kind: g.kind,
      label: g.label,
      nodeIds: g.nodeIds,
      health: countHealth(members),
    };
  });
}

const GROUP_PAIR_DELIMITER = "||";

/**
 * Build inter-group edges for overview mode.
 * Only edges whose source and target belong to different groups are included.
 * Duplicate group-pair edges are deduplicated.
 */
export function buildOverviewEdges(
  edges: TopologyEdge[],
  nodes: TopologyNode[],
): OverviewGroupEdge[] {
  const nodeGroup = buildNodeGroupMap(nodes);
  const seen = new Set<string>();
  const result: OverviewGroupEdge[] = [];

  for (const e of edges) {
    const sg = nodeGroup.get(e.source);
    const tg = nodeGroup.get(e.target);
    if (!sg || !tg || sg === tg) continue;

    const pairKey = [sg, tg].sort().join(GROUP_PAIR_DELIMITER);
    if (seen.has(pairKey)) continue;
    seen.add(pairKey);

    result.push({
      id: `overview-${sg}-${tg}`,
      sourceGroupId: sg,
      targetGroupId: tg,
      label: "inter-group",
      kind: e.kind,
    });
  }
  return result;
}

// ────────────────────────────────────────────────────────────
// Focused group mode
// ────────────────────────────────────────────────────────────

/**
 * Extract the nodes and edges for a single focused group.
 */
export function buildFocusedGroupData(
  groupId: string,
  nodes: TopologyNode[],
  edges: TopologyEdge[],
): FocusedGroupData {
  const groupNodeIds = new Set(
    nodes.filter(n => (n.groupId ?? "ungrouped") === groupId).map(n => n.id),
  );
  const groupNodes = nodes.filter(n => groupNodeIds.has(n.id));

  const internalEdges: TopologyEdge[] = [];
  const crossGroupEdges: TopologyEdge[] = [];

  for (const e of edges) {
    const srcIn = groupNodeIds.has(e.source);
    const tgtIn = groupNodeIds.has(e.target);
    if (srcIn && tgtIn) {
      internalEdges.push(e);
    } else if (srcIn || tgtIn) {
      crossGroupEdges.push(e);
    }
  }

  return { nodes: groupNodes, internalEdges, crossGroupEdges };
}

// ────────────────────────────────────────────────────────────
// Edge classification helpers
// ────────────────────────────────────────────────────────────

/**
 * Classify an edge label as shared-network or same-project.
 * This is used in focused mode to style edges differently.
 */
export function classifyEdge(label: string): "shared-network" | "same-project" | "other" {
  if (label.includes("shared network")) return "shared-network";
  if (label.includes("same project")) return "same-project";
  return "other";
}
