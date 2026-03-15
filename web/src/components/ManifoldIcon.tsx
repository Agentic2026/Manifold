import type { SVGProps } from "react";

/**
 * Canonical Manifold brand icon.
 *
 * Renders inline so it inherits `currentColor` and can be styled via
 * className / standard SVG props just like a lucide icon.
 */
export function ManifoldIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="32"
      height="32"
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="Manifold"
      {...props}
    >
      <rect width="32" height="32" rx="8" fill="currentColor" opacity="0.1" />
      <path
        d="M8 24V8l8 10 8-10v16"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="16" cy="14" r="2" fill="currentColor" opacity="0.5" />
    </svg>
  );
}
