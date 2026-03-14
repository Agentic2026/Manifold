import { InputHTMLAttributes, forwardRef, useCallback, useId, useRef, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "../lib/utils";
import { Label } from "./Label";

export interface PasswordFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
  error?: string;
}

const PasswordField = forwardRef<HTMLInputElement, PasswordFieldProps>(
  ({ className, label, error, id, ...props }, forwardedRef) => {
    const [visible, setVisible] = useState(false);
    const internalRef = useRef<HTMLInputElement | null>(null);
    const generatedId = useId();
    const inputId = id || generatedId;
    const errorId = `${inputId}-error`;

    // Merge forwarded ref with our internal ref
    const setRefs = useCallback(
      (node: HTMLInputElement | null) => {
        internalRef.current = node;
        if (typeof forwardedRef === "function") {
          forwardedRef(node);
        } else if (forwardedRef) {
          forwardedRef.current = node;
        }
      },
      [forwardedRef],
    );

    const handleToggle = useCallback(() => {
      const input = internalRef.current;
      if (!input) {
        setVisible((v) => !v);
        return;
      }

      // Capture caret/selection before the type change
      const start = input.selectionStart;
      const end = input.selectionEnd;
      const dir = input.selectionDirection;

      setVisible((v) => !v);

      // Restore focus + selection after React re-renders
      requestAnimationFrame(() => {
        input.focus();
        try {
          input.setSelectionRange(start, end, dir ?? undefined);
        } catch {
          // setSelectionRange throws on some input types in certain browsers
          // (e.g. mobile Safari). Safe to ignore since focus is still restored.
        }
      });
    }, []);

    // Prevent pointer-down from stealing focus from the input
    const handlePointerDown = useCallback(
      (e: React.PointerEvent | React.MouseEvent) => {
        e.preventDefault();
      },
      [],
    );

    const Icon = visible ? Eye : EyeOff;

    return (
      <div className="space-y-2">
        {label && <Label htmlFor={inputId}>{label}</Label>}
        <div className="relative">
          <input
            id={inputId}
            ref={setRefs}
            type={visible ? "text" : "password"}
            spellCheck={false}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            className={cn(
              "flex h-10 w-full rounded-xl border border-border bg-surface px-3 py-2 pr-10 text-sm ring-offset-surface placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
              error && "border-danger focus-visible:ring-danger",
              className,
            )}
            {...props}
          />
          <button
            type="button"
            aria-label={visible ? "Hide password" : "Show password"}
            aria-pressed={visible}
            onClick={handleToggle}
            onPointerDown={handlePointerDown}
            onMouseDown={handlePointerDown}
            className="absolute right-0 top-0 flex h-10 w-10 items-center justify-center text-text-muted hover:text-text transition-colors disabled:pointer-events-none disabled:opacity-50"
            disabled={props.disabled}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        {error && (
          <p id={errorId} className="text-sm text-danger">
            {error}
          </p>
        )}
      </div>
    );
  },
);
PasswordField.displayName = "PasswordField";

export { PasswordField };
