/**
 * Rule engine admin API client (T804).
 *
 * Endpoint base: ${process.env.NEXT_PUBLIC_API_URL}/api/rules.
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

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

export type ComparisonOp =
  | "=="
  | "!="
  | "<"
  | "<="
  | ">"
  | ">="
  | "in"
  | "not_in"
  | "contains"
  | "starts_with"
  | "exists";

export type LogicalOp = "AND" | "OR" | "NOT";

export interface AtomicCondition {
  op: ComparisonOp;
  field: string;
  value: unknown;
}

export interface ConditionGroup {
  op: LogicalOp;
  children: Array<ConditionGroup | AtomicCondition>;
}

export type ConditionNode = ConditionGroup | AtomicCondition;
export type RuleCondition = ConditionNode | null;

export interface RuleAction {
  type: "notify" | "create_ticket" | "webhook" | "emit_event";
  // 其它字段直接放在顶层 (channel / priority / url 等)
  [key: string]: unknown;
}

export interface RuleRow {
  id: string;
  organisation_id: string;
  name: string;
  description: string;
  trigger: string;
  condition: ConditionGroup | null;
  actions: RuleAction[];
  enabled: boolean;
  cooldown_seconds: number;
  tags: string[];
  last_triggered_at: string | null;
  trigger_count: number;
  created_at: string | null;
}

export interface RuleRun {
  id: string;
  rule_id: string;
  trigger: string;
  matched: boolean;
  context_snapshot: Record<string, unknown>;
  actions_executed: RuleAction[];
  duration_ms: number;
  error: string | null;
  occurred_at: string;
}

export interface BuiltinTrigger {
  name: string;
  description: string;
  schema: Record<string, unknown>;
  example_context: Record<string, unknown>;
  kind: "metric" | "event";
}

// ---------------------------------------------------------------------------
// fetch helpers
// ---------------------------------------------------------------------------

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const token = await getToken();
  const res = await fetch(url, {
    ...init,
    headers: { ...(await authHeaders(token)), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`rules ${init?.method ?? "GET"} ${url} → ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export interface RuleUpsertBody {
  name: string;
  description?: string;
  trigger: string;
  condition: RuleCondition;
  actions: RuleAction[];
  enabled?: boolean;
  cooldown_seconds?: number;
  tags?: string[];
}

export const rulesApi = {
  list: (params: { trigger?: string; enabled?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.trigger) q.set("trigger", params.trigger);
    if (params.enabled !== undefined)
      q.set("enabled", String(params.enabled));
    const qs = q.toString();
    return fetchJson<RuleRow[]>(
      `${API_BASE}/api/rules${qs ? `?${qs}` : ""}`,
    );
  },
  get: (id: string) => fetchJson<RuleRow>(`${API_BASE}/api/rules/${id}`),
  create: (body: RuleUpsertBody) =>
    fetchJson<RuleRow>(`${API_BASE}/api/rules`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: Partial<RuleUpsertBody>) =>
    fetchJson<RuleRow>(`${API_BASE}/api/rules/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) =>
    fetch(`${API_BASE}/api/rules/${id}`, { method: "DELETE" }).then((r) => {
      if (!r.ok) throw new Error(`delete failed: ${r.status}`);
    }),
  test: (
    id: string,
    context: Record<string, unknown>,
    dryRun = true,
  ) =>
    fetchJson<{
      matched: boolean;
      condition_trace: Array<Record<string, unknown>>;
      actions_executed: Array<Record<string, unknown>>;
      duration_ms: number;
      error: string | null;
    }>(`${API_BASE}/api/rules/${id}/test`, {
      method: "POST",
      body: JSON.stringify({ context, dry_run: dryRun }),
    }),
  runs: (id: string, limit = 50) =>
    fetchJson<RuleRun[]>(
      `${API_BASE}/api/rules/${id}/runs?limit=${limit}`,
    ),
  triggers: () =>
    fetchJson<{ triggers: BuiltinTrigger[] }>(
      `${API_BASE}/api/rules/triggers/catalogue`,
    ),
};
