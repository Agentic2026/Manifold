import { useEffect, useState, useRef } from "react";
import { cn } from "../lib/utils";

interface SecurityGaugeProps {
  score: number; // 0–100
  breakdown?: { label: string; impact: number }[];
}

export function SecurityGauge({ score, breakdown }: SecurityGaugeProps) {
  const [displayScore, setDisplayScore] = useState(0);
  const [mounted, setMounted] = useState(false);
  const rafRef = useRef<number>(0);

  // Animate score count-up
  useEffect(() => {
    setMounted(true);
    const start = performance.now();
    const duration = 1200;
    const from = 0;
    const to = score;

    function tick(now: number) {
      const elapsed = now - start;
      const t = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplayScore(Math.round(from + (to - from) * eased));
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [score]);

  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (displayScore / 100) * circumference;

  const color =
    score >= 80
      ? "var(--color-healthy)"
      : score >= 50
        ? "var(--color-suspicious)"
        : "var(--color-compromised)";

  const label =
    score >= 80 ? "Secure" : score >= 50 ? "At Risk" : "Critical";

  return (
    <div className="group relative flex flex-col items-center px-4 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted mb-2">
        Security Posture
      </p>
      <div className="relative w-[96px] h-[96px]">
        <svg viewBox="0 0 96 96" className="w-full h-full -rotate-90">
          {/* Background circle */}
          <circle
            cx="48"
            cy="48"
            r={radius}
            fill="none"
            stroke="var(--color-border)"
            strokeWidth="7"
          />
          {/* Score arc */}
          <circle
            cx="48"
            cy="48"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={mounted ? offset : circumference}
            style={{ transition: "stroke-dashoffset 1.2s ease-out, stroke 0.5s ease" }}
          />
        </svg>
        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="text-2xl font-bold tabular-nums"
            style={{ color }}
          >
            {displayScore}
          </span>
          <span className="text-[9px] text-text-muted font-medium">/100</span>
        </div>
      </div>
      <span
        className="mt-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full"
        style={{
          color,
          backgroundColor: `color-mix(in srgb, ${color} 10%, transparent)`,
          border: `1px solid color-mix(in srgb, ${color} 20%, transparent)`,
        }}
      >
        {label}
      </span>

      {/* Hover tooltip breakdown */}
      {breakdown && breakdown.length > 0 && (
        <div className="absolute left-full top-0 ml-2 w-52 bg-surface-raised border border-border rounded-lg shadow-lg p-3 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50">
          <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2">
            Score Breakdown
          </p>
          <div className="space-y-1">
            {breakdown.map((item) => (
              <div key={item.label} className="flex items-center justify-between text-[11px]">
                <span className="text-text-muted">{item.label}</span>
                <span
                  className={cn(
                    "font-mono font-semibold",
                    item.impact < 0 ? "text-compromised" : "text-healthy",
                  )}
                >
                  {item.impact > 0 ? "+" : ""}
                  {item.impact}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
