"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error" | "info" | "warning";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastOptions {
  type?: ToastType;
  /** 自动消失时间，毫秒；传 0 表示不自动关闭 */
  duration?: number;
  /** 右侧行动按钮，例如「去查看」「重试」 */
  action?: ToastAction;
}

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
  action?: ToastAction;
  leaving?: boolean;
}

interface ToastContextValue {
  toast: (message: string, typeOrOptions?: ToastType | ToastOptions) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast 必须用在 <ToastProvider> 内");
  return ctx;
}

const ICONS: Record<ToastType, React.ReactNode> = {
  success: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 shrink-0">
      <path d="m9 12 2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="9" />
    </svg>
  ),
  error: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 shrink-0">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v4M12 16h.01" strokeLinecap="round" />
    </svg>
  ),
  warning: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 shrink-0">
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" strokeLinejoin="round" />
      <path d="M12 9v4M12 17h.01" strokeLinecap="round" />
    </svg>
  ),
  info: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 shrink-0">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 16v-4M12 8h.01" strokeLinecap="round" />
    </svg>
  ),
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);
  const timers = React.useRef<Map<number, ReturnType<typeof setTimeout>[]>>(
    new Map()
  );

  const dismiss = React.useCallback((id: number) => {
    setToasts((t) => t.map((x) => (x.id === id ? { ...x, leaving: true } : x)));
    const tm = setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id));
    }, 180);
    timers.current.set(id, [...(timers.current.get(id) || []), tm]);
  }, []);

  const toast = React.useCallback(
    (message: string, typeOrOptions: ToastType | ToastOptions = "info") => {
      const opts: ToastOptions =
        typeof typeOrOptions === "string" ? { type: typeOrOptions } : typeOrOptions;
      const type = opts.type ?? "info";
      // 需求：默认 3 秒自动消失；带操作按钮的给到 5 秒，避免来不及点
      const duration =
        opts.duration ?? (opts.action ? 5000 : 3000);
      const id = Date.now() + Math.random();
      setToasts((t) => [...t.slice(-3), { id, type, message, action: opts.action }]);
      if (duration > 0) {
        const tm = setTimeout(() => dismiss(id), duration);
        timers.current.set(id, [...(timers.current.get(id) || []), tm]);
      }
    },
    [dismiss]
  );

  React.useEffect(() => {
    const map = timers.current;
    return () => {
      map.forEach((list) => list.forEach((t) => clearTimeout(t)));
      map.clear();
    };
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              "pointer-events-auto flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-sm shadow-lg backdrop-blur",
              "transition-all duration-200 ease-out",
              t.leaving ? "translate-x-2 opacity-0" : "animate-toast-in",
              t.type === "success" &&
                "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
              t.type === "error" &&
                "border-destructive/40 bg-destructive/10 text-destructive",
              t.type === "warning" &&
                "border-amber-500/40 bg-amber-500/10 text-amber-300",
              t.type === "info" && "border-border bg-card text-card-foreground"
            )}
          >
            <span className="mt-0.5">{ICONS[t.type]}</span>
            <span className="min-w-0 flex-1 break-words leading-relaxed">
              {t.message}
            </span>
            {t.action ? (
              <button
                type="button"
                onClick={() => {
                  t.action?.onClick();
                  dismiss(t.id);
                }}
                className="shrink-0 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium underline underline-offset-2 transition-colors hover:bg-white/10"
              >
                {t.action.label}
              </button>
            ) : null}
            <button
              type="button"
              aria-label="关闭"
              onClick={() => dismiss(t.id)}
              className="shrink-0 rounded-md p-0.5 opacity-50 transition-opacity hover:opacity-100"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
                <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
