/**
 * T903 — Admin: 匹配质量 dashboard API client.
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

export interface QualitySummary {
  precision: number;
  recall: number;
  f1: number;
  total: number;
  tp: number;
  fp: number;
  fn: number;
  tn: number;
  drift: number;
}

export interface QualityBucket {
  count: number;
  placed_rate: number;
  rejected_rate: number;
  pending_rate?: number;
  avg_harmonic?: number;
}

export interface QualitySnapshot {
  summary: QualitySummary;
  bucket_distribution: Record<string, QualityBucket>;
  segment_metrics: Record<string, { count: number; precision: number; recall: number; f1: number }>;
  history: Array<{
    recorded_at: string;
    precision: number;
    recall: number;
    f1: number;
    total: number;
  }>;
  since_days: number;
  generated_at: string;
}

export const matchingQualityApi = {
  async get(since_days = 7): Promise<QualitySnapshot> {
    const h = await authHeaders();
    const r = await fetch(
      `${API_BASE}/api/admin/matching-quality?since_days=${since_days}`,
      { headers: h }
    );
    if (!r.ok) throw new Error(`quality get failed: ${r.status}`);
    return r.json();
  },
};