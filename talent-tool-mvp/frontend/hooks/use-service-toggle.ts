"use client";

/**
 * v8.0 T3501 — useServiceToggle hook.
 *
 * Client-side mirror of the backend `service_toggle.is_enabled` decision.
 * Subscribes to `service.changed` events from the EventBus so any UI flips
 * immediately when an admin pushes a change.
 *
 * Usage:
 *   const realtimeVoice = useServiceToggle("api.ai_interview");
 *   if (!realtimeVoice) return null;
 */

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useEventBus } from "@/hooks/use-event";

const CACHE_PREFIX = "waibao:st:";
const CACHE_TTL_MS = 60_000;

export interface ServiceDecision {
  name: string;
  status: "enabled" | "disabled" | "maintenance" | "beta";
  available: boolean;
  reason?: string;
  plan_required?: string;
  role?: string;
  org_id?: string | null;
}

export interface UseServiceToggleOptions {
  plan?: string;
  role?: string;
  orgId?: string;
  /** When true, return the cached value without re-fetching. */
  static?: boolean;
  /** Default value when the server cannot be reached. */
  defaultAvailable?: boolean;
}

interface CacheEntry {
  decision: ServiceDecision;
  expires: number;
}

function readCache(name: string): ServiceDecision | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_PREFIX + name);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEntry;
    if (parsed.expires < Date.now()) return null;
    return parsed.decision;
  } catch {
    return null;
  }
}

function writeCache(decision: ServiceDecision): void {
  if (typeof window === "undefined") return;
  try {
    const entry: CacheEntry = { decision, expires: Date.now() + CACHE_TTL_MS };
    window.localStorage.setItem(
      CACHE_PREFIX + decision.name,
      JSON.stringify(entry),
    );
  } catch {
    /* quota exceeded - ignore */
  }
}

function buildQuery(
  name: string,
  plan: string,
  role: string,
  orgId: string | undefined,
): string {
  const params = new URLSearchParams({ plan, role });
  if (orgId) params.set("org_id", orgId);
  return `/api/admin/services/${encodeURIComponent(name)}/decide?${params.toString()}`;
}

export function useServiceToggle(
  name: string,
  options: UseServiceToggleOptions = {},
): boolean {
  const { plan = "free", role = "", orgId, static: staticMode, defaultAvailable = true } = options;
  const bus = useEventBus();

  // Optimistic local cache
  const [available, setAvailable] = React.useState<boolean>(() => {
    const cached = readCache(name);
    return cached ? cached.available : defaultAvailable;
  });

  const query = useQuery({
    queryKey: ["service-toggle", name, plan, role, orgId ?? ""],
    enabled: !staticMode,
    staleTime: CACHE_TTL_MS,
    queryFn: async (): Promise<ServiceDecision | null> => {
      try {
        const res = await fetch(buildQuery(name, plan, role, orgId), {
          credentials: "include",
        });
        if (!res.ok) return null;
        const data = (await res.json()) as ServiceDecision;
        writeCache(data);
        return data;
      } catch {
        return readCache(name);
      }
    },
  });

  React.useEffect(() => {
    if (query.data) {
      setAvailable(query.data.available);
    }
  }, [query.data]);

  // Subscribe to live service.changed events
  React.useEffect(() => {
    if (staticMode) return;
    if (!bus || typeof bus.subscribe !== "function") return;
    const off = bus.subscribe("service.changed", (msg: unknown) => {
      const payload = msg as { service?: string };
      if (payload?.service === name) {
        // Re-fetch on next tick
        query.refetch();
      }
    });
    return () => {
      try {
        off?.();
      } catch {
        /* noop */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bus, name]);

  return available;
}

export function useServiceCatalog(
  plan: string = "free",
  role: string = "",
): { data: ServiceDecision[] | undefined; isLoading: boolean; refetch: () => void } {
  const q = useQuery({
    queryKey: ["service-catalog", plan, role],
    staleTime: CACHE_TTL_MS,
    queryFn: async () => {
      const params = new URLSearchParams({ plan, role });
      const res = await fetch(
        `/api/admin/services?${params.toString()}`,
        { credentials: "include" },
      );
      if (!res.ok) return [];
      const json = (await res.json()) as { items: ServiceDecision[] };
      return json.items ?? [];
    },
  });
  return { data: q.data, isLoading: q.isLoading, refetch: q.refetch };
}
