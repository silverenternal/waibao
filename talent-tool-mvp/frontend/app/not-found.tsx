import Link from "next/link";
import { Home, Search } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * T5006 — Root 404 page.
 *
 * Rendered by Next.js whenever no route matches. Kept as a Server Component
 * (no "use client") so it works for deeply nested unmatched segments too.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center gap-6 px-4 py-16 text-center">
      <div className="space-y-2">
        <p className="text-6xl font-extrabold tracking-tight text-primary sm:text-7xl">
          404
        </p>
        <h1 className="text-2xl font-bold tracking-tight">Page not found</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          The page you are looking for doesn&apos;t exist or may have been moved.
          Check the URL or head back to safety.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button asChild>
          <Link href="/">
            <Home className="mr-1.5 h-4 w-4" />
            Back home
          </Link>
        </Button>
        <Button variant="outline" asChild>
          <Link href="/match">
            <Search className="mr-1.5 h-4 w-4" />
            Browse matches
          </Link>
        </Button>
      </div>
    </div>
  );
}
