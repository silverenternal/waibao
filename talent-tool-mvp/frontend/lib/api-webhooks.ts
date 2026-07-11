/**
 * Webhook admin API client (T802).
 *
 * Endpoint base: `${process.env.NEXT_PUBLIC_API_URL}/api/webhooks`.
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

export interface WebhookRow {
  id: string;
  organisation_id: string;
  name: string;
  url: string;
  events: string[];
  active: boolean;
  secret?: string | null;
  description?: string | null;
  created_at: string;
}

export interface WebhookDelivery {
  id: string;
  webhook_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  status: "pending" | "success" | "failed_retrying" | "failed_dead_letter";
  attempts: number;
  last_attempt_at: string | null;
  response_code: number | null;
  response_body: string | null;
  last_error: string | null;
  created_at: string;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const token = await getToken();
  const res = await fetch(url, {
    ...init,
    headers: { ...(await authHeaders(token)), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`webhook ${init?.method ?? "GET"} ${url} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const webhooksApi = {
  list: () => fetchJson<WebhookRow[]>(`${API_BASE}/api/webhooks`),
  get: (id: string) =>
    fetchJson<WebhookRow>(`${API_BASE}/api/webhooks/${id}`),
  create: (body: Omit<WebhookRow, "id" | "organisation_id" | "created_at">) =>
    fetchJson<WebhookRow>(`${API_BASE}/api/webhooks`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: Partial<WebhookRow>) =>
    fetchJson<WebhookRow>(`${API_BASE}/api/webhooks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) =>
    fetch(`${API_BASE}/api/webhooks/${id}`, { method: "DELETE" }).then((r) => {
      if (!r.ok) throw new Error(`delete failed: ${r.status}`);
    }),
  deliveries: (id: string, limit = 50) =>
    fetchJson<WebhookDelivery[]>(
      `${API_BASE}/api/webhooks/${id}/deliveries?limit=${limit}`,
    ),
  test: (id: string, event: string, data: Record<string, unknown> = {}) =>
    fetchJson<{
      ok: boolean;
      status_code: number | null;
      response_body: string | null;
      signature: string;
      timestamp: string;
      delivery_id: string;
    }>(`${API_BASE}/api/webhooks/${id}/test`, {
      method: "POST",
      body: JSON.stringify({ event, data }),
    }),
  replay: (id: string) =>
    fetchJson<{ queued: number; delivery_ids: string[] }>(
      `${API_BASE}/api/webhooks/${id}/replay`,
      { method: "POST" },
    ),
};

export const ALL_WEBHOOK_EVENTS = [
  "ticket.created",
  "ticket.assigned",
  "ticket.resolved",
  "ticket.escalated",
  "match.proposed",
  "match.accepted",
  "match.rejected",
  "emotion.risk",
  "emotion.crisis",
  "policy.legal_risk",
  "jd.overspec_warning",
  "jd.bias_detected",
  "room.mention",
] as const;

export type WebhookEventType = (typeof ALL_WEBHOOK_EVENTS)[number];
