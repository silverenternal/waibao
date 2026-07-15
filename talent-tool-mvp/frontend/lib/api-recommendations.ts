/**
 * T6104 — Recommendation records API client (push talent to employer).
 *
 * Talks to /api/recommendations/* on the FastAPI backend:
 *   GET    /api/recommendations               employer list (their org)
 *   GET    /api/recommendations/{id}          detail (score + reasons + gaps +
 *                                             risks + full resume + contact)
 *   PATCH  /api/recommendations/{id}/status   accept / reject
 *   GET    /api/recommendations/{id}/download resume text — ADMIN ONLY
 *
 * 甲方合同: 资料查看下载导出权限仅平台管理员 — the download endpoint is
 * admin-only on the backend; the UI hides the download button for non-admins
 * and surfaces can_download from the detail payload.
 */
import { fetchAPI } from "@/lib/api";

const BASE = "/api/recommendations";

export type RecommendationStatus =
  | "pending"
  | "viewed"
  | "accepted"
  | "rejected";

/** Resume snapshot captured at push time (immutable). */
export interface ResumeSnapshot {
  full_name?: string;
  title?: string;
  city?: string;
  skills?: string[];
  seniority?: string | null;
  education?: string | null;
  experience_years?: number | null;
  availability?: string | null;
  salary_min_k?: number | null;
  salary_max_k?: number | null;
  summary?: string;
  industries?: string[];
  captured_at?: string;
  [key: string]: unknown;
}

export interface ContactInfo {
  email?: string | null;
  phone?: string | null;
  linkedin_url?: string | null;
}

/** List-row shape (no PII). */
export interface RecommendationSummary {
  id: string;
  candidate_id: string;
  role_id: string;
  org_id: string;
  match_score: number;
  match_reasons: string[];
  skill_gaps: string[];
  risks: string[];
  candidate_name: string;
  candidate_title: string;
  role_title: string;
  company_name: string;
  status: RecommendationStatus;
  viewed_at: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
  rejected_reason: string | null;
  created_at: string;
  updated_at: string;
}

/** Detail shape (adds the full resume + contact + admin flag). */
export interface RecommendationDetail extends RecommendationSummary {
  resume_snapshot: ResumeSnapshot;
  contact_info: ContactInfo;
  can_download: boolean;
}

export interface ListRecommendationsParams {
  status?: RecommendationStatus;
  limit?: number;
  offset?: number;
  /** admin tooling only: inspect another org */
  org_id?: string;
}

// ---------------------------------------------------------------------------
// Calls
// ---------------------------------------------------------------------------

export async function listRecommendations(
  params: ListRecommendationsParams = {},
): Promise<RecommendationSummary[]> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.org_id) qs.set("org_id", params.org_id);
  const s = qs.toString();
  return fetchAPI<RecommendationSummary[]>(`${BASE}${s ? `?${s}` : ""}`);
}

export async function getRecommendation(
  id: string,
): Promise<RecommendationDetail> {
  return fetchAPI<RecommendationDetail>(
    `${BASE}/${encodeURIComponent(id)}`,
  );
}

export async function updateRecommendationStatus(
  id: string,
  status: "accepted" | "rejected" | "viewed",
  reason?: string,
): Promise<RecommendationSummary> {
  return fetchAPI<RecommendationSummary>(
    `${BASE}/${encodeURIComponent(id)}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({ status, reason }),
    },
  );
}

/**
 * Download the snapshot resume as plain text (admin only).
 * Returns the raw text body — the browser triggers the file save via the
 * Content-Disposition header set by the backend.
 */
export async function downloadRecommendationResume(
  id: string,
): Promise<string> {
  const res = await fetch(`${BASE}/${encodeURIComponent(id)}/download`, {
    method: "GET",
    headers: await authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`下载失败 (${res.status})`);
  }
  return res.text();
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function statusLabel(status: RecommendationStatus): string {
  switch (status) {
    case "pending":
      return "待处理";
    case "viewed":
      return "已查看";
    case "accepted":
      return "已接受";
    case "rejected":
      return "已拒绝";
    default:
      return status;
  }
}

export function statusTone(
  status: RecommendationStatus,
): "neutral" | "blue" | "green" | "red" {
  switch (status) {
    case "pending":
      return "neutral";
    case "viewed":
      return "blue";
    case "accepted":
      return "green";
    case "rejected":
      return "red";
    default:
      return "neutral";
  }
}

export function formatSalary(
  min: number | null | undefined,
  max: number | null | undefined,
): string {
  if (min == null && max == null) return "薪资面议";
  if (min != null && max != null) return `${min}-${max}K`;
  return `${min ?? max}K`;
}

async function authHeaders(): Promise<Record<string, string>> {
  // Lazy import to avoid pulling the supabase client into the module graph
  // for callers that only need the typed helpers above.
  const { createClient } = await import("@/lib/supabase");
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token
    ? { Authorization: `Bearer ${session.access_token}` }
    : {};
}
