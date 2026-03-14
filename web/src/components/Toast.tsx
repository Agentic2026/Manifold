import { CheckCircle2, XCircle, AlertTriangle, Info, X } from "lucide-react";
import { useToast, type ToastVariant } from "../context/ToastContext";
import { cn } from "../lib/utils";

const VARIANT_CONFIG: Record<
  ToastVariant,
  { icon: React.ElementType; border: string; iconColor: string; progress: string }
> = {
  success: {
    icon: CheckCircle2,
    border: "border-l-healthy",
    iconColor: "text-healthy",
    progress: "bg-healthy",
  },
  error: {
    icon: XCircle,
    border: "border-l-compromised",
    iconColor: "text-compromised",
    progress: "bg-compromised",
  },
  warning: {
    icon: AlertTriangle,
    border: "border-l-suspicious",
    iconColor: "text-suspicious",
    progress: "bg-suspicious",
  },
  info: {
    icon: Info,
    border: "border-l-primary",
    iconColor: "text-primary",
    progress: "bg-primary",
  },
};

export function ToastContainer() {
  const { toasts, removeToast } = useToast();

  return (
    <div className="fixed bottom-4 right-20 z-[60] flex flex-col-reverse gap-2 pointer-events-none">
      {toasts.map((toast) => {
        const config = VARIANT_CONFIG[toast.variant];
        const Icon = config.icon;
        return (
          <div
            key={toast.id}
            className={cn(
              "pointer-events-auto min-w-[320px] max-w-[400px] bg-surface-raised border border-border border-l-4 rounded-xl shadow-lg overflow-hidden",
              "animate-[slide-in-right_0.3s_ease-out]",
              config.border,
            )}
          >
            <div className="flex items-start gap-3 p-3">
              <Icon className={cn("w-5 h-5 flex-shrink-0 mt-0.5", config.iconColor)} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-text">{toast.title}</p>
                {toast.description && (
                  <p className="text-xs text-text-muted mt-0.5">{toast.description}</p>
                )}
              </div>
              <button
                onClick={() => removeToast(toast.id)}
                className="p-0.5 rounded hover:bg-surface-alt transition-colors text-text-muted hover:text-text flex-shrink-0"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="h-0.5 w-full bg-border">
              <div
                className={cn("h-full animate-[shrink-width_5s_linear_forwards]", config.progress)}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
