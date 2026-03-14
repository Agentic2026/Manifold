import { HTMLAttributes, forwardRef } from "react";
import { cn } from "../lib/utils";

export interface BadgeProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "outline" | "destructive";
}

const variants = {
  default:
    "border-transparent bg-primary text-white hover:bg-primary-hover shadow-sm",
  secondary:
    "border-transparent bg-surface-alt text-text hover:bg-border shadow-sm",
  destructive:
    "border-transparent bg-danger text-white hover:bg-danger-hover shadow-sm",
  outline: "text-text border-border",
};

const Badge = forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant = "default", ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "inline-flex items-center rounded-lg border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
          variants[variant],
          className,
        )}
        {...props}
      />
    );
  },
);
Badge.displayName = "Badge";

export { Badge };
