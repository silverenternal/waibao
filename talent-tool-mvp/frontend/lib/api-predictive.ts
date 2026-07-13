// Predictive Analytics API client (T2803) — LightGBM + Prophet

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

async function authedFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("sb_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!res.ok) {
    throw new Error(`predictive ${path} ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

// -------------------------------------------------------------------
// Types
// -------------------------------------------------------------------
export type RiskLevel = "low" | "medium" | "high";

export interface AttritionFactor {
  feature: string;
  impact: number;
  direction: string;
}

export interface AttritionRisk {
  user_id: string;
  risk_score: number;
  risk_level: RiskLevel;
  factors: AttritionFactor[];
  explanation: string;
  intervention: string[];
  model_used: string;
  inference_ms: number;
  computed_at: string;
}

export interface TeamAttrition {
  org_id: string;
  n: number;
  high: number;
  medium: number;
  low: number;
  users: AttritionRisk[];
}

export interface HireSuccess {
  candidate_id: string;
  success_score: number;
  drivers: Array<{ feature: string; impact: number }>;
  model_used: string;
  inference_ms: number;
  explanation: string;
  computed_at: string;
}

export interface ForecastPoint {
  ds: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
}

export interface ForecastResult {
  metric: string;
  horizon_days: number;
  history_days: number;
  points: ForecastPoint[];
  model_used: string;
  trend_slope: number;
  computed_at: string;
}

export interface PredictiveHealth {
  ok: boolean;
  attrition_loaded: boolean;
  hire_success_loaded: boolean;
  models_dir: string | null;
}

export interface RetrainResult {
  status: string;
  duration_seconds: number;
  metrics: {
    attrition: { auc: number; n: number };
    hire_success: { rmse: number; n: number };
    prophet_trained: boolean;
  };
}

// -------------------------------------------------------------------
// Client
// -------------------------------------------------------------------
export const predictiveApi = {
  attrition: (userId: string) =>
    authedFetch<AttritionRisk>(`/api/predictive/attrition/${userId}`),
  teamAttrition: (orgId: string, userIds: string[]) =>
    authedFetch<TeamAttrition>(
      `/api/predictive/attrition/team/${orgId}?user_ids=${userIds.join(",")}`
    ),
  hireSuccess: (candidateId: string) =>
    authedFetch<HireSuccess>(`/api/predictive/hire-success/${candidateId}`),
  forecast: (params: {
    metric?: string;
    horizonDays?: number;
    historyDays?: number;
    seed?: string;
  } = {}) => {
    const q = new URLSearchParams();
    q.set("metric", params.metric ?? "candidate_inflow");
    q.set("horizon_days", String(params.horizonDays ?? 30));
    q.set("history_days", String(params.historyDays ?? 90));
    q.set("seed", params.seed ?? "default");
    return authedFetch<ForecastResult>(
      `/api/predictive/forecast?${q.toString()}`
    );
  },
  retrain: (n = 2000) =>
    authedFetch<RetrainResult>(`/api/predictive/retrain?n=${n}`, {
      method: "POST",
    }),
  health: () => authedFetch<PredictiveHealth>("/api/predictive/health"),
  models: () =>
    authedFetch<{
      attrition: { loaded: boolean; path: string | null };
      hire_success: { loaded: boolean };
      prophet_metric: string | null;
    }>("/api/predictive/models"),
};

// -------------------------------------------------------------------
// Display helpers
// -------------------------------------------------------------------
export const RISK_LEVEL_COLOR: Record<RiskLevel, string> = {
  low: "bg-emerald-100 text-emerald-800 border-emerald-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  high: "bg-red-100 text-red-800 border-red-200",
};

export const RISK_LEVEL_LABEL: Record<RiskLevel, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};

export const FEATURE_LABEL: Record<string, string> = {
  emotion_avg_30d: "情绪分数 (30d)",
  journal_freq_30d: "日志频率 (30d)",
  interaction_gap_avg_h: "平均互动间隔",
  negative_tickets_30d: "负面工单数",
  task_completion_rate_30d: "任务完成率",
  tenure_months: "司龄 (月)",
  last_promotion_months: "距上次晋升",
  match_score: "匹配分",
  channel_idx: "渠道",
  seniority_idx: "资历",
  time_to_decision_h: "决策时长 (h)",
  eval_clarity: "评估 - 表达清晰度",
  eval_culture: "评估 - 文化匹配",
  eval_technical: "评估 - 技术能力",
  city_match: "城市匹配",
  remote_ok: "远程可",
};
