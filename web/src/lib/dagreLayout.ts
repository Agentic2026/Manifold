/**
 * dagreLayout.ts — Dagre-based automatic layout for focused subgraphs.
 *
 * Replaces the backend's static grid positions when viewing a single
 * group's services, giving a proper hierarchical DAG layout.
 */

import dagre from "@dagrejs/dagre";

interface LayoutNode {
  id: string;
  width?: number;
  height?: number;
}

interface LayoutEdge {
  source: string;
  target: string;
}

interface PositionedNode {
  id: string;
  position: { x: number; y: number };
}

/**
 * Compute dagre positions for a set of nodes and edges.
 * Returns a map of node id → { x, y } position.
 */
export function computeDagreLayout(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  options?: {
    direction?: "TB" | "LR" | "BT" | "RL";
    nodeWidth?: number;
    nodeHeight?: number;
    rankSep?: number;
    nodeSep?: number;
  },
): PositionedNode[] {
  const {
    direction = "TB",
    nodeWidth = 160,
    nodeHeight = 60,
    rankSep = 80,
    nodeSep = 40,
  } = options ?? {};

  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: direction, ranksep: rankSep, nodesep: nodeSep });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of nodes) {
    g.setNode(n.id, { width: n.width ?? nodeWidth, height: n.height ?? nodeHeight });
  }
  for (const e of edges) {
    // Only add edges whose endpoints are in the graph
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target);
    }
  }

  dagre.layout(g);

  return nodes.map(n => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      position: {
        x: (pos?.x ?? 0) - (n.width ?? nodeWidth) / 2,
        y: (pos?.y ?? 0) - (n.height ?? nodeHeight) / 2,
      },
    };
  });
}
