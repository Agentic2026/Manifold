import { describe, it, expect } from "vitest";
import {
  topologyToElements,
  deriveGroupsFromNodes,
  type CyNodeData,
} from "./topologyElements";
import type {
  TopologyData,
  TopologyNode,
  TopologyGroup,
} from "../../api/manifold";

// ── Fixtures ──────────────────────────────────────────────────

function makeNode(
  id: string,
  overrides: Partial<TopologyNode> = {},
): TopologyNode {
  return {
    id,
    label: id,
    serviceId: id.toUpperCase(),
    status: "healthy",
    type: "service",
    position: { x: 0, y: 0 },
    ...overrides,
  };
}

function makeData(
  nodes: TopologyNode[],
  edges: TopologyData["edges"] = [],
  groups: TopologyGroup[] = [],
): TopologyData {
  return {
    nodes,
    edges,
    groups,
    lastUpdated: new Date().toISOString(),
    scanStatus: "idle",
  };
}

// ── deriveGroupsFromNodes ─────────────────────────────────────

describe("deriveGroupsFromNodes", () => {
  it("creates groups from node groupId metadata", () => {
    const nodes = [
      makeNode("svc-a", { groupId: "net:internal", groupKind: "network", groupLabel: "internal" }),
      makeNode("svc-b", { groupId: "net:internal", groupKind: "network", groupLabel: "internal" }),
      makeNode("svc-c", { groupId: "net:public", groupKind: "network", groupLabel: "public" }),
    ];

    const { groups, nodeGroupMap } = deriveGroupsFromNodes(nodes);

    expect(groups).toHaveLength(2);
    expect(nodeGroupMap.get("svc-a")).toBe("net:internal");
    expect(nodeGroupMap.get("svc-c")).toBe("net:public");
  });

  it("falls back to project prefix from node IDs", () => {
    const nodes = [
      makeNode("myapp__web"),
      makeNode("myapp__api"),
      makeNode("other__worker"),
    ];

    const { groups, nodeGroupMap } = deriveGroupsFromNodes(nodes);

    expect(groups).toHaveLength(2);
    expect(nodeGroupMap.get("myapp__web")).toBe("proj:myapp");
    expect(nodeGroupMap.get("other__worker")).toBe("proj:other");
  });

  it("leaves ungrouped nodes without a parent", () => {
    const nodes = [makeNode("standalone")];
    const { nodeGroupMap } = deriveGroupsFromNodes(nodes);
    expect(nodeGroupMap.has("standalone")).toBe(false);
  });
});

// ── topologyToElements ────────────────────────────────────────

describe("topologyToElements", () => {
  it("creates compound nodes for groups", () => {
    const data = makeData(
      [makeNode("svc-a", { groupId: "net:int", groupKind: "network", groupLabel: "int" })],
      [],
      [{ id: "net:int", label: "int", kind: "network" }],
    );

    const elements = topologyToElements(data);
    const groupNodes = elements.filter(
      (e) => e.group === "nodes" && (e.data as CyNodeData).isGroup,
    );

    expect(groupNodes).toHaveLength(1);
    expect(groupNodes[0]!.data.id).toBe("net:int");
  });

  it("assigns service nodes as children of their group", () => {
    const data = makeData(
      [makeNode("svc-a", { groupId: "net:int", groupKind: "network", groupLabel: "int" })],
      [],
      [{ id: "net:int", label: "int", kind: "network" }],
    );

    const elements = topologyToElements(data);
    const serviceNode = elements.find(
      (e) => e.group === "nodes" && e.data.id === "svc-a",
    );

    expect(serviceNode).toBeDefined();
    expect((serviceNode!.data as CyNodeData).parent).toBe("net:int");
  });

  it("marks hidden edges with hidden-edge class", () => {
    const data = makeData(
      [makeNode("a"), makeNode("b")],
      [
        { id: "e1", source: "a", target: "b", kind: "inferred", label: "net", display: "hidden" },
        { id: "e2", source: "a", target: "b", kind: "api", label: "API", display: "visible" },
      ],
    );

    const elements = topologyToElements(data);
    const edges = elements.filter((e) => e.group === "edges");

    const hiddenEdge = edges.find((e) => e.data.id === "e1");
    const visibleEdge = edges.find((e) => e.data.id === "e2");

    expect(hiddenEdge!.classes).toContain("hidden-edge");
    expect(visibleEdge!.classes).not.toContain("hidden-edge");
  });

  it("applies status classes to service nodes", () => {
    const data = makeData([
      makeNode("a", { status: "healthy" }),
      makeNode("b", { status: "compromised" }),
    ]);

    const elements = topologyToElements(data);
    const nodeA = elements.find((e) => e.data.id === "a");
    const nodeB = elements.find((e) => e.data.id === "b");

    expect(nodeA!.classes).toContain("status-healthy");
    expect(nodeB!.classes).toContain("status-compromised");
  });

  it("derives groups from node IDs when no groups provided", () => {
    const data = makeData([
      makeNode("proj__web"),
      makeNode("proj__api"),
    ]);
    // No groups in data

    const elements = topologyToElements(data);
    const groupNodes = elements.filter(
      (e) => e.group === "nodes" && (e.data as CyNodeData).isGroup,
    );

    expect(groupNodes).toHaveLength(1);
    expect(groupNodes[0]!.data.id).toBe("proj:proj");
  });

  it("handles dense topology with many nodes and groups", () => {
    const groups: TopologyGroup[] = [
      { id: "net:frontend", label: "frontend", kind: "network" },
      { id: "net:backend", label: "backend", kind: "network" },
      { id: "net:data", label: "data", kind: "network" },
    ];

    const nodes: TopologyNode[] = [];
    for (let i = 0; i < 30; i++) {
      const gIdx = i % 3;
      const group = groups[gIdx]!;
      nodes.push(
        makeNode(`svc-${i}`, {
          groupId: group.id,
          groupKind: group.kind,
          groupLabel: group.label,
        }),
      );
    }

    const data = makeData(nodes, [], groups);
    const elements = topologyToElements(data);

    const groupElements = elements.filter(
      (e) => e.group === "nodes" && (e.data as CyNodeData).isGroup,
    );
    const serviceElements = elements.filter(
      (e) => e.group === "nodes" && !(e.data as CyNodeData).isGroup,
    );

    expect(groupElements).toHaveLength(3);
    expect(serviceElements).toHaveLength(30);

    // Every service node should have a parent
    for (const el of serviceElements) {
      expect((el.data as CyNodeData).parent).toBeDefined();
    }
  });
});
