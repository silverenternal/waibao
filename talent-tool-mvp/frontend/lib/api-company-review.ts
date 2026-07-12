/**
 * Company Review API client (T2401).
 *
 * Endpoint base: ${NEXT_PUBLIC_API_URL}/api/company-review
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

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url, {
    method: "GET",
    headers: await authHeaders(),
    credentials: "include",
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  return resp.json() as Promise<T>;
}

export interface CompanyRatingItem {
  source: string;
  score: number;
  review_count: number;
  recommend_pct?: number | null;
  ceo_pct?: number | null;
  breakdown: Record<string, number>;
}

export interface ReviewItem {
  id: string;
  source: string;
  title: string;
  content: string;
  pros?: string | null;
  cons?: string | null;
  rating: number;
  job_title?: string | null;
  employment_status?: string | null;
  created_at?: string | null;
  author?: string | null;
  helpful_count: number;
}

export interface InterviewItem {
  id: string;
  source: string;
  job_title: string;
  difficulty: number;
  experience: "positive" | "neutral" | "negative";
  process?: string | null;
  questions: string[];
  result: "offer" | "rejected" | "pending" | "no_response";
  created_at?: string | null;
  author?: string | null;
}

export interface SalaryInfo {
  company_id: string;
  median_k: number;
  p25_k?: number | null;
  p75_k?: number | null;
  sample_size: number;
  currency: string;
  by_role: Record<string, number>;
  last_updated?: string | null;
}

export interface CompanyBundle {
  company_id: string;
  aggregated_score?: number | null;
  ratings: CompanyRatingItem[];
  reviews: ReviewItem[];
  interviews: InterviewItem[];
  salary: SalaryInfo | null;
}

export async function getCompanyBundle(companyId: string): Promise<CompanyBundle> {
  return getJson<CompanyBundle>(`${API_BASE}/api/company-review/${companyId}`);
}

export async function getCompanyInterviews(
  companyId: string,
  page = 1,
  pageSize = 20
): Promise<{ items: InterviewItem[]; page: number; page_size: number }> {
  return getJson(
    `${API_BASE}/api/company-review/${companyId}/interviews?page=${page}&page_size=${pageSize}`
  );
}

export async function getCompanySalary(companyId: string): Promise<SalaryInfo> {
  return getJson<SalaryInfo>(`${API_BASE}/api/company-review/${companyId}/salary`);
}

export async function searchCompanies(
  query: string,
  limit = 20
): Promise<{ query: string; results: Array<{ id: string; name: string; industry: string; rating: number }>; total: number }> {
  return getJson(
    `${API_BASE}/api/company-review/search?q=${encodeURIComponent(query)}&limit=${limit}`
  );
}

export const SOURCE_LABEL: Record<string, string> = {
  kanzhun: "看准网",
  glassdoor: "Glassdoor",
  maimai: "脉脉",
  mock: "Mock",
  aggregated: "聚合",
};

export const SOURCE_COLOR: Record<string, string> = {
  kanzhun: "bg-blue-100 text-blue-800",
  glassdoor: "bg-emerald-100 text-emerald-800",
  maimai: "bg-purple-100 text-purple-800",
  mock: "bg-slate-100 text-slate-700",
  aggregated: "bg-amber-100 text-amber-800",
};