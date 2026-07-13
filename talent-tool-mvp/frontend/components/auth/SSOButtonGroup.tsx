"use client";

/**
 * T2901 — Renders a list of SSO providers as a stack of :class:`SSOButton`s.
 *
 * The list is fetched from the backend, so adding a new IdP on the
 * backend is automatically surfaced in the UI without rebuilding the
 * frontend.
 */

import { useEffect, useState } from "react";
import { SSOButton } from "./SSOButton";
import { listSSOProviders, type SSOProviderMeta } from "@/lib/auth-sso";

export interface SSOButtonGroupProps {
  /** Where to send the user after a successful login. */
  relayState?: string;
  /** Pre-fetched providers — useful in tests. If omitted we fetch on mount. */
  providers?: SSOProviderMeta[];
  /** When false, hide providers in the "cn" category. */
  showCNProviders?: boolean;
}

export function SSOButtonGroup({
  relayState,
  providers: initialProviders,
  showCNProviders = true,
}: SSOButtonGroupProps) {
  const [providers, setProviders] = useState<SSOProviderMeta[] | null>(
    initialProviders ?? null
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialProviders) return;
    let cancelled = false;
    listSSOProviders()
      .then((list) => {
        if (!cancelled) setProviders(list);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Failed to load SSO providers");
      });
    return () => { cancelled = true; };
  }, [initialProviders]);

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
        {error}
      </div>
    );
  }
  if (!providers) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-[78px] rounded-xl bg-white/5 border border-white/5 animate-pulse"
          />
        ))}
      </div>
    );
  }
  const filtered = providers.filter(
    (p) => p.enabled && (showCNProviders || p.category !== "cn")
  );
  if (filtered.length === 0) return null;

  return (
    <div className="space-y-3" data-testid="sso-button-group">
      {filtered.map((p) => (
        <SSOButton key={p.slug} provider={p} relayState={relayState} />
      ))}
    </div>
  );
}

export default SSOButtonGroup;
