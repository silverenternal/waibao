// API client for video interviews (T1305)
"use client";

import { createClient } from "@/lib/supabase";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface VideoInterviewPayload {
  candidate_id: string;
  employer_id: string;
  host_email: string;
  topic: string;
  start_time: string;
  duration_min: number;
  participant_emails?: string[];
  preferred_provider?: "zoom" | "tencent_meeting" | "mock";
  ticket_id?: string;
  match_id?: string;
  calendar_tokens?: Record<string, string>;
}

export interface VideoInterview {
  id: string;
  meeting_id: string;
  provider: string;
  topic: string;
  start_time: string;
  duration_min: number;
  join_url: string;
  host_url?: string | null;
  password?: string | null;
  status: string;
  recording_id?: string | null;
  recording_url?: string | null;
}

export interface VideoRecording {
  video_interview_id: string;
  recording_id: string;
  status: string;
  play_url?: string | null;
  download_url?: string | null;
  duration_seconds: number;
  uploads_url?: string | null;
  provider: string;
}

async function getAuthHeaders(): Promise<Record<string, string>> {
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
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(headers as Record<string, string>),
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

export const videoInterviewApi = {
  list: async (params: { candidate_id?: string; employer_id?: string } = {}) => {
    const search = new URLSearchParams();
    if (params.candidate_id) search.set("candidate_id", params.candidate_id);
    if (params.employer_id) search.set("employer_id", params.employer_id);
    const qs = search.toString();
    return request<{ ok: boolean; data: VideoInterview[]; count: number }>(
      `/api/video-interviews${qs ? "?" + qs : ""}`,
    );
  },

  schedule: async (payload: VideoInterviewPayload) =>
    request<{ ok: boolean; data: VideoInterview }>(`/api/video-interviews`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  cancel: async (id: string) =>
    request<{ ok: boolean; data: { status: string } }>(
      `/api/video-interviews/${id}`,
      { method: "DELETE" },
    ),

  recording: async (id: string) =>
    request<{ ok: boolean; data: VideoRecording }>(
      `/api/video-interviews/${id}/recording`,
    ),
};
