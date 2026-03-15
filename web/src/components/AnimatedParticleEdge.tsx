import {
  type EdgeProps,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
} from "@xyflow/react";

interface ParticleEdgeData {
  kind: "network" | "api";
  label: string;
  sourceStatus?: string;
  targetStatus?: string;
  [key: string]: unknown;
}

export function AnimatedParticleEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const d = data as ParticleEdgeData | undefined;
  const isApi = d?.kind === "api";
  const isCompromised =
    d?.sourceStatus === "compromised" || d?.targetStatus === "compromised";
  const isWarning =
    d?.sourceStatus === "warning" || d?.targetStatus === "warning";

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  // Particle configuration
  const particleColor = isCompromised
    ? "var(--color-compromised)"
    : isWarning
      ? "var(--color-suspicious)"
      : "var(--color-monitoring)";
  const particleCount = isCompromised ? 5 : isWarning ? 3 : 2;
  const duration = isCompromised ? 1.5 : isWarning ? 2.5 : 3;
  const particleSize = isCompromised ? 3 : 2;

  // Generate staggered particles
  const particles = Array.from({ length: particleCount }, (_, i) => ({
    key: `${id}-p${i}`,
    delay: (i * duration) / particleCount,
  }));

  return (
    <>
      {/* Glow filter definition */}
      <svg style={{ position: "absolute", width: 0, height: 0 }}>
        <defs>
          <filter id={`glow-${id}`}>
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
      </svg>

      {/* Base edge line */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: isCompromised
            ? "var(--color-compromised)"
            : isApi
              ? "var(--color-primary)"
              : "var(--color-border)",
          strokeWidth: isCompromised ? 2 : isApi ? 1.5 : 1,
          strokeDasharray: isApi ? "6 3" : undefined,
          opacity: isCompromised ? 0.5 : 0.75,
        }}
      />

      {/* Animated particles */}
      {particles.map(({ key, delay }) => (
        <circle
          key={key}
          r={particleSize}
          fill={particleColor}
          filter={isCompromised ? `url(#glow-${id})` : undefined}
          opacity={0.9}
        >
          <animateMotion
            dur={`${duration}s`}
            repeatCount="indefinite"
            begin={`${delay}s`}
            path={edgePath}
          />
        </circle>
      ))}

      {/* Edge label */}
      {d?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
            className="absolute nodrag nopan"
          >
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-surface-raised border border-border text-text-muted shadow-sm whitespace-nowrap">
              {d.label}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
