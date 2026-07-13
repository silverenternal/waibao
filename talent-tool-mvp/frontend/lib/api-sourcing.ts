/**
 * AI 主动 Sourcing API client (T3002).
 */
import { fetchAPI } from "@/lib/api";

export interface MatchScore {
  skill: number;
  experience: number;
  location: number;
  activity: number;
  seniority: number;
  overall: number;
}

export interface SourcedCandidate {
  id: string;
  source: string;
  name: string;
  headline?: string | null;
  location?: string | null;
  skills: string[];
  years_experience?: number | null;
  company?: string | null;
  profile_url?: string | null;
  avatar_url?: string | null;
  email?: string | null;
  followers: number;
  public_repos: number;
  top_languages: string[];
  match: MatchScore;
  reasons: string[];
}

export interface SearchRequest {
  title: string;
  skills?: string[];
  location?: string;
  seniority?: string;
  min_years?: number;
  keywords?: string[];
  target?: number;
}

export interface SearchResponse {
  job: { title: string; location?: string | null; skills: string[] };
  total: number;
  candidates: SourcedCandidate[];
}

export interface InviteResponse {
  status: string;
  candidate_id: string;
  candidate_name: string;
  job_title?: string | null;
  message: string;
}

export const MATCH_DIMENSIONS: { key: keyof MatchScore; label: string }[] = [
  { key: "skill", label: "技能" },
  { key: "experience", label: "经验" },
  { key: "location", label: "地域" },
  { key: "activity", label: "活跃度" },
  { key: "seniority", label: "资历" },
];

export async function searchCandidates(body: SearchRequest): Promise<SearchResponse> {
  return fetchAPI<SearchResponse>("/api/sourcing/search", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getCandidate(id: string): Promise<SourcedCandidate> {
  return fetchAPI<SourcedCandidate>(`/api/sourcing/candidates/${encodeURIComponent(id)}`);
}

export async function inviteCandidate(
  id: string,
  payload: { job_title?: string; message?: string },
): Promise<InviteResponse> {
  return fetchAPI<InviteResponse>(
    `/api/sourcing/candidates/${encodeURIComponent(id)}/invite`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}
