import { describe, it, expect } from "vitest";
import {
  topologyToElements,
  deriveGroupsFromNodes,
  type CyNodeData,
  type CyEdgeData,
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

// ── Edge visibility — overview mode ───────────────────────────

describe("topologyToElements edge visibility (overview)", () => {
  const groups: TopologyGroup[] = [
    { id: "net:int", label: "internal", kind: "network" },
    { id: "net:pub", label: "public", kind: "network" },
  ];

  function makeGroupedData(
    edges: TopologyData["edges"],
  ): TopologyData {
    return makeData(
      [
        makeNode("a", { groupId: "net:int", groupKind: "network", groupLabel: "internal" }),
        makeNode("b", { groupId: "net:int", groupKind: "network", groupLabel: "internal" }),
        makeNode("c", { groupId: "net:pub", groupKind: "network", groupLabel: "public" }),
      ],
      edges,
      groups,
    );
  }

  it("regression: inferred intra-group shared-network edges are NOT hidden", () => {
    const data = makeGroupedData([
      {
        id: "e1",
        source: "a",
        target: "b",
        kind: "inferred",
        label: "inferred: shared network (int_default)",
        display: "visible",
        inferredSubtype: "shared_network",
      },
    ]);

    const elements = topologyToElements(data);
    const edge = elements.find((e) => e.data.id === "e1");

    expect(edge!.classes).not.toContain("hidden-edge");
    expect(edge!.classes).toContain("inferred-network");
  });

  it("same-project-only inferred edges are hidden in overview", () => {
    const data = makeGroupedData([
      {
        id: "e1",
        source: "a",
        target: "b",
        kind: "inferred",
        label: "inferred: same project (myapp)",
        display: "hidden",
        inferredSubtype: "same_project",
      },
    ]);

    const elements = topologyToElements(data);
    const edge = elements.find((e) => e.data.id === "e1");

    expect(edge!.classes).toContain("hidden-edge");
  });

  it("cross-group inferred edges are visible in overview", () => {
    const data = makeGroupedData([
      {
        id: "e1",
        source: "a",
        target: "c",
        kind: "inferred",
        label: "inferred: shared network (bridge)",
        display: "visible",
        inferredSubtype: "shared_network",
      },
    ]);

    const elements = topologyToElements(data);
    const edge = elements.find((e) => e.data.id === "e1");

    expect(edge!.classes).not.toContain("hidden-edge");
    expect(edge!.classes).not.toContain("focus-dimmed");
  });

  it("declared/API edges are always visible in overview", () => {
    const data = makeGroupedData([
      {
        id: "e1",
        source: "a",
        target: "b",
        kind: "api",
        label: "API call",
        display: "visible",
      },
    ]);

    const elements = topologyToElements(data);
    const edge = elements.find((e) => e.data.id === "e1");

    expect(edge!.classes).not.toContain("hidden-edge");
    expect(edge!.classes).toContain("kind-api");
  });

  it("includes inferredSubtype in edge data", () => {
    const data = makeGroupedData([
      {
        id: "e1",
        source: "a",
        target: "b",
        kind: "inferred",
        label: "shared network",
        display: "visible",
        inferredSubtype: "shared_network",
      },
    ]);

    const elements = topologyToElements(data);
    const edge = elements.find((e) => e.data.id === "e1");
    expect((edge!.data as CyEdgeData).inferredSubtype).toBe("shared_network");
  });
});

// ── Edge visibility — focused group mode ──────────────────────

describe("topologyToElements focused group mode", () => {
  const groups: TopologyGroup[] = [
    { id: "net:int", label: "internal", kind: "network" },
    { id: "net:pub", label: "public", kind: "network" },
  ];

  function makeGroupedData(
    edges: TopologyData["edges"],
  ): TopologyData {
    return makeData(
      [
        makeNode("a", { groupId: "net:int", groupKind: "network", groupLabel: "internal" }),
        makeNode("b", { groupId: "net:int", groupKind: "network", groupLabel: "internal" }),
        makeNode("c", { groupId: "net:pub", groupKind: "network", groupLabel: "public" }),
      ],
      edges,
      groups,
    );
  }

  it("dims unrelated groups and nodes when a group is focused", () => {
    const data = makeGroupedData([]);
    const elements = topologyToElements(data, "net:int");

    const focusedGroup = elements.find((e) => e.data.id === "net:int");
    const otherGroup = elements.find((e) => e.data.id === "net:pub");
    const internalNode = elements.find((e) => e.data.id === "a");
    const externalNode = elements.find((e) => e.data.id === "c");

    expect(focusedGroup!.classes).not.toContain("focus-dimmed");
    expect(otherGroup!.classes).toContain("focus-dimmed");
    expect(internalNode!.classes).not.toContain("focus-dimmed");
    expect(externalNode!.classes).toContain("focus-dimmed");
  });

  it("shows internal edges in focused group", () => {
    const data = makeGroupedData([
      {
        id: "e1",
        source: "a",
        target: "b",
        kind: "inferred",
        label: "inferred: same project (myapp)",
        display: "hidden",
        inferredSubtype: "same_project",
      },
    ]);

    const elements = topologyToElements(data, "net:int");
    const edge = elements.find((e) => e.data.id === "e1");

    // In focused mode, internal edges are visible (no hidden-edge, no focus-dimmed)
    expect(edge!.classes).not.toContain("hidden-edge");
    expect(edge!.classes).not.toContain("focus-dimmed");
    expect(edge!.classes).toContain("inferred-project");
  });

  it("shows cross-group edges touching focused group", () => {
    const data = makeGroupedData([
      {
        id: "e1",
        source: "a",
        target: "c",
        kind: "inferred",
        label: "inferred: shared network (bridge)",
        display: "visible",
        inferredSubtype: "shared_network",
      },
    ]);

    const elements = topologyToElements(data, "net:int");
    const edge = elements.find((e) => e.data.id === "e1");

    expect(edge!.classes).not.toContain("focus-dimmed");
  });

  it("dims edges unrelated to focused group", () => {
    // Create a third group for a truly unrelated edge
    const threeGroups: TopologyGroup[] = [
      { id: "net:a", label: "A", kind: "network" },
      { id: "net:b", label: "B", kind: "network" },
      { id: "net:c", label: "C", kind: "network" },
    ];

    const data = makeData(
      [
        makeNode("n1", { groupId: "net:a", groupKind: "network", groupLabel: "A" }),
        makeNode("n2", { groupId: "net:b", groupKind: "network", groupLabel: "B" }),
        makeNode("n3", { groupId: "net:c", groupKind: "network", groupLabel: "C" }),
      ],
      [
        {
          id: "e-unrelated",
          source: "n2",
          target: "n3",
          kind: "inferred",
          label: "inferred: shared network (x)",
          display: "visible",
          inferredSubtype: "shared_network",
        },
      ],
      threeGroups,
    );

    const elements = topologyToElements(data, "net:a");
    const edge = elements.find((e) => e.data.id === "e-unrelated");

    expect(edge!.classes).toContain("focus-dimmed");
  });

  it("All groups mode (null) resets to overview behavior", () => {
    const data = makeGroupedData([
      {
        id: "e1",
        source: "a",
        target: "b",
        kind: "inferred",
        label: "inferred: shared network (int_default)",
        display: "visible",
        inferredSubtype: "shared_network",
      },
    ]);

    const elements = topologyToElements(data, null);

    // No dimming in overview mode
    const allClasses = elements.map((e) => e.classes ?? "").join(" ");
    expect(allClasses).not.toContain("focus-dimmed");
  });
});
