// Assessment API client (T1306)
"use client";

import { createClient } from "@/lib/supabase";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AssessmentInvitePayload {
  candidate_id: string;
  assessment_id: string;
  candidate_email?: string;
  candidate_name?: string;
  expires_in_hours?: number;
  job_id?: string;
  metadata?: Record<string, string>;
}

export interface AssessmentScore {
  name: string;
  value: number;
  max: number;
  band?: string | null;
}

export interface AssessmentResult {
  invitation_id: string;
  candidate_id: string;
  assessment_id: string;
  status: "pending" | "submitted" | "scored" | "expired";
  overall_score: number | null;
  percentile?: number | null;
  passed?: boolean | null;
  scores: AssessmentScore[];
  report_url?: string | null;
  completed_at?: string | null;
  provider: string;
  confidence?: string | null;  // very_high / high / medium / low / very_low
}

export interface AssessmentInvitation {
  id: string;
  invitation_id: string;
  candidate_id: string;
  provider: string;
  status: string;
  invite_url: string | null;
  expires_at: string | null;
  job_id?: string | null;
}

async function headers(): Promise<Record<string, string>> {
  try {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const token = session?.access_token || "";
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const h = await headers();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(h as Record<string, string>),
      ...((init?.headers as Record<string, string>) || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(
      `${init?.method || "GET"} ${path} → ${res.status}: ${body}`,
    );
  }
  return res.json() as Promise<T>;
}

export const assessmentApi = {
  invite: async (payload: AssessmentInvitePayload) =>
    request<{ ok: boolean; data: AssessmentInvitation }>(
      "/api/assessments/invite",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  result: async (invitationId: string) =>
    request<{ ok: boolean; data: AssessmentResult }>(
      `/api/assessments/${encodeURIComponent(invitationId)}/result`,
    ),

  list: async (params: { candidate_id?: string; job_id?: string } = {}) => {
    const search = new URLSearchParams();
    if (params.candidate_id) search.set("candidate_id", params.candidate_id);
    if (params.job_id) search.set("job_id", params.job_id);
    const qs = search.toString();
    return request<{ ok: boolean; data: AssessmentInvitation[]; count: number }>(
      `/api/assessments${qs ? "?" + qs : ""}`,
    );
  },
};
