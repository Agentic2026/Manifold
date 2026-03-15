import { describe, it, expect } from "vitest";
import {
  buildOverviewGroups,
  buildOverviewEdges,
  buildFocusedGroupData,
  classifyEdge,
} from "../lib/topologyGrouping";
import type {
  TopologyNode,
  TopologyEdge,
  TopologyGroup,
} from "../api/manifold";

// ── Fixtures ────────────────────────────────────────────────

const NODES: TopologyNode[] = [
  { id: "a1", label: "A1", serviceId: "A1", status: "healthy", type: "service", position: { x: 0, y: 0 }, groupId: "g1", groupKind: "network", groupLabel: "net-frontend" },
  { id: "a2", label: "A2", serviceId: "A2", status: "warning", type: "api", position: { x: 0, y: 0 }, groupId: "g1", groupKind: "network", groupLabel: "net-frontend" },
  { id: "b1", label: "B1", serviceId: "B1", status: "compromised", type: "database", position: { x: 0, y: 0 }, groupId: "g2", groupKind: "compose", groupLabel: "backend" },
  { id: "b2", label: "B2", serviceId: "B2", status: "healthy", type: "service", position: { x: 0, y: 0 }, groupId: "g2", groupKind: "compose", groupLabel: "backend" },
  { id: "u1", label: "U1", serviceId: "U1", status: "healthy", type: "gateway", position: { x: 0, y: 0 }, groupId: "ungrouped", groupKind: "ungrouped", groupLabel: "Ungrouped" },
];

const GROUPS: TopologyGroup[] = [
  { id: "g1", kind: "network", label: "net-frontend", nodeIds: ["a1", "a2"] },
  { id: "g2", kind: "compose", label: "backend", nodeIds: ["b1", "b2"] },
  { id: "ungrouped", kind: "ungrouped", label: "Ungrouped", nodeIds: ["u1"] },
];

const EDGES: TopologyEdge[] = [
  { id: "e1", source: "a1", target: "a2", kind: "network", label: "inferred: shared network (frontend)" },
  { id: "e2", source: "a2", target: "b1", kind: "api", label: "API: service_role" },
  { id: "e3", source: "b1", target: "b2", kind: "network", label: "inferred: same project (backend)" },
  { id: "e4", source: "u1", target: "a1", kind: "network", label: "NETWORK: public:443" },
];

// ── Tests ───────────────────────────────────────────────────

describe("buildOverviewGroups", () => {
  it("returns one entry per group with aggregate health", () => {
    const groups = buildOverviewGroups(NODES, GROUPS);
    expect(groups).toHaveLength(3);

    const g1 = groups.find(g => g.id === "g1")!;
    expect(g1.health.total).toBe(2);
    expect(g1.health.healthy).toBe(1);
    expect(g1.health.warning).toBe(1);
    expect(g1.health.compromised).toBe(0);

    const g2 = groups.find(g => g.id === "g2")!;
    expect(g2.health.compromised).toBe(1);
    expect(g2.health.healthy).toBe(1);
  });

  it("includes node IDs for each group", () => {
    const groups = buildOverviewGroups(NODES, GROUPS);
    const g1 = groups.find(g => g.id === "g1")!;
    expect(g1.nodeIds).toEqual(["a1", "a2"]);
  });
});

describe("buildOverviewEdges", () => {
  it("returns only inter-group edges, deduplicated", () => {
    const edges = buildOverviewEdges(EDGES, NODES);
    // e1 is intra-g1, e3 is intra-g2, e2 is g1→g2, e4 is ungrouped→g1
    expect(edges.length).toBe(2);

    const sourceTargetPairs = edges.map(e => [e.sourceGroupId, e.targetGroupId].sort().join("||"));
    expect(sourceTargetPairs).toContain(["g1", "g2"].sort().join("||"));
    expect(sourceTargetPairs).toContain(["g1", "ungrouped"].sort().join("||"));
  });

  it("excludes intra-group edges", () => {
    const edges = buildOverviewEdges(EDGES, NODES);
    const intra = edges.filter(e => e.sourceGroupId === e.targetGroupId);
    expect(intra).toHaveLength(0);
  });
});

describe("buildFocusedGroupData", () => {
  it("returns only nodes in the selected group", () => {
    const data = buildFocusedGroupData("g1", NODES, EDGES);
    expect(data.nodes).toHaveLength(2);
    expect(data.nodes.map(n => n.id).sort()).toEqual(["a1", "a2"]);
  });

  it("classifies internal vs cross-group edges", () => {
    const data = buildFocusedGroupData("g1", NODES, EDGES);
    // e1 (a1→a2) is internal, e2 (a2→b1) and e4 (u1→a1) are cross-group
    expect(data.internalEdges).toHaveLength(1);
    expect(data.internalEdges[0].id).toBe("e1");
    expect(data.crossGroupEdges).toHaveLength(2);
    expect(data.crossGroupEdges.map(e => e.id).sort()).toEqual(["e2", "e4"]);
  });

  it("returns empty arrays for a group with no matching nodes", () => {
    const data = buildFocusedGroupData("nonexistent", NODES, EDGES);
    expect(data.nodes).toHaveLength(0);
    expect(data.internalEdges).toHaveLength(0);
    expect(data.crossGroupEdges).toHaveLength(0);
  });
});

describe("classifyEdge", () => {
  it("classifies shared-network edges", () => {
    expect(classifyEdge("inferred: shared network (foo)")).toBe("shared-network");
  });

  it("classifies same-project edges", () => {
    expect(classifyEdge("inferred: same project (bar)")).toBe("same-project");
  });

  it("classifies other edges", () => {
    expect(classifyEdge("API: some_role")).toBe("other");
    expect(classifyEdge("NETWORK: public:443")).toBe("other");
  });
});

describe("edge visibility rules", () => {
  it("overview mode only shows inter-group edges", () => {
    const overviewEdges = buildOverviewEdges(EDGES, NODES);
    // Verify no overview edge has same source/target group
    for (const e of overviewEdges) {
      expect(e.sourceGroupId).not.toBe(e.targetGroupId);
    }
  });

  it("focused mode includes shared-network inferred edges as internal", () => {
    const data = buildFocusedGroupData("g1", NODES, EDGES);
    const internalLabels = data.internalEdges.map(e => e.label);
    expect(internalLabels.some(l => l.includes("shared network"))).toBe(true);
  });
});

describe("topology data shapes", () => {
  it("overview groups have correct shape", () => {
    const groups = buildOverviewGroups(NODES, GROUPS);
    for (const g of groups) {
      expect(g).toHaveProperty("id");
      expect(g).toHaveProperty("kind");
      expect(g).toHaveProperty("label");
      expect(g).toHaveProperty("nodeIds");
      expect(g).toHaveProperty("health");
      expect(g.health).toHaveProperty("healthy");
      expect(g.health).toHaveProperty("warning");
      expect(g.health).toHaveProperty("compromised");
      expect(g.health).toHaveProperty("total");
    }
  });

  it("focused data has correct shape", () => {
    const data = buildFocusedGroupData("g2", NODES, EDGES);
    expect(data).toHaveProperty("nodes");
    expect(data).toHaveProperty("internalEdges");
    expect(data).toHaveProperty("crossGroupEdges");
    // Each node has groupId
    for (const n of data.nodes) {
      expect(n.groupId).toBe("g2");
    }
  });
});
