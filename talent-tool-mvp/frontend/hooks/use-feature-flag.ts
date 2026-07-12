"use client";

/**
 * v6.0 T2103 — useFeatureFlag hook.
 *
 * Client-side mirror of the backend decision. The hook:
 *   1. Reads the cached decision from /api/admin/feature-flags/{name}/decide
 *   2. Subscribes to `feature_flag.changed` events over the EventBus SSE
 *      stream so UI flips immediately when an operator pushes a new rollout.
 *   3. Falls back to localStorage caching so subsequent renders are instant.
 *
 * Usage:
 *   const realtimeVoice = useFeatureFlag('realtime_voice', { userId, orgId });
 *   if (!realtimeVoice) return <UpgradeHint />;
 */

import * as React from "react";
import { useEventBus } from "@/hooks/use-event";

const CACHE_PREFIX = "waibao:ff:";
const CACHE_TTL_MS = 60_000;

export interface FeatureFlagDecision {
  name: string;
  enabled: boolean;
  reason: string;
  rollout_percent?: number;
  global_enabled?: boolean;
}

export interface UseFeatureFlagOptions {
  /** Default value when the server cannot be reached. */
  defaultEnabled?: boolean;
  /** When true, do not subscribe to live updates. */
  static?: boolean;
}

interface CacheEntry {
  decision: FeatureFlagDecision;
  expires: number;
}

function readCache(name: string, userId?: string, orgId?: string): CacheEntry | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(
      `${CACHE_PREFIX}${name}:u=${userId ?? ""}:o=${orgId ?? ""}`
    );
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEntry;
    if (parsed.expires < Date.now()) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeCache(entry: CacheEntry, userId?: string, orgId?: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      `${CACHE_PREFIX}${entry.decision.name}:u=${userId ?? ""}:o=${orgId ?? ""}`,
      JSON.stringify(entry)
    );
  } catch {
    /* quota / private mode — ignore */
  }
}

function clearCache(name?: string): void {
  if (typeof window === "undefined") return;
  try {
    if (!name) {
      for (const key of Object.keys(window.localStorage)) {
        if (key.startsWith(CACHE_PREFIX)) window.localStorage.removeItem(key);
      }
      return;
    }
    for (const key of Object.keys(window.localStorage)) {
      if (key.startsWith(`${CACHE_PREFIX}${name}:`)) window.localStorage.removeItem(key);
    }
  } catch {
    /* ignore */
  }
}

async function fetchDecision(
  name: string,
  userId?: string,
  orgId?: string
): Promise<FeatureFlagDecision> {
  const params = new URLSearchParams();
  if (userId) params.set("user_id", userId);
  if (orgId) params.set("org_id", orgId);
  const url = `/api/admin/feature-flags/${encodeURIComponent(name)}/decide${
    params.toString() ? `?${params.toString()}` : ""
  }`;
  const r = await fetch(url, { credentials: "include" });
  if (!r.ok) {
    // Unknown flag => default-off rather than crash. Backend already does this,
    // but we are defensive in case the route is missing entirely.
    return { name, enabled: false, reason: "http_error" };
  }
  return (await r.json()) as FeatureFlagDecision;
}

export function useFeatureFlag(
  name: string,
  context: { userId?: string; orgId?: string } = {},
  options: UseFeatureFlagOptions = {}
): boolean {
  const { userId, orgId } = context;
  const { defaultEnabled = false, static: isStatic = false } = options;
  const [enabled, setEnabled] = React.useState<boolean>(defaultEnabled);
  const [reason, setReason] = React.useState<string>("loading");
  const [loaded, setLoaded] = React.useState(false);

  // Bus subscription — re-fetch whenever a flag changes on the server.
  const bus = useEventBus?.();
  React.useEffect(() => {
    if (isStatic || !bus) return;
    const unsub = bus.subscribe?.("feature_flag.changed", (evt: any) => {
      const payload = evt?.payload ?? {};
      if (payload?.name === name) {
        // Force re-fetch on next tick.
        setLoaded(false);
      }
    });
    return () => {
      try {
        unsub?.();
      } catch {
        /* ignore */
      }
    };
  }, [bus, name, isStatic]);

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      // 1) try cache
      const cached = readCache(name, userId, orgId);
      if (cached) {
        if (!cancelled) {
          setEnabled(cached.decision.enabled);
          setReason(cached.decision.reason);
          setLoaded(true);
        }
        return;
      }
      // 2) network
      try {
        const decision = await fetchDecision(name, userId, orgId);
        if (cancelled) return;
        setEnabled(decision.enabled);
        setReason(decision.reason);
        setLoaded(true);
        writeCache(
          { decision, expires: Date.now() + CACHE_TTL_MS },
          userId,
          orgId
        );
      } catch {
        if (cancelled) return;
        setEnabled(defaultEnabled);
        setReason("network_error");
        setLoaded(true);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [name, userId, orgId, defaultEnabled, loaded]);

  return enabled;
}

/** Imperative read for non-React code paths (e.g. middleware / event handlers). */
export async function readFeatureFlag(
  name: string,
  context: { userId?: string; orgId?: string } = {}
): Promise<FeatureFlagDecision> {
  const cached = readCache(name, context.userId, context.orgId);
  if (cached) return cached.decision;
  const decision = await fetchDecision(name, context.userId, context.orgId);
  writeCache({ decision, expires: Date.now() + CACHE_TTL_MS }, context.userId, context.orgId);
  return decision;
}

/** Drop cached decisions — useful after admin writes. */
export function invalidateFeatureFlagCache(name?: string): void {
  clearCache(name);
}

export const __testing = { CACHE_PREFIX, CACHE_TTL_MS };