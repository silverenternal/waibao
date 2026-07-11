/**
 * T901 — 匹配可解释性 API client.
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

export interface MatchExplanation {
  match_id: string;
  reasons: string[];
  weak_points: string[];
  model_version?: string;
}

export interface MatchCounterfactual {
  match_id: string;
  if_have: string;
  score_lift: number;
  model_version?: string;
}

export const matchExplainApi = {
  async getExplain(matchId: string): Promise<MatchExplanation> {
    const h = await authHeaders();
    const r = await fetch(`${API_BASE}/api/match/${matchId}/explain`, { headers: h });
    if (!r.ok) throw new Error(`getExplain failed: ${r.status}`);
    return r.json();
  },

  async getCounterfactual(matchId: string): Promise<MatchCounterfactual> {
    const h = await authHeaders();
    const r = await fetch(`${API_BASE}/api/match/${matchId}/counterfactual`, {
      headers: h,
    });
    if (!r.ok) throw new Error(`getCounterfactual failed: ${r.status}`);
    return r.json();
  },
};