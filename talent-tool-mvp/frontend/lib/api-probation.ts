/**
 * Probation API client (T2404).
 */

export const DIMENSION_LABELS: Record<string, string> = {
  performance: "绩效",
  learning: "学习能力",
  integration: "团队融入",
  attitude: "工作态度",
  potential: "发展潜力",
};

export const DIMENSIONS = ["performance", "learning", "integration", "attitude", "potential"] as const;
export type DimensionKey = (typeof DIMENSIONS)[number];

export interface ProbationScores {
  performance: number;
  learning: number;
  integration: number;
  attitude: number;
  potential: number;
}

export interface ProbationReview {
  id: string;
  review_stage: "30" | "90" | "180" | "final" | "completion";
  review_date: string;
  scores: ProbationScores;
  comments?: string;
  status: "pending" | "submitted" | "passed" | "failed" | "extended";
}

export interface ProbationTask {
  id: string;
  type: string;
  title: string;
  description: string;
  due_at: string;
  completed_at?: string;
  reminded_at?: string;
}

export interface MyProbation {
  employee_id: string;
  latest_review?: ProbationReview;
  next_task?: ProbationTask;
  task_summary: {
    total: number;
    completed: number;
    pending: number;
    completion_rate: number;
  };
  is_confirmed: boolean;
  as_of: string;
}

export interface TeamProbation {
  org_id: string;
  stats: {
    total: number;
    on_track: number;
    at_risk: number;
    pending_review: number;
    confirmed: number;
  };
  employees: Array<{
    id: string;
    name: string;
    hire_date: string;
    tags: string[];
    latest_score?: number;
  }>;
}

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Probation API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchMyProbation(): Promise<MyProbation> {
  return http<MyProbation>("/api/probation/me");
}

export async function fetchTeamProbation(orgId: string): Promise<TeamProbation> {
  return http<TeamProbation>(`/api/probation/team/${encodeURIComponent(orgId)}`);
}

export async function submitReview(
  employeeId: string,
  orgId: string,
  reviewStage: string,
  scores: ProbationScores,
  comments: string,
): Promise<ProbationReview> {
  return http<ProbationReview>("/api/probation/reviews/submit", {
    method: "POST",
    body: JSON.stringify({
      employee_id: employeeId,
      org_id: orgId,
      review_stage: reviewStage,
      scores,
      comments,
    }),
  });
}

export async function extendProbation(reviewId: string, days: number, reason: string) {
  return http(`/api/probation/${reviewId}/extend`, {
    method: "POST",
    body: JSON.stringify({ extension_days: days, reason }),
  });
}

export async function completeProbation(reviewId: string, notes: string) {
  return http(`/api/probation/${reviewId}/complete`, {
    method: "POST",
    body: JSON.stringify({ notes }),
  });
}
