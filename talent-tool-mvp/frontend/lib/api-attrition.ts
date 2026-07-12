/**
 * Attrition Prediction API client (T2403).
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

export interface RiskFactor {
  key: string;
  contribution: number;
  description: string;
}

export interface AttritionRisk {
  user_id: string;
  risk_score: number;
  risk_level: "low" | "medium" | "high";
  factors: RiskFactor[];
  explanation: string;
  model_used: "lightgbm" | "llm" | "rules";
  computed_at: string;
}

export interface TeamRisk {
  org_id: string;
  total: number;
  high_risk: number;
  medium_risk: number;
  low_risk: number;
  avg_risk_score: number;
  risk_users: AttritionRisk[];
  computed_at: string;
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url, {
    method: "GET",
    headers: await authHeaders(),
    credentials: "include",
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json() as Promise<T>;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const resp = await fetch(url, {
    method: "POST",
    headers: await authHeaders(),
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json() as Promise<T>;
}

export async function getUserRisk(userId: string): Promise<AttritionRisk> {
  return getJson<AttritionRisk>(
    `${API_BASE}/api/attrition/risk/${encodeURIComponent(userId)}`
  );
}

export async function getTeamRisk(
  orgId: string,
  userIds: string[]
): Promise<TeamRisk> {
  const ids = userIds.join(",");
  return getJson<TeamRisk>(
    `${API_BASE}/api/attrition/risk/team/${encodeURIComponent(orgId)}?user_ids=${ids}`
  );
}

export async function sendCareMessage(
  userId: string,
  message: string,
  channel: "im" | "email" | "dingtalk" = "im"
): Promise<{ status: string; user_id: string; channel: string }> {
  return postJson(`${API_BASE}/api/attrition/care`, {
    user_id: userId,
    message,
    channel,
  });
}

export async function retrainModel(notes = ""): Promise<{ status: string }> {
  return postJson(`${API_BASE}/api/attrition/retrain`, { notes });
}

export const RISK_LEVEL_COLOR: Record<string, string> = {
  low: "bg-emerald-100 text-emerald-800 border-emerald-300",
  medium: "bg-amber-100 text-amber-800 border-amber-300",
  high: "bg-rose-100 text-rose-800 border-rose-300",
};

export const RISK_LEVEL_LABEL: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};