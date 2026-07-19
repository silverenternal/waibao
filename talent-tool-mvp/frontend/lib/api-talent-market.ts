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
 * v11.2 (T6304) — threshold-visibility:
 *   POST /api/talent-market/initiate-contact  (open a comm channel)
 *   GET  /api/talent-market/channels          (list my comm channels)
 *
 * PII note: talent contact fields (full_name/email/phone/linkedin) are only
 * populated when the caller is an authenticated employer/admin; anonymous
 * and seeker callers receive masked cards.
 *
 * Threshold rule (甲方): only matches ≥ MATCH_THRESHOLD (70%) are mutually
 * visible & contactable. Below the threshold neither side can see each other.
 * The employer talent list is already server-side filtered to ≥ threshold;
 * anonymous users receive masked cards with `can_contact=false` and no real
 * match score. 匹配因素含 五险一金 + 出差 (高优先级, soft scoring — never
 * eliminate).
 */

import { fetchAPI, type PaginatedResponse } from "@/lib/api";

const BASE = "/api/talent-market";

/** 甲方阀值: 双方仅当匹配度 ≥ 70% 才互可见且可发起沟通. */
export const MATCH_THRESHOLD = 70;

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

// ---------------------------------------------------------------------------
// v11.2 (T6302) — identity / compensation / threshold enums
// ---------------------------------------------------------------------------

/** identity_status / id_card_status / education_doc_status / resume_status */
export type IdentityStatus = "pending" | "submitted" | "verified";

/** candidate travel_tolerance */
export type TravelTolerance = "willing" | "occasional" | "unwilling";

/** role travel_required */
export type TravelRequirement = "none" | "occasional" | "frequent";

/** who opened a communication channel */
export type ChannelInitiator = "candidate" | "employer";

export interface CommunicationChannel {
  id: number;
  candidate_id: string;
  role_id: string;
  org_id: string;
  initiated_by: ChannelInitiator;
  match_score: number | null;
  status: "open" | "closed";
  created_at: string;
  updated_at: string;
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
  /**
   * v11.2 viewer-aware fields (all optional — masked/anonymous cards omit).
   * can_contact=false & absent best_role_id/score => below threshold or anon.
   */
  can_contact?: boolean;
  /** best matching role id for the current employer viewer (used by initiate-contact). */
  best_role_id?: string | null;
  /** true once a communication channel is already open. */
  comm_channel_open?: boolean;
  /** candidate expects 五险一金. */
  social_insurance_expectation?: boolean | null;
  /** candidate 出差接受度. */
  travel_tolerance?: TravelTolerance | null;
  /** identity verification display status (待上传 / 待审核 / 已认证). */
  identity_status?: IdentityStatus | null;
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
  /**
   * v11.2 viewer-aware fields (all optional — masked/anonymous cards omit).
   */
  can_contact?: boolean;
  /** best matching candidate (talent) id for the current seeker viewer. */
  best_role_id?: string | null;
  comm_channel_open?: boolean;
  /** role offers 五险一金 (default true per migration). */
  offers_social_insurance?: boolean | null;
  /** role offers 住房公积金. */
  offers_housing_fund?: boolean | null;
  /** role 出差要求. */
  travel_required?: TravelRequirement | null;
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
// v11.2 (T6304) — threshold-visibility: initiate contact + channels
// ---------------------------------------------------------------------------

/**
 * Open a communication channel with the other party. Requires match_score ≥
 * MATCH_THRESHOLD; the backend enforces the threshold and rejects below it.
 *
 * - Employer initiates against a talent:  { talent_id, role_id }
 * - Talent initiates against a job:       { role_id } (candidate inferred from token)
 *
 * roleId should come from the card's `best_role_id`. Returns the (possibly
 * already-open) channel.
 */
export async function initiateContact(params: {
  talentId?: string;
  roleId: string;
}): Promise<CommunicationChannel> {
  const body: Record<string, string> = { role_id: params.roleId };
  if (params.talentId) body.talent_id = params.talentId;
  return fetchAPI<CommunicationChannel>(`${BASE}/initiate-contact`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** List communication channels visible to the current viewer (own channels). */
export async function listChannels(): Promise<CommunicationChannel[]> {
  return fetchAPI<CommunicationChannel[]>(`${BASE}/channels`);
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

// ---------------------------------------------------------------------------
// v11.2 (T6302) — compensation / identity display maps
// ---------------------------------------------------------------------------

/** role travel_required → 出差 label. */
export function travelRequiredLabel(req: TravelRequirement | null | undefined): string {
  switch (req) {
    case "none":
      return "不出差";
    case "occasional":
      return "偶尔出差";
    case "frequent":
      return "频繁出差";
    default:
      return "";
  }
}

/** candidate travel_tolerance → 出差接受度 label. */
export function travelToleranceLabel(t: TravelTolerance | null | undefined): string {
  switch (t) {
    case "willing":
      return "接受出差";
    case "occasional":
      return "可偶尔出差";
    case "unwilling":
      return "不愿出差";
    default:
      return "";
  }
}

/** identity_status → 待上传 / 待审核 / 已认证. */
export function identityStatusLabel(s: IdentityStatus | null | undefined): string {
  switch (s) {
    case "pending":
      return "待上传";
    case "submitted":
      return "待审核";
    case "verified":
      return "已认证";
    default:
      return "";
  }
}
