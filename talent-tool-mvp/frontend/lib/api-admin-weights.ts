/**
 * T903 — Admin: 权重 API client.
 */

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

async function getToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("sb_token") || null;
}

async function authHeaders(): Promise<Record<string, string>> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const token = await getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

export interface WeightsSnapshot {
  current: Record<string, number>;
  defaults: Record<string, number>;
  history: Array<{
    id?: string;
    actor?: string;
    weights: Record<string, number>;
    reason?: string;
    created_at?: string;
  }>;
  pending: Array<{
    id?: string;
    weights: Record<string, number>;
    reason?: string;
    actor?: string;
    updated_at?: string;
  }>;
}

export interface WeightRecommendation {
  metrics: any;
  current: Record<string, number>;
  recommendation: {
    new_weights: Record<string, number>;
    delta: Record<string, number>;
    reason: string;
    confidence: number;
  };
  generated_at: string;
}

export const adminWeightsApi = {
  async list(): Promise<WeightsSnapshot> {
    const h = await authHeaders();
    const r = await fetch(`${API_BASE}/api/admin/weights`, { headers: h });
    if (!r.ok) throw new Error(`weights list failed: ${r.status}`);
    return r.json();
  },

  async override(weights: Record<string, number>, reason: string) {
    const h = await authHeaders();
    const r = await fetch(`${API_BASE}/api/admin/weights`, {
      method: "PATCH",
      headers: h,
      body: JSON.stringify({ weights, reason }),
    });
    if (!r.ok) throw new Error(`weights override failed: ${r.status}`);
    return r.json();
  },

  async apply(weights: Record<string, number>, reason: string) {
    const h = await authHeaders();
    const r = await fetch(`${API_BASE}/api/admin/weights/apply`, {
      method: "POST",
      headers: h,
      body: JSON.stringify({ weights, reason }),
    });
    if (!r.ok) throw new Error(`weights apply failed: ${r.status}`);
    return r.json();
  },

  async recommend(since_days = 7): Promise<WeightRecommendation> {
    const h = await authHeaders();
    const r = await fetch(
      `${API_BASE}/api/admin/weights/recommend?since_days=${since_days}`,
      { headers: h }
    );
    if (!r.ok) throw new Error(`weights recommend failed: ${r.status}`);
    return r.json();
  },
};