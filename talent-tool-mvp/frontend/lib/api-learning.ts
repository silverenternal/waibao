/**
 * 学习资源 API 客户端 (T607)
 * 后端路由:
 *   GET /api/learning/search?skill=&limit=
 *   GET /api/learning/recommend?user_id=&gap_skills=
 */

import { fetchAPI } from "@/lib/api";

export interface LearningResource {
  title: string;
  provider: string;
  url: string;
  duration_hours: number;
  level: "beginner" | "intermediate" | "advanced" | string;
  rating: number;
  skill_tags: string[];
  description?: string;
  price?: number;
  language?: string;
  source?: "real" | "fallback" | string;
}

export async function searchLearningResources(
  skill: string,
  limit = 20,
): Promise<LearningResource[]> {
  const res = await fetchAPI<{ items: LearningResource[]; total: number }>(
    `/api/learning/search?skill=${encodeURIComponent(skill)}&limit=${limit}`,
    { retries: 1 },
  );
  return res.items ?? [];
}

export async function recommendLearningResources(
  gapSkills: string[],
  userId?: string,
  limit = 20,
): Promise<LearningResource[]> {
  const params = new URLSearchParams();
  params.set("gap_skills", gapSkills.join(","));
  params.set("limit", String(limit));
  if (userId) params.set("user_id", userId);
  const res = await fetchAPI<{ items: LearningResource[]; total: number }>(
    `/api/learning/recommend?${params.toString()}`,
    { retries: 1 },
  );
  return res.items ?? [];
}