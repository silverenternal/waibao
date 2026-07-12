/**
 * Salary Report API client (T2402).
 */
const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("sb_token");
    if (token) h["Authorization"] = `Bearer ${token}`;
  }
  return h;
}

export interface SalaryDistribution {
  role: string;
  city: string;
  seniority: string;
  p10_k: number;
  p25_k: number;
  p50_k: number;
  p75_k: number;
  p90_k: number;
  sample_size: number;
  currency: string;
  computed_at: string;
}

export interface SalaryTrend {
  role: string;
  city: string;
  period: "monthly" | "quarterly" | "yearly";
  points: Array<{
    period: string;
    median_k: number;
    p25_k?: number;
    p75_k?: number;
    sample_size?: number;
  }>;
  change_6m_pct: number;
  computed_at: string;
}

export interface OfferPosition {
  role: string;
  city: string;
  seniority: string;
  offer_k: number;
  p50_k: number;
  percentile: string;
  percentile_rank: number;
  recommendation: "low" | "fair" | "competitive" | "high";
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url, {
    method: "GET",
    headers: await authHeaders(),
    credentials: "include",
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json() as Promise<T>;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const resp = await fetch(url, {
    method: "POST",
    headers: await authHeaders(),
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json() as Promise<T>;
}

export async function getSalaryInsights(
  role: string,
  city: string,
  seniority = "mid"
): Promise<{ distribution: SalaryDistribution; trend: SalaryTrend }> {
  return getJson(
    `${API_BASE}/api/salary/insights?role=${encodeURIComponent(role)}&city=${encodeURIComponent(city)}&seniority=${seniority}`
  );
}

export async function getSalaryPercentiles(
  role: string,
  city: string,
  seniority = "mid"
): Promise<SalaryDistribution> {
  return getJson(
    `${API_BASE}/api/salary/percentiles?role=${encodeURIComponent(role)}&city=${encodeURIComponent(city)}&seniority=${seniority}`
  );
}

export async function getSalaryTrends(
  role: string,
  city: string,
  period: "monthly" | "quarterly" | "yearly" = "monthly",
  months = 12
): Promise<SalaryTrend> {
  return getJson(
    `${API_BASE}/api/salary/trends?role=${encodeURIComponent(role)}&city=${encodeURIComponent(city)}&period=${period}&months=${months}`
  );
}

export async function locateOffer(
  role: string,
  city: string,
  seniority: string,
  offerK: number
): Promise<OfferPosition> {
  return postJson(`${API_BASE}/api/salary/locate`, {
    role,
    city,
    seniority,
    offer_k: offerK,
  });
}