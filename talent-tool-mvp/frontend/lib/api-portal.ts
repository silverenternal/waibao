/**
 * Developer Portal API client — T2902.
 *
 * Thin wrapper around fetch that:
 *   * sets the Authorization header from Supabase session,
 *   * injects the X-API-Version: v2 header (recommended),
 *   * surfaces deprecation markers via the `X-API-Deprecated` response header.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function getAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    __supabase_session_token?: string;
  };
  if (w.__supabase_session_token) return w.__supabase_session_token;
  // Fallback: try supabase from cookies / localStorage.  We intentionally keep
  // this lazy to avoid bundling the Supabase SDK on every page.
  try {
    const stored = window.localStorage.getItem("recruittech_token");
    return stored ?? null;
  } catch {
    return null;
  }
}

export type PortalFetchOptions = RequestInit & {
  token?: string | null;
  apiVersion?: "v1" | "v2";
};

export async function apiFetch(
  path: string,
  opts: PortalFetchOptions = {},
): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const headers = new Headers(opts.headers);
  const token = opts.token ?? (await getAuthToken());
  if (token) headers.set("Authorization", `Bearer ${token}`);
  headers.set("X-API-Version", opts.apiVersion ?? "v2");
  headers.set("Content-Type", headers.get("Content-Type") ?? "application/json");
  return fetch(url, { ...opts, headers });
}

/**
 * Helper that throws if `response.ok` is false — useful for SDK callers
 * who prefer throw-based error handling over inspecting status codes.
 */
export async function apiFetchOk<T = unknown>(
  path: string,
  opts: PortalFetchOptions = {},
): Promise<T> {
  const r = await apiFetch(path, opts);
  if (!r.ok) {
    let body: unknown = undefined;
    try {
      body = await r.json();
    } catch {
      body = await r.text();
    }
    throw new Error(
      `API ${r.status} ${r.statusText} on ${path}: ${JSON.stringify(body)}`,
    );
  }
  return (await r.json()) as T;
}
