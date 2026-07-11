/**
 * API Keys admin API client (T803).
 *
 * Endpoint base: ${process.env.NEXT_PUBLIC_API_URL}/api/admin/api-keys.
 *
 * Plaintext 仅在 create() 返回一次. 后续所有 endpoint 不返回 key_hash / plaintext.
 */

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

async function authHeaders(token: string | null) {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

async function getToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("sb_token") || null;
}

export const API_KEY_SCOPES = [
  "candidates:read",
  "candidates:write",
  "roles:read",
  "matches:write",
  "tickets:write",
] as const;

export type ApiKeyScope = (typeof API_KEY_SCOPES)[number];

export interface ApiKeyRow {
  id: string;
  name: string;
  key_prefix: string;
  scopes: ApiKeyScope[];
  rate_limit_per_min: number;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_at: string | null;
}

/** 仅 create 时返回 plaintext. */
export interface ApiKeyCreated extends ApiKeyRow {
  plaintext: string;
}

export interface ApiKeyUsage {
  api_key_id: string;
  window_days: number;
  total_calls: number;
  success_rate: number;
  per_endpoint: Array<{
    endpoint: string;
    calls: number;
    avg_status: number;
    last_called_at: string | null;
  }>;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const token = await getToken();
  const res = await fetch(url, {
    ...init,
    headers: { ...(await authHeaders(token)), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`api-key ${init?.method ?? "GET"} ${url} → ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export const apiKeysAdminApi = {
  list: () => fetchJson<ApiKeyRow[]>(`${API_BASE}/api/admin/api-keys`),
  get: (id: string) =>
    fetchJson<ApiKeyRow>(`${API_BASE}/api/admin/api-keys/${id}`),
  create: (body: {
    name: string;
    scopes: ApiKeyScope[];
    rate_limit_per_min?: number;
    expires_at?: string | null;
  }) =>
    fetchJson<ApiKeyCreated>(`${API_BASE}/api/admin/api-keys`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (
    id: string,
    body: Partial<{
      name: string;
      scopes: ApiKeyScope[];
      rate_limit_per_min: number;
      expires_at: string | null;
    }>,
  ) =>
    fetchJson<ApiKeyRow>(`${API_BASE}/api/admin/api-keys/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  revoke: (id: string) =>
    fetch(`${API_BASE}/api/admin/api-keys/${id}`, { method: "DELETE" }).then(
      (r) => {
        if (!r.ok) throw new Error(`revoke failed: ${r.status}`);
      },
    ),
  usage: (id: string, days = 7) =>
    fetchJson<ApiKeyUsage>(
      `${API_BASE}/api/admin/api-keys/${id}/usage?days=${days}`,
    ),
};

/**
 * 公开 API v1 client (T803).
 * 第三方开发者调用;自带 X-API-Key.
 */
export const publicApi = {
  createCandidate: (apiKey: string, body: Record<string, unknown>) =>
    fetch(`${API_BASE}/api/public/v1/candidates`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify(body),
    }).then((r) => r.json()),
  getCandidate: (apiKey: string, id: string) =>
    fetch(`${API_BASE}/api/public/v1/candidates/${id}`, {
      headers: { "X-API-Key": apiKey },
    }).then((r) => r.json()),
  listRoles: (apiKey: string) =>
    fetch(`${API_BASE}/api/public/v1/roles`, {
      headers: { "X-API-Key": apiKey },
    }).then((r) => r.json()),
  proposeMatch: (apiKey: string, body: Record<string, unknown>) =>
    fetch(`${API_BASE}/api/public/v1/matches`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify(body),
    }).then((r) => r.json()),
  createTicket: (apiKey: string, body: Record<string, unknown>) =>
    fetch(`${API_BASE}/api/public/v1/tickets`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify(body),
    }).then((r) => r.json()),
};
