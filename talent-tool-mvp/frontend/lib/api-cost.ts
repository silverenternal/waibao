/**
 * Cost dashboard API client (T806).
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
// Types
// ---------------------------------------------------------------------------

export interface ProviderCost {
  provider: string;
  cost_usd: number;
}

export interface TenantCost {
  tenant_id: string;
  cost_usd: number;
}

export interface ModelCost {
  model: string;
  cost_usd: number;
}

export interface DailyCostPoint {
  date: string;
  cost_usd: number;
}

export interface ProviderTenantMatrixEntry {
  provider: string;
  tenants: TenantCost[];
}

export interface CostSummary {
  total_cost_usd: number;
  by_provider: ProviderCost[];
  by_tenant: TenantCost[];
  by_model: ModelCost[];
  daily_trend: DailyCostPoint[];
  provider_tenant_matrix: ProviderTenantMatrixEntry[];
}

export interface CacheStats {
  ttl_seconds: number;
  max_size: number;
  memory_size: number;
  redis_size: number;
  redis_healthy: boolean;
  hits: number;
  misses: number;
  writes: number;
  write_failures: number;
  hit_rate: number;
  total_requests: number;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const costApi = {
  async getSummary(tenantId?: string, sinceDays = 30): Promise<CostSummary> {
    const token = await getToken();
    const url = new URL(`${API_BASE}/api/admin/cost/summary`);
    if (tenantId) url.searchParams.set("tenant_id", tenantId);
    url.searchParams.set("since_days", String(sinceDays));
    const res = await fetch(url.toString(), {
      headers: await authHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Failed to fetch summary: ${res.status}`);
    const json = (await res.json()) as { data: CostSummary };
    return json.data;
  },

  async getByProvider(tenantId?: string, sinceDays = 30): Promise<ProviderCost[]> {
    const token = await getToken();
    const url = new URL(`${API_BASE}/api/admin/cost/by-provider`);
    if (tenantId) url.searchParams.set("tenant_id", tenantId);
    url.searchParams.set("since_days", String(sinceDays));
    const res = await fetch(url.toString(), {
      headers: await authHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Failed to fetch by-provider: ${res.status}`);
    const json = (await res.json()) as { data: ProviderCost[] };
    return json.data || [];
  },

  async getByTenant(sinceDays = 30): Promise<TenantCost[]> {
    const token = await getToken();
    const url = new URL(`${API_BASE}/api/admin/cost/by-tenant`);
    url.searchParams.set("since_days", String(sinceDays));
    const res = await fetch(url.toString(), {
      headers: await authHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Failed to fetch by-tenant: ${res.status}`);
    const json = (await res.json()) as { data: TenantCost[] };
    return json.data || [];
  },

  async getCacheStats(): Promise<CacheStats> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/cost/cache-stats`, {
      headers: await authHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Failed to fetch cache stats: ${res.status}`);
    const json = (await res.json()) as { data: CacheStats };
    return json.data;
  },
};
