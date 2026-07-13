"use client";

import { useEffect, useState } from "react";
import apiV2 from "@/lib/api-v2";

/**
 * Renders a non-blocking banner listing which API v1 routes the current
 * component (or page) uses, and points users at the v2 equivalents.
 *
 * Drop one in anywhere that still imports from `@/lib/api-v1`:
 *
 *     <DeprecatedVersionBanner surface="CandidateMatchTable" routes={["/candidates"]} />
 *
 * The banner *also* self-discovers deprecation timeline via
 * :func:`apiV2.manifest` so it can render the dynamic sunset date.
 */
type Manifest = {
  current: string;
  recommended: string;
  deprecated: string[];
  versions: Array<{
    version: string;
    status: string;
    sunset_at: string | null;
    successor: string | null;
    is_recommended?: boolean;
  }>;
};

export interface DeprecatedVersionBannerProps {
  /** Symbolic name to display (page or component label). */
  surface: string;
  /** The v1 path prefixes the consumer still relies on. */
  routes: string[];
  /** Class additions for the wrapping element. */
  className?: string;
}

export function DeprecatedVersionBanner({
  surface,
  routes,
  className = "",
}: DeprecatedVersionBannerProps) {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiV2
      .manifest()
      .then((m: Manifest) => {
        if (!cancelled) setManifest(m);
      })
      .catch(() => {
        /* offline — manifest unavailable; banner still works */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const storageKey = `deprecation-banner:${surface}`;
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.localStorage.getItem(storageKey) === "1") setDismissed(true);
  }, [storageKey]);

  if (dismissed) return null;

  const sunset =
    manifest?.versions.find((v: Manifest["versions"][number]) => v.version === "v1")?.sunset_at ?? null;

  function dismiss() {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(storageKey, "1");
    }
    setDismissed(true);
  }

  return (
    <aside
      role="status"
      className={
        "flex flex-wrap items-start gap-3 rounded-md border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-100 " +
        className
      }
    >
      <div className="flex-1 space-y-1">
        <p className="font-medium">
          {surface} 仍在使用 API v1 — 请迁移到 v2。
        </p>
        <ul className="ml-4 list-disc space-y-0.5 text-xs">
          {routes.map((r) => (
            <li key={r}>
              <code>{r}</code> &rarr;{" "}
              <code className="text-emerald-700 dark:text-emerald-300">
                /api/v2{r}
              </code>
            </li>
          ))}
        </ul>
        {sunset ? (
          <p className="text-xs">
            <strong>Sunset:</strong> {sunset}. 之后 v1 将返回 410 Gone。
          </p>
        ) : null}
      </div>
      <button
        type="button"
        onClick={dismiss}
        className="rounded-md bg-amber-900 px-3 py-1 text-xs text-amber-50 hover:bg-amber-700"
      >
        Dismiss
      </button>
    </aside>
  );
}

export default DeprecatedVersionBanner;
