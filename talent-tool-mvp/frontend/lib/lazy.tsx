/**
 * lazy.tsx — route & heavy-component lazy loading helpers.
 *
 * Code-splitting strategy (Lighthouse "Reduce JavaScript execution time"):
 *   - Charts (recharts/tremor), editors (react-flow, react-markdown) and
 *     the RAG/voice canvases are heavy. Import them via {@link lazyChart},
 *     {@link lazyHeavy} so they ship in a separate chunk and only hydrate
 *     when scrolled into view.
 *   - Provide a skeleton fallback so CLS stays low.
 *
 * Usage:
 *   const SalaryChart = lazyChart(() => import("@/components/SalaryChart"));
 *   <SalaryChart />
 */
import dynamic from "next/dynamic";
import * as React from "react";
import { cn } from "@/lib/utils";

function Skeleton({ className }: { className?: string }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading"
      className={cn(
        "animate-pulse rounded-lg bg-muted/60",
        "min-h-[120px] w-full",
        className,
      )}
    />
  );
}

export interface LazyOptions {
  /** Custom loading fallback. Defaults to a muted skeleton block. */
  loading?: React.ComponentType;
  /** Render only on the client (skip SSR). Useful for canvas/voice. */
  ssr?: boolean;
}

/**
 * Generic lazy wrapper for heavy components. Prefer the named helpers
 * below for semantic clarity.
 */
export function lazyHeavy<P extends object>(
  loader: () => Promise<{ default: React.ComponentType<P> }>,
  opts: LazyOptions = {},
) {
  return dynamic(loader, {
    loading: () => {
      const F = opts.loading ?? Skeleton;
      return <F />;
    },
    ssr: opts.ssr ?? true,
  });
}

/** Lazy wrapper tuned for chart components (taller skeleton). */
export function lazyChart<P extends object>(
  loader: () => Promise<{ default: React.ComponentType<P> }>,
) {
  return dynamic(loader, {
    loading: () => <Skeleton className="min-h-[260px]" />,
    ssr: true,
  });
}

/** Client-only lazy wrapper (canvas, voice, recorder). */
export function lazyClient<P extends object>(
  loader: () => Promise<{ default: React.ComponentType<P> }>,
) {
  return dynamic(loader, {
    loading: () => <Skeleton />,
    ssr: false,
  });
}

export { Skeleton };
