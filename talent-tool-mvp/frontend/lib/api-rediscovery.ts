/**
 * Rediscovery API client (T2406).
 */

export interface SleepyCandidate {
  id: string;
  name: string;
  email?: string;
  last_active_at?: string;
  dormant_days: number;
  job_titles: string[];
  skills: string[];
  city?: string;
  seniority?: string;
  salary_expect?: number;
  activity_score: number;
  fit_score: number;
  rediscover_potential: number;
  reason: string;
  recommended_roles: Array<{
    role_id: string;
    title: string;
    score: number;
    overlap_skills: string[];
  }>;
}

export interface ActivationPreview {
  candidate: SleepyCandidate;
  preview_message: string;
  suggested_strategy: string;
}

export interface RediscoveryStats {
  total_activations: number;
  converted: number;
  overall_conversion_rate: number;
  by_strategy: Record<
    string,
    { total: number; converted: number; rate: number }
  >;
  by_channel: Record<string, number>;
}

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`Rediscovery API error ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchSleepyCandidates(strategy = "standard") {
  return http<{
    strategy: string;
    threshold_days: number;
    count: number;
    candidates: SleepyCandidate[];
  }>(`/api/rediscovery/candidates?strategy=${strategy}`);
}

export async function previewActivation(candidateId: string) {
  return http<ActivationPreview>(
    `/api/rediscovery/candidates/${candidateId}/preview`,
  );
}

export async function activateCandidate(
  candidateId: string,
  payload: { strategy: string; channel: string; message?: string },
) {
  return http(`/api/rediscovery/${candidateId}/activate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchStats() {
  return http<RediscoveryStats>("/api/rediscovery/stats");
}

export async function fetchStrategies() {
  return http<{ strategies: Array<{ name: string; threshold: number; description: string }> }>(
    "/api/rediscovery/strategies",
  );
}
