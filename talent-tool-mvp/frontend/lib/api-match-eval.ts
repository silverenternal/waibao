/**
 * T902 — 互评对照 API client.
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

export interface EvalScores {
  skill?: number;
  communication?: number;
  culture?: number;
  potential?: number;
  comment?: string;
}

export interface DivergentDimension {
  dimension: string;
  candidate: number;
  employer: number;
  gap: number;
}

export interface EvalComment {
  id: string;
  match_id: string;
  author_id: string;
  author_role: string;
  body: string;
  dimension?: string | null;
  created_at: string;
}

export interface EvalComparison {
  match_id: string;
  candidate_eval: EvalScores | null;
  employer_eval: EvalScores | null;
  aligned_strengths: string[];
  aligned_concerns: string[];
  divergent_dimensions: DivergentDimension[];
  overall_alignment: number;
  discussion_room_id: string | null;
  comments: EvalComment[];
}

export const matchEvalApi = {
  async get(matchId: string): Promise<EvalComparison> {
    const h = await authHeaders();
    const r = await fetch(`${API_BASE}/api/match/eval/${matchId}`, { headers: h });
    if (!r.ok) throw new Error(`eval get failed: ${r.status}`);
    return r.json();
  },

  async startDiscussion(
    matchId: string,
    body: { topic?: string; participants?: string[] } = {}
  ): Promise<{ match_id: string; room_id: string; topic: string; status: string }> {
    const h = await authHeaders();
    const r = await fetch(`${API_BASE}/api/match/eval/${matchId}/discuss`, {
      method: "POST",
      headers: h,
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`discuss failed: ${r.status}`);
    return r.json();
  },

  async postComment(
    matchId: string,
    body: { body: string; dimension?: string; author_role?: string }
  ): Promise<{ comment: EvalComment }> {
    const h = await authHeaders();
    const r = await fetch(`${API_BASE}/api/match/eval/${matchId}/comments`, {
      method: "POST",
      headers: h,
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`comment failed: ${r.status}`);
    return r.json();
  },
};