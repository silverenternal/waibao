"use client";

/**
 * T5006 — Reusable class-based ErrorBoundary.
 *
 * Use this to wrap page-level content so a render-time error in one route
 * segment never crashes the whole shell. For route-segment errors Next.js
 * `error.tsx` is preferred (it integrates with the router); this component is
 * for fine-grained boundaries (e.g. a heavy widget, a third-party chart) and
 * for the page-level wrapping applied across the app.
 *
 *   <ErrorBoundary fallback={<ErrorFallback />}>
 *     <SomeRiskyWidget />
 *   </ErrorBoundary>
 */

import * as React from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Optional custom fallback. Receives the error and a reset callback. */
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
  /** Called whenever an error is captured (logging / telemetry). */
  onError?: (error: Error, info: React.ErrorInfo) => void;
  /** Reset the boundary when this value changes (e.g. route key). */
  resetKeys?: unknown[];
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Default inline fallback UI — self-contained so callers get a sensible
 * default without importing anything extra. Mirrors the visual language of
 * app/error.tsx for consistency.
 */
export function ErrorFallback({
  error,
  onReset,
}: {
  error: Error;
  onReset?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-destructive/40 bg-destructive/5 p-8 text-center"
    >
      <AlertTriangle className="h-10 w-10 text-destructive" aria-hidden />
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">Something went wrong</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          {error.message ||
            "An unexpected error occurred while rendering this section."}
        </p>
      </div>
      {onReset ? (
        <Button variant="outline" size="sm" onClick={onReset}>
          <RotateCcw className="mr-1.5 h-4 w-4" />
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // Forward to optional observer (telemetry). Console keeps a dev trail.
    console.error("[ErrorBoundary]", error, info.componentStack);
    this.props.onError?.(error, info);
  }

  override componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    // If any resetKey changed after an error, auto-recover.
    if (this.state.error && prevProps.resetKeys !== this.props.resetKeys) {
      const prev = prevProps.resetKeys ?? [];
      const next = this.props.resetKeys ?? [];
      if (
        prev.length !== next.length ||
        prev.some((v, i) => !Object.is(v, next[i]))
      ) {
        this.reset();
      }
    }
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  override render(): React.ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    return <ErrorFallback error={error} onReset={this.reset} />;
  }
}

export default ErrorBoundary;
