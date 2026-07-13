/**
 * API v1 client — DEPRECATED — T2904.
 *
 * Routes through `/api/v1/*` and surfaces the deprecation headers that the
 * backend middleware emits (``X-API-Deprecated``, ``Sunset``, ``Link``,
 * ``Deprecation``).  Components using this client render the
 * :class:`DeprecatedVersionBanner` so end users see a non-blocking nag.
 *
 * IMPORTANT: This module is kept for backward compatibility only.  New
 * code should import from `@/lib/api-v2` instead.
 *
 * Removal schedule
 * ----------------
 * * 2026-09-01 — deprecation banner shown to all consumers.
 * * 2026-12-31 — last date clients may continue calling v1.
 * * 2027-01-01 — v1 returns 410 Gone.
 */

import { apiV2, V2ApiError, v2Fetch, v2List } from "./api-v2";

const VERSION = "v1" as const;

interface V1RequestInit extends RequestInit {
  token?: string | null;
}

const VERSIONING = {
  version: VERSION,
  deprecated: true,
  /** RFC 8594 — when the version will sunset. */
  sunsetAt: "2027-01-01T00:00:00Z",
  /** Recommended target. */
  successor: "v2",
} as const;

let listenersInstalled = false;
const seenWarnings = new Set<string>();

/**
 * Subscribe to console + window-level warnings so integration smoke tests
 * can observe deprecation traffic without instrumenting every call site.
 */
function installListeners() {
  if (listenersInstalled || typeof window === "undefined") return;
  listenersInstalled = true;
  window.addEventListener("vite:deprecated-api-used" as never, () => {
    // hook for future client-side telemetry
  });
}

function warnOnce(path: string): void {
  installListeners();
  const key = `${path}|${VERSION}`;
  if (seenWarnings.has(key)) return;
  seenWarnings.add(key);
  // eslint-disable-next-line no-console
  console.warn(
    `[api-v1] DEPRECATED — route ${path} targets the /api/v1 namespace. ` +
      `Sunset: ${VERSIONING.sunsetAt}. Migrate to api-v2 — successor: ${VERSIONING.successor}.`,
  );
}

export async function v1Fetch<T = unknown>(
  path: string,
  init: V1RequestInit = {},
): Promise<T> {
  if (!path.startsWith("/")) {
    throw new Error(`v1Fetch expects an absolute path; got ${path}`);
  }
  warnOnce(path);
  const url = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/${VERSION}${path}`;
  const headers = new Headers(init.headers);
  headers.set("X-API-Version", VERSION);
  headers.set("Accept", "application/json");
  const token = init.token ?? undefined;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const r = await fetch(url, { ...init, headers });
  if (r.headers.get("x-api-deprecated") === "true") {
    /* expected — used as a hint by consumers */
  }
  const ct = r.headers.get("content-type") ?? "";
  const parsed: unknown = ct.includes("application/json")
    ? await r.json()
    : await r.text();
  if (!r.ok) {
    const code =
      typeof parsed === "object" && parsed !== null && "code" in parsed
        ? String((parsed as Record<string, unknown>).code)
        : undefined;
    throw new V2ApiError(r.status, r.statusText, code, parsed);
  }
  return parsed as T;
}

export const apiV1 = {
  ...apiV2, // re-export manifest/fetch helpers for ergonomics
  version: VERSION,
  fetch: v1Fetch,
  list: <T>(
    path: string,
    query: Record<string, string | number | undefined | null> = {},
  ) =>
    v2List<T>(path, query).then((page) => {
      warnOnce(path);
      return page;
    }),
  /**
   * Re-export v2 manifest as v1 awareness — consumers can call
   * `apiV1.manifest()` to learn about the deprecation timeline.
   */
  manifest: () => apiV2.manifest(),
  /** Static metadata describing the v1 lifecycle. */
  lifecycle: VERSIONING,
} as const;

export { v2Fetch as v1PassthroughFetch };

export default apiV1;
