/**
 * Centralised API version metadata — T2904.
 *
 * Single source of truth for both `api-v1.ts` and `api-v2.ts` so the
 * deprecation schedule, banner copy and SDK target stay in lock-step.
 *
 * Values are duplicated from `backend/api/versioning.py:VERSION_REGISTRY`
 * — if you change one, change both.  (We intentionally avoid an HTTP
 * round-trip on every render; the banner component fetches the live
 * manifest lazily for the live sunset date.)
 */

export const API_RECOMMENDED_VERSION = "v2" as const;
export const API_DEPRECATED_VERSION = "v1" as const;

/** ISO date at which v1 returns 410 Gone. */
export const V1_SUNSET_AT = "2027-01-01T00:00:00Z";

/** ISO date when v1 starts to receive the deprecation warning banner. */
export const V1_DEPRECATION_NOTICE_AT = "2026-09-01T00:00:00Z";

export const API_VERSION_LIFECYCLE = {
  v1: {
    version: "v1",
    status: "deprecated",
    successor: "v2",
    sunset_at: V1_SUNSET_AT,
    deprecation_notice_at: V1_DEPRECATION_NOTICE_AT,
    docs: "/developers",
  },
  v2: {
    version: "v2",
    status: "current",
    successor: "v2",
    sunset_at: null,
    docs: "/developers",
  },
} as const;

export type ApiVersion = keyof typeof API_VERSION_LIFECYCLE;

export function isDeprecatedVersion(v: string): boolean {
  const entry = API_VERSION_LIFECYCLE[v as ApiVersion];
  return entry ? entry.status === "deprecated" : false;
}

export function successorFor(v: string): ApiVersion {
  const entry = API_VERSION_LIFECYCLE[v as ApiVersion];
  return (entry?.successor ?? "v2") as ApiVersion;
}

export default API_VERSION_LIFECYCLE;
