/**
 * cytoscapeStyles.ts — Cytoscape.js stylesheet for the System Map.
 *
 * Uses CSS-variable-aware color tokens so the graph respects the app
 * dark-theme palette.
 */

import type cytoscape from "cytoscape";

type Stylesheet = cytoscape.StylesheetStyle | cytoscape.StylesheetCSS;

// Status → border color (uses CSS custom properties from Tailwind config)
const STATUS_COLORS: Record<string, string> = {
  healthy: "#22c55e",      // --color-healthy
  warning: "#f59e0b",      // --color-suspicious
  compromised: "#ef4444",  // --color-compromised
};

const SERVICE_TYPE_SHAPES: Record<string, string> = {
  gateway: "diamond",
  frontend: "round-rectangle",
  service: "ellipse",
  api: "round-rectangle",
  agent: "hexagon",
  database: "barrel",
};

export const cytoscapeStylesheet: Stylesheet[] = [
  // ── Compound / group nodes ─────────────────────────────
  {
    selector: "node.group",
    style: {
      "background-color": "rgba(100, 116, 139, 0.08)",
      "background-opacity": 0.6,
      "border-width": 1,
      "border-color": "rgba(148, 163, 184, 0.3)",
      "border-style": "dashed",
      label: "data(label)",
      "text-valign": "top",
      "text-halign": "center",
      "font-size": 11,
      "font-weight": "bold",
      color: "rgba(148, 163, 184, 0.8)",
      "text-margin-y": -6,
      "padding": "20px",
      shape: "round-rectangle",
      "min-width": "80px",
      "min-height": "60px",
    } as unknown as Record<string, string | number>,
  },
  {
    selector: "node.group-network",
    style: {
      "border-color": "rgba(59, 130, 246, 0.3)",
      "background-color": "rgba(59, 130, 246, 0.05)",
    },
  },
  {
    selector: "node.group-project",
    style: {
      "border-color": "rgba(168, 85, 247, 0.3)",
      "background-color": "rgba(168, 85, 247, 0.05)",
    },
  },

  // ── Service (child) nodes ──────────────────────────────
  {
    selector: "node.service",
    style: {
      "background-color": "#1e293b",
      "border-width": 2,
      "border-color": "#475569",
      label: "data(label)",
      "text-valign": "bottom",
      "text-halign": "center",
      "font-size": 10,
      color: "#cbd5e1",
      "text-margin-y": 4,
      width: 36,
      height: 36,
      "text-max-width": "80px",
      "text-wrap": "ellipsis",
    } as unknown as Record<string, string | number>,
  },

  // Status-specific borders
  {
    selector: "node.status-healthy",
    style: {
      "border-color": STATUS_COLORS.healthy,
    },
  },
  {
    selector: "node.status-warning",
    style: {
      "border-color": STATUS_COLORS.warning,
    },
  },
  {
    selector: "node.status-compromised",
    style: {
      "border-color": STATUS_COLORS.compromised,
      "border-width": 3,
    },
  },

  // Type-specific shapes
  ...Object.entries(SERVICE_TYPE_SHAPES).map(
    ([type, shape]): Stylesheet => ({
      selector: `node.type-${type}`,
      style: {
        shape: shape as "ellipse",
      },
    }),
  ),

  // Selected state
  {
    selector: "node.service:selected",
    style: {
      "border-width": 3,
      "border-color": "#6366f1",
      "overlay-color": "#6366f1",
      "overlay-opacity": 0.15,
    },
  },

  // Search highlight
  {
    selector: "node.search-match",
    style: {
      "border-width": 3,
      "border-color": "#f59e0b",
      "overlay-color": "#f59e0b",
      "overlay-opacity": 0.1,
    },
  },

  // Dimmed (non-match during search)
  {
    selector: "node.search-dimmed",
    style: {
      opacity: 0.3,
    },
  },

  // ── Edges ──────────────────────────────────────────────
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": "#475569",
      "target-arrow-color": "#475569",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 0.8,
      opacity: 0.7,
    } as unknown as Record<string, string | number>,
  },
  {
    selector: "edge.kind-api",
    style: {
      "line-style": "dashed",
      "line-color": "#6366f1",
      "target-arrow-color": "#6366f1",
      width: 1.5,
    },
  },
  {
    selector: "edge.kind-network",
    style: {
      "line-color": "#475569",
      "target-arrow-color": "#475569",
    },
  },
  {
    selector: "edge.kind-inferred",
    style: {
      "line-style": "dotted",
      "line-color": "#64748b",
      "target-arrow-color": "#64748b",
      width: 1,
      opacity: 0.4,
    },
  },
  // Shared-network inferred edges — security-relevant, slightly more visible
  {
    selector: "edge.inferred-network",
    style: {
      "line-style": "dotted",
      "line-color": "#3b82f6",
      "target-arrow-color": "#3b82f6",
      width: 1,
      opacity: 0.5,
    },
  },
  // Same-project-only inferred edges — de-emphasized
  {
    selector: "edge.inferred-project",
    style: {
      "line-style": "dotted",
      "line-color": "#64748b",
      "target-arrow-color": "#64748b",
      width: 0.75,
      opacity: 0.25,
    },
  },
  {
    selector: "edge.hidden-edge",
    style: {
      display: "none",
    },
  },
  // Focus-mode dimming for unrelated elements
  {
    selector: "node.focus-dimmed",
    style: {
      opacity: 0.2,
    },
  },
  {
    selector: "edge.focus-dimmed",
    style: {
      opacity: 0.1,
    },
  },
  {
    selector: "edge:selected",
    style: {
      width: 2.5,
      opacity: 1,
      "line-color": "#6366f1",
      "target-arrow-color": "#6366f1",
    },
  },
];
