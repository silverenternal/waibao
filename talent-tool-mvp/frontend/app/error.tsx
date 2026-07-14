"use client";

/**
 * T5006 — Route-segment error boundary.
 *
 * Next.js renders this automatically when any server/client component in the
 * closest segment (or below) throws during render. It must be a Client
 * Component and export `error` + `reset` handlers.
 */

import * as React from "react";
import { AlertTriangle, RotateCcw, Home } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    console.error("[route-error]", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 px-4 py-16 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
        <AlertTriangle className="h-8 w-8 text-destructive" aria-hidden />
      </div>
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">
          This page hit an error
        </h1>
        <p className="max-w-md text-sm text-muted-foreground">
          {error.message ||
            "An unexpected error occurred while loading this page. You can try again, or head back home."}
        </p>
        {error.digest ? (
          <p className="font-mono text-xs text-muted-foreground/70">
            error digest: {error.digest}
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button onClick={reset}>
          <RotateCcw className="mr-1.5 h-4 w-4" />
          Try again
        </Button>
        <Button variant="outline" asChild>
          <Link href="/">
            <Home className="mr-1.5 h-4 w-4" />
            Back home
          </Link>
        </Button>
      </div>
    </div>
  );
}
