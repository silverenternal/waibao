// BackgroundCheck API client (T1307)
"use client";

import { createClient } from "@/lib/supabase";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface BGCheckFinding {
  code: string;
  severity: string;
  description: string;
  category?: string | null;
}

export interface BGCheckStatus {
  check_id: string;
  candidate_id: string;
  status: "pending" | "in_progress" | "clear" | "consider" | "suspended";
  progress_pct: number;
  report_url?: string | null;
  findings: BGCheckFinding[];
  updated_at?: string | null;
  provider: string;
}

export interface BGCheckRecord {
  check_id: string;
  candidate_id: string;
  provider: string;
  status: string;
  report_url?: string | null;
  offer_id?: string | null;
  job_id?: string | null;
  created_at: string;
  completed_at?: string | null;
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

export const bgCheckApi = {
  initiate: async (payload: {
    candidate_id: string;
    candidate_email?: string;
    candidate_name?: string;
    offer_id?: string;
    job_id?: string;
    check_types?: { code: string; name?: string; required?: boolean }[];
  }) =>
    request<{ ok: boolean; data: BGCheckRecord }>(
      "/api/background-checks",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  triggerPreOffer: async (payload: {
    candidate_id: string;
    candidate_email?: string;
    candidate_name?: string;
    offer_id?: string;
    job_id?: string;
  }) =>
    request<{ ok: boolean; data: { skipped: boolean; data: BGCheckRecord } }>(
      "/api/background-checks/trigger-pre-offer",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  status: async (checkId: string) =>
    request<{ ok: boolean; data: BGCheckStatus }>(
      `/api/background-checks/${encodeURIComponent(checkId)}/status`,
    ),

  list: async (params: { candidate_id?: string; offer_id?: string } = {}) => {
    const search = new URLSearchParams();
    if (params.candidate_id) search.set("candidate_id", params.candidate_id);
    if (params.offer_id) search.set("offer_id", params.offer_id);
    const qs = search.toString();
    return request<{ ok: boolean; data: BGCheckRecord[]; count: number }>(
      `/api/background-checks${qs ? "?" + qs : ""}`,
    );
  },
};
