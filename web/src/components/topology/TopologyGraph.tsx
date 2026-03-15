/**
 * TopologyGraph.tsx — Cytoscape.js + ELK layered graph renderer
 * for the Manifold System Map.
 *
 * Responsibilities:
 * - Accepts grouped topology data
 * - Maps groups to Cytoscape compound nodes
 * - Maps services to child nodes within groups
 * - Maps edges to Cytoscape edges with display filtering
 * - Runs ELK layered layout with production-grade options
 * - Supports node selection and callbacks to the inspector
 * - Supports pan/zoom/fit and search highlighting
 */

import { useRef, useEffect, useCallback, useMemo } from "react";
import cytoscape from "cytoscape";
import elk from "cytoscape-elk";

import type { TopologyData } from "../../api/manifold";
import { topologyToElements } from "./topologyElements";
import { cytoscapeStylesheet } from "./cytoscapeStyles";

// Register the ELK layout extension (idempotent)
cytoscape.use(elk);

// ── ELK layout options ────────────────────────────────────────

const ELK_LAYOUT_OPTIONS = {
  name: "elk" as const,
  // ELK algorithm options passed through to elkjs
  elk: {
    algorithm: "layered",
    // Direction: left-to-right works well for service topologies
    "elk.direction": "RIGHT",
    // Node placement strategy — minimize bends
    "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    // Crossing minimization
    "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    // Edge routing — orthogonal for clarity
    "elk.edgeRouting": "POLYLINE",
    // Spacing for readable dense graphs
    "elk.spacing.nodeNode": "50",
    "elk.spacing.edgeEdge": "25",
    "elk.spacing.edgeNode": "30",
    "elk.layered.spacing.nodeNodeBetweenLayers": "80",
    "elk.layered.spacing.edgeNodeBetweenLayers": "40",
    // Hierarchy handling for compound nodes
    "elk.hierarchyHandling": "INCLUDE_CHILDREN",
    // Padding inside compound nodes
    "elk.padding": "[top=30,left=20,bottom=20,right=20]",
    // Stability / determinism
    "elk.randomSeed": "42",
  },
  // Fit and animate after layout
  fit: true,
  padding: 40,
  animate: false,
};

// ── Component props ───────────────────────────────────────────

interface TopologyGraphProps {
  data: TopologyData;
  searchQuery: string;
  selectedNodeId: string | null;
  onNodeSelect: (nodeId: string | null) => void;
  focusedGroupId?: string | null;
}

export function TopologyGraph({
  data,
  searchQuery,
  selectedNodeId,
  onNodeSelect,
  focusedGroupId = null,
}: TopologyGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  // Convert topology data to Cytoscape elements
  const elements = useMemo(() => topologyToElements(data, focusedGroupId), [data, focusedGroupId]);

  // ── Initialize Cytoscape ──────────────────────────────────

  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: elements as cytoscape.ElementDefinition[],
      style: cytoscapeStylesheet,
      // Interaction
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      minZoom: 0.2,
      maxZoom: 3,
    });

    cyRef.current = cy;

    // Run ELK layout
    const layout = cy.layout(ELK_LAYOUT_OPTIONS as cytoscape.LayoutOptions);
    layout.run();

    // Node click handler
    cy.on("tap", "node.service", (evt) => {
      const nodeId = evt.target.id();
      onNodeSelect(nodeId);
    });

    // Background click → deselect
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        onNodeSelect(null);
      }
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // We intentionally only re-init when the data identity changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements]);

  // ── Sync selection ────────────────────────────────────────

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    // Clear previous selection
    cy.nodes(".service").unselect();

    if (selectedNodeId) {
      const node = cy.getElementById(selectedNodeId);
      if (node.length > 0) {
        node.select();
      }
    }
  }, [selectedNodeId]);

  // ── Search highlighting ───────────────────────────────────

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    const serviceNodes = cy.nodes(".service");

    if (!searchQuery) {
      serviceNodes.removeClass("search-match search-dimmed");
      return;
    }

    const q = searchQuery.toLowerCase();
    serviceNodes.forEach((node) => {
      const label = String(node.data("label") ?? "").toLowerCase();
      const serviceId = String(node.data("serviceId") ?? "").toLowerCase();
      const match = label.includes(q) || serviceId.includes(q);
      node.toggleClass("search-match", match);
      node.toggleClass("search-dimmed", !match);
    });

    // Center on first match
    const matches = serviceNodes.filter(".search-match");
    if (matches.length > 0) {
      cy.animate({
        center: { eles: matches.first() },
        duration: 300,
      });
    }
  }, [searchQuery]);

  // ── Focus group: center on selected group ─────────────────

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    if (focusedGroupId) {
      // Fit to the focused group's children
      const groupNode = cy.getElementById(focusedGroupId);
      if (groupNode.length > 0) {
        const children = groupNode.children();
        if (children.length > 0) {
          cy.animate({
            fit: { eles: children, padding: 60 },
            duration: 400,
          });
        }
      }
    } else {
      // Reset: fit all elements
      cy.animate({
        fit: { eles: cy.elements(), padding: 40 },
        duration: 400,
      });
    }
  }, [focusedGroupId]);

  // ── Fit view helper ────────────────────────────────────────

  const handleFitView = useCallback(() => {
    cyRef.current?.fit(undefined, 40);
  }, []);

  // ── Zoom controls ──────────────────────────────────────────

  const handleZoomIn = useCallback(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({ level: cy.zoom() * 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }, []);

  const handleZoomOut = useCallback(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({ level: cy.zoom() / 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }, []);

  return (
    <div className="relative w-full h-full">
      {/* Cytoscape container */}
      <div ref={containerRef} className="w-full h-full" />

      {/* Zoom controls */}
      <div className="absolute bottom-4 right-4 z-10 flex flex-col gap-1">
        <button
          onClick={handleZoomIn}
          className="w-8 h-8 rounded-lg bg-surface-raised border border-border text-text-muted hover:text-text hover:bg-surface-alt transition-colors flex items-center justify-center text-sm font-bold"
          title="Zoom in"
        >
          +
        </button>
        <button
          onClick={handleZoomOut}
          className="w-8 h-8 rounded-lg bg-surface-raised border border-border text-text-muted hover:text-text hover:bg-surface-alt transition-colors flex items-center justify-center text-sm font-bold"
          title="Zoom out"
        >
          −
        </button>
        <button
          onClick={handleFitView}
          className="w-8 h-8 rounded-lg bg-surface-raised border border-border text-text-muted hover:text-text hover:bg-surface-alt transition-colors flex items-center justify-center text-xs"
          title="Fit view"
        >
          ⊞
        </button>
      </div>
    </div>
  );
}
