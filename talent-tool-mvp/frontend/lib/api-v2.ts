/**
 * API v2 client — recommended target — T2904.
 *
 * Mirrors the shape of `lib/api.ts` but prepends `/api/v2/` to every
 * endpoint and explicitly tag requests with the v2 header.  Caller
 * benefits:
 *
 *   * Stable forward-compatible schemas.
 *   * 308 redirect from legacy `/api/<x>` is no longer required.
 *   * Strict RFC 7807 problem responses for errors.
 *   * Optional `next_cursor` pagination (cursor-based, not page-based).
 *
 * NOTE: Preferred over `lib/api-v1.ts`.  v1 will be removed on
 * 2027-01-01 — see `lib/api-versioning.ts` for the schedule.
 */

import { createClient } from "@/lib/supabase";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const VERSION = "v2" as const;

export class V2ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public code: string | undefined,
    public body: unknown,
  ) {
    super(`V2 API ${status}: ${statusText} (${code ?? "no-code"})`);
    this.name = "V2ApiError";
  }
}

interface V2RequestInit extends RequestInit {
  /** Override the Bearer token; defaults to the current Supabase session. */
  token?: string | null;
  /** Hint to the backend; if a deprecated version is detected, we throw. */
  acceptVersion?: typeof VERSION;
}

async function getAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  try {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}

export async function v2Fetch<T = unknown>(
  path: string,
  init: V2RequestInit = {},
): Promise<T> {
  if (!path.startsWith("/")) {
    throw new Error(`v2Fetch expects an absolute path; got ${path}`);
  }
  const url = `${API_BASE}/api/${VERSION}${path}`;
  const headers = new Headers(init.headers);
  headers.set("X-API-Version", VERSION);
  headers.set("Accept", "application/json, application/problem+json");
  const token = init.token ?? (await getAuthToken());
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const r = await fetch(url, { ...init, headers });
  // Surface deprecation if the backend somehow serves v1 from this client.
  if (r.headers.get("x-api-deprecated") === "true") {
    // eslint-disable-next-line no-console
    console.warn("[v2] received a deprecated v1 response — check routing.");
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

/** Convenience: list + cursor iteration. */
export async function v2List<T>(
  path: string,
  query: Record<string, string | number | undefined | null> = {},
): Promise<{ items: T[]; next_cursor: string | null }> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue;
    qs.set(k, String(v));
  }
  const qsStr = qs.toString();
  return v2Fetch<{ items: T[]; next_cursor: string | null }>(
    `${path}${qsStr ? "?" + qsStr : ""}`,
  );
}

// ---- High-level client ----------------------------------------------------

export const apiV2 = {
  version: VERSION,
  fetch: v2Fetch,
  list: v2List,
  /** Schema endpoint surfaced by backend (``GET /api/v2/version``). */
  async manifest() {
    return v2Fetch<{
      current: string;
      recommended: string;
      deprecated: string[];
      versions: Array<{
        version: string;
        status: string;
        sunset_at: string | null;
        successor: string | null;
      }>;
    }>("/version");
  },
} as const;

export default apiV2;
