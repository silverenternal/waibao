/**
 * 计划追踪 API 客户端 (T607)
 * 后端路由:
 *   POST /api/plan/adjust     {user_id, action, target_item, detail, delta_days}
 *   POST /api/plan/checkin    {user_id, item_title, progress_delta, note}
 *   GET  /api/plan/progress/{user_id}
 *   POST /api/plan/init       {user_id, plan_data}
 *   GET  /api/plan/history/{user_id}
 */

import { fetchAPI } from "@/lib/api";

export type PlanAdjustAction =
  | "delay"
  | "accelerate"
  | "replace"
  | "add"
  | "remove";

export interface PlanItemProgress {
  title: string;
  progress: number;
  completed: boolean;
  duration: string;
  priority: string;
  bucket: "short" | "mid" | "long";
}

export interface PlanProgress {
  user_id: string;
  plan_id: string | null;
  overall_progress: number;
  items: PlanItemProgress[];
  upcoming_milestones: Array<{
    title: string;
    target_date: string;
    completed: boolean;
    progress: number;
    notes: string;
  }>;
  stale_items: string[];
  updated_at?: string;
}

export async function fetchPlanProgress(
  userId: string,
): Promise<PlanProgress> {
  return fetchAPI<PlanProgress>(
    `/api/plan/progress/${encodeURIComponent(userId)}`,
    { retries: 1 },
  );
}

export async function checkin(
  userId: string,
  itemTitle: string,
  progressDelta = 0.1,
  note = "",
): Promise<{ status: string; checkin: unknown }> {
  return fetchAPI("/api/plan/checkin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      item_title: itemTitle,
      progress_delta: progressDelta,
      note,
    }),
    retries: 1,
  });
}

export async function adjustPlan(
  userId: string,
  action: PlanAdjustAction,
  targetItem: string,
  detail = "",
  deltaDays = 0,
): Promise<{ status: string; adjustment: unknown }> {
  return fetchAPI("/api/plan/adjust", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      action,
      target_item: targetItem,
      detail,
      delta_days: deltaDays,
    }),
    retries: 1,
  });
}

export async function initPlan(
  userId: string,
  planData: Record<string, unknown>,
): Promise<{ status: string; plan: unknown }> {
  return fetchAPI("/api/plan/init", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, plan_data: planData }),
    retries: 1,
  });
}

export interface CheckinRecord {
  plan_id: string;
  user_id: string;
  item_title: string;
  progress_delta: number;
  note: string;
  created_at: string;
}

export async function fetchPlanHistory(userId: string): Promise<{
  user_id: string;
  checkins: CheckinRecord[];
  adjustments: Array<{
    plan_id: string;
    user_id: string;
    action: string;
    target_item: string;
    detail: string;
    delta_days: number;
    created_at: string;
  }>;
}> {
  return fetchAPI(`/api/plan/history/${encodeURIComponent(userId)}`, {
    retries: 1,
  });
}