/**
 * T6103 — Recruitment Marketplace API client.
 *
 * Two-sided talent/job market: jobseekers store profiles, employers store
 * open roles, both sides browse and get match recommendations.
 *
 * Backend routes (public browse, no auth needed for listings):
 *   GET /api/talent-market/stats
 *   GET /api/talent-market/recommendations
 *   GET /api/talent-market/talents            (paginated + filtered)
 *   GET /api/talent-market/talents/{id}       (full resume for employer)
 *   GET /api/talent-market/jobs               (paginated + filtered)
 *   GET /api/talent-market/jobs/{id}          (job card)
 *
 * PII note: talent contact fields (full_name/email/phone/linkedin) are only
 * populated when the caller is an authenticated employer/admin; anonymous
 * and seeker callers receive masked cards.
 */

import { fetchAPI, type PaginatedResponse } from "@/lib/api";

const BASE = "/api/talent-market";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MarketStats {
  talents_total: number;
  talents_online: number;
  jobs_total: number;
  companies_total: number;
  matches_total: number;
}

export interface TalentCard {
  id: string;
  name: string;
  title: string;
  city: string;
  skills: string[];
  seniority: string | null;
  education: string | null;
  salary_min_k: number | null;
  salary_max_k: number | null;
  experience_years: number | null;
  availability: string | null;
  match_score: number;
  online: boolean;
  avatar_color: string;
}

export interface TalentDetail extends TalentCard {
  full_name: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  summary: string | null;
  industries: string[];
}

export interface JobCard {
  id: string;
  company: string;
  company_industry: string;
  title: string;
  city: string;
  salary_min_k: number | null;
  salary_max_k: number | null;
  skills_required: string[];
  skills_preferred: string[];
  seniority: string | null;
  education: string | null;
  experience_years: string | null;
  remote_policy: string;
  match_score: number;
  posted_at: string;
}

export interface JobDetail extends JobCard {
  description: string | null;
  responsibilities: string[];
  requirements: string[];
  benefits: string[];
  headcount: number;
}

export interface MatchRecommendation {
  id: string;
  talent_id: string;
  talent_name: string;
  talent_title: string;
  job_id: string;
  job_title: string;
  company: string;
  score: number;
  reasons: string[];
}

export interface TalentFilters {
  keyword?: string;
  position?: string;
  skill?: string;
  city?: string;
  salary_min?: number;
  salary_max?: number;
  education?: string;
  page?: number;
  page_size?: number;
}

export interface JobFilters {
  keyword?: string;
  position?: string;
  city?: string;
  salary_min?: number;
  salary_max?: number;
  page?: number;
  page_size?: number;
}

// ---------------------------------------------------------------------------
// Calls
// ---------------------------------------------------------------------------

export async function fetchMarketStats(): Promise<MarketStats> {
  return fetchAPI<MarketStats>(`${BASE}/stats`);
}

export async function fetchRecommendations(
  limit = 5,
): Promise<MatchRecommendation[]> {
  return fetchAPI<MatchRecommendation[]>(
    `${BASE}/recommendations?limit=${limit}`,
  );
}

export async function fetchTalents(
  filters: TalentFilters = {},
): Promise<PaginatedResponse<TalentCard>> {
  return fetchAPI<PaginatedResponse<TalentCard>>(
    `${BASE}/talents?${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function fetchTalent(id: string): Promise<TalentDetail> {
  return fetchAPI<TalentDetail>(`${BASE}/talents/${encodeURIComponent(id)}`);
}

export async function fetchJobs(
  filters: JobFilters = {},
): Promise<PaginatedResponse<JobCard>> {
  return fetchAPI<PaginatedResponse<JobCard>>(
    `${BASE}/jobs?${buildQuery(filters as Record<string, unknown>)}`,
  );
}

export async function fetchJob(id: string): Promise<JobDetail> {
  return fetchAPI<JobDetail>(`${BASE}/jobs/${encodeURIComponent(id)}`);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildQuery(filters: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  return params.toString();
}

export function formatSalary(min: number | null, max: number | null): string {
  if (min == null && max == null) return "薪资面议";
  if (min != null && max != null) return `${min}-${max}K`;
  return `${min ?? max}K`;
}

export function remotePolicyLabel(policy: string): string {
  switch (policy) {
    case "remote":
      return "远程";
    case "hybrid":
      return "混合办公";
    case "onsite":
    default:
      return "坐班";
  }
}
