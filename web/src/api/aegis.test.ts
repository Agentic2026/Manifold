import { describe, it, expect, vi, beforeEach } from "vitest";

// ── mock global fetch ──────────────────────────────────────
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Import AFTER stubbing fetch
const { aegisApi } = await import("../api/aegis");

beforeEach(() => {
  mockFetch.mockReset();
});

describe("aegisApi.getTopology", () => {
  it("returns live data when the backend responds", async () => {
    const liveData = {
      nodes: [{ id: "svc", label: "Service", serviceId: "svc", status: "healthy", type: "service", position: { x: 0, y: 0 } }],
      edges: [],
      lastUpdated: new Date().toISOString(),
      scanStatus: "idle",
    };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => liveData,
    });

    const result = await aegisApi.getTopology();
    expect(result).toEqual(liveData);
    expect(result!.nodes[0]?.id).toBe("svc");
  });

  it("returns null (not mock data) when backend is unreachable in live mode", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    const result = await aegisApi.getTopology();
    expect(result).toBeNull();
  });

  it("returns mock data only when explicitly requested", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    const result = await aegisApi.getTopology({ useMock: true });
    expect(result).not.toBeNull();
    expect(result!.nodes.length).toBeGreaterThan(0);
  });
});

describe("NodeTelemetry optional fields", () => {
  it("handles null latencyMs and errorRate in topology response", async () => {
    const liveData = {
      nodes: [{
        id: "svc",
        label: "Service",
        serviceId: "svc",
        status: "healthy",
        type: "service",
        position: { x: 0, y: 0 },
        telemetry: {
          ingressMbps: 1.5,
          egressMbps: 2.3,
          latencyMs: null,
          errorRate: null,
          lastSeen: new Date().toISOString(),
        },
      }],
      edges: [],
      lastUpdated: new Date().toISOString(),
      scanStatus: "idle",
    };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => liveData,
    });

    const result = await aegisApi.getTopology();
    expect(result).not.toBeNull();
    const node = result!.nodes[0];
    expect(node?.telemetry?.ingressMbps).toBe(1.5);
    expect(node?.telemetry?.latencyMs).toBeNull();
    expect(node?.telemetry?.errorRate).toBeNull();
    expect(node?.telemetry?.lastSeen).toBeDefined();
  });
});
