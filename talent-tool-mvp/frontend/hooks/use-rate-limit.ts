"use client";

/**
 * T2602 - useRateLimit
 *
 * Client-side mirror of the backend rate-limit / quota state.
 *
 * Responsibilities:
 *   1. Read rate-limit headers off every API response
 *      (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`,
 *      and `Retry-After` on 429s).
 *   2. Surface a typed `RateLimitSnapshot` for UI consumers — toasts,
 *      progress bars, upgrade nudges, etc.
 *   3. Track plan + tenant context (X-Plan + X-Tenant-ID echoed by the
 *      backend on every response).
 *
 * Usage:
 *
 *     const rl = useRateLimit();
 *     <ProgressBar used={rl.used} limit={rl.limit} />
 *     {rl.isExhausted && <UpgradeBanner plan={rl.plan} />}
 */

import * as React from "react";

export interface RateLimitSnapshot {
  /** Tenant id from the most recent response, if any. */
  tenantId: string | null;
  /** Plan echoed by the backend (free | pro | enterprise). */
  plan: "free" | "pro" | "enterprise" | string;
  /** Maximum requests allowed in the current window. */
  limit: number | null;
  /** Remaining requests in the current window. */
  remaining: number | null;
  /** Seconds until the limit resets. null when unknown. */
  resetInSeconds: number | null;
  /** Seconds to wait before retrying after a 429. */
  retryAfterSeconds: number | null;
  /** Convenience flags. */
  isExhausted: boolean;
  isWarning: boolean;   // remaining < 10 % of limit
  lastUpdated: number;  // epoch ms
}

const INITIAL: RateLimitSnapshot = {
  tenantId: null,
  plan: "free",
  limit: null,
  remaining: null,
  resetInSeconds: null,
  retryAfterSeconds: null,
  isExhausted: false,
  isWarning: false,
  lastUpdated: 0,
};

export interface FetchLikeResponse {
  headers: Headers;
  status: number;
}

export interface UseRateLimitOptions {
  /** Auto-bind to window.fetch (default: true). */
  bindFetch?: boolean;
  /** Storage key for caching the snapshot across reloads. */
  cacheKey?: string;
}

export function useRateLimit(
  options: UseRateLimitOptions = {},
): RateLimitSnapshot & { recordResponse: (r: FetchLikeResponse) => void } {
  const { bindFetch = true, cacheKey = "waibao:ratelimit" } = options;
  const [snap, setSnap] = React.useState<RateLimitSnapshot>(() => {
    if (typeof window === "undefined") return INITIAL;
    try {
      const raw = window.localStorage.getItem(cacheKey);
      if (raw) return JSON.parse(raw) as RateLimitSnapshot;
    } catch (_e) {
      /* ignore */
    }
    return INITIAL;
  });

  const recordResponse = React.useCallback(
    (resp: FetchLikeResponse) => {
      const h = resp.headers;
      const limit = parseIntOrNull(h.get("X-RateLimit-Limit"));
      const remaining = parseIntOrNull(h.get("X-RateLimit-Remaining"));
      const reset = parseIntOrNull(h.get("X-RateLimit-Reset"));
      const retryAfterRaw = h.get("Retry-After");
      const retryAfter = retryAfterRaw ? parseInt(retryAfterRaw, 10) : null;
      const tenantId = h.get("X-Tenant-ID");
      const planHeader = h.get("X-Plan");
      const plan = (planHeader || "free").toLowerCase();

      const next: RateLimitSnapshot = {
        tenantId,
        plan,
        limit,
        remaining,
        resetInSeconds: reset,
        retryAfterSeconds: resp.status === 429 ? retryAfter : null,
        isExhausted:
          resp.status === 429 ||
          (remaining !== null && remaining <= 0),
        isWarning:
          limit !== null &&
          remaining !== null &&
          remaining > 0 &&
          remaining / limit < 0.1,
        lastUpdated: Date.now(),
      };
      setSnap(next);
      if (typeof window !== "undefined") {
        try {
          window.localStorage.setItem(cacheKey, JSON.stringify(next));
        } catch (_e) {
          /* quota / private mode — skip */
        }
      }
    },
    [cacheKey],
  );

  // Optionally bind window.fetch so every response is observed.
  React.useEffect(() => {
    if (!bindFetch || typeof window === "undefined") return;
    const original = window.fetch.bind(window);
    window.fetch = ((...args: Parameters<typeof fetch>) => {
      return original(...args).then((resp) => {
        try {
          recordResponse(resp);
        } catch (_e) {
          /* never throw from a fetch wrapper */
        }
        return resp;
      });
    }) as typeof fetch;
    return () => {
      window.fetch = original;
    };
  }, [bindFetch, recordResponse]);

  return { ...snap, recordResponse };
}

function parseIntOrNull(s: string | null): number | null {
  if (s == null) return null;
  const n = parseInt(s, 10);
  return Number.isFinite(n) ? n : null;
}

export default useRateLimit;
