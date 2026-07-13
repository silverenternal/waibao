"use client";

/**
 * v7.0 T3003 — WhiteLabelProvider
 *
 * Loads the tenant's branding record at mount, pushes the values into
 * CSS variables, and exposes a context so any component can read the
 * current branding without re-fetching.
 *
 * Usage (app/layout.tsx):
 *   <WhiteLabelProvider tenantId={tenantId}>
 *     <ThemeProvider>{children}</ThemeProvider>
 *   </WhiteLabelProvider>
 *
 * Or with auto-detection:
 *   <WhiteLabelProvider>{children}</WhiteLabelProvider>
 */

import * as React from "react";

import {
  DEFAULT_BRANDING,
  applyBranding,
  resolveTenantId,
  whitelabelApi,
  type Branding,
  type BrandingBundle,
} from "../lib/theme";

interface WhiteLabelContextValue {
  tenantId: string;
  branding: Branding;
  cssVariables: Record<string, string>;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  update: (next: Partial<Branding>) => Promise<void>;
}

const Ctx = React.createContext<WhiteLabelContextValue | null>(null);

export function useWhiteLabel(): WhiteLabelContextValue {
  const ctx = React.useContext(Ctx);
  if (!ctx) {
    // Soft default so deeply nested components never crash.
    return {
      tenantId: "public",
      branding: DEFAULT_BRANDING,
      cssVariables: {},
      loading: false,
      error: "WhiteLabelProvider not mounted",
      refresh: async () => {},
      update: async () => {},
    };
  }
  return ctx;
}

export interface WhiteLabelProviderProps {
  /** Tenant to load; defaults to ``resolveTenantId()``. */
  tenantId?: string;
  /** Optional override — bypasses the API for Storybook / tests. */
  initialBranding?: Branding;
  /** Skip the API entirely. */
  skipFetch?: boolean;
  /** Children. */
  children: React.ReactNode;
}

export function WhiteLabelProvider({
  tenantId,
  initialBranding,
  skipFetch = false,
  children,
}: WhiteLabelProviderProps) {
  const resolvedTenant = React.useMemo(
    () => tenantId || resolveTenantId(),
    [tenantId],
  );

  const [branding, setBranding] = React.useState<Branding>(
    initialBranding ?? DEFAULT_BRANDING,
  );
  const [cssVariables, setCssVariables] = React.useState<Record<string, string>>(
    {},
  );
  const [loading, setLoading] = React.useState<boolean>(!skipFetch);
  const [error, setError] = React.useState<string | null>(null);

  const applyAll = React.useCallback((b: Branding) => {
    applyBranding(b);
  }, []);

  const load = React.useCallback(async () => {
    if (skipFetch) {
      applyAll(initialBranding ?? DEFAULT_BRANDING);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const bundle: BrandingBundle = await whitelabelApi.get(resolvedTenant);
      setBranding(bundle.branding);
      setCssVariables(bundle.css_variables || {});
      applyAll(bundle.branding);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      // Fallback to defaults so the page still renders.
      applyAll(DEFAULT_BRANDING);
    } finally {
      setLoading(false);
    }
  }, [resolvedTenant, skipFetch, initialBranding, applyAll]);

  React.useEffect(() => {
    load();
  }, [load]);

  const refresh = React.useCallback(async () => {
    await load();
  }, [load]);

  const update = React.useCallback(
    async (next: Partial<Branding>) => {
      const merged: Branding = { ...branding, ...next, tenant_id: resolvedTenant };
      setBranding(merged);
      applyAll(merged);
      try {
        const saved = await whitelabelApi.upsert(resolvedTenant, merged);
        setBranding(saved);
        applyAll(saved);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      }
    },
    [branding, resolvedTenant, applyAll],
  );

  const value = React.useMemo<WhiteLabelContextValue>(
    () => ({
      tenantId: resolvedTenant,
      branding,
      cssVariables,
      loading,
      error,
      refresh,
      update,
    }),
    [resolvedTenant, branding, cssVariables, loading, error, refresh, update],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export default WhiteLabelProvider;