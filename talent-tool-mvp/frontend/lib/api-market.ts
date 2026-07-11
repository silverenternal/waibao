/**
 * 招聘市场 API 客户端 (T607)
 * 后端路由: /api/career-plan + /api/job-market/*
 */

import { fetchAPI, ApiError } from "@/lib/api";

export interface SalaryPoint {
  period: string; // YYYY-MM
  median_k: number;
  p25_k?: number | null;
  p75_k?: number | null;
  sample_size?: number | null;
  currency: string;
}

export interface SkillDemand {
  skill: string;
  demand_score: number;
  job_count: number;
  growth_pct?: number | null;
}

export interface JobPosting {
  source: string;
  external_id: string;
  title: string;
  company: string;
  city?: string | null;
  salary_min_k?: number | null;
  salary_max_k?: number | null;
  salary_currency: string;
  experience_years?: string | null;
  education?: string | null;
  skills: string[];
  url?: string | null;
  posted_at?: string | null;
  description_snippet?: string | null;
}

export interface MarketInsights {
  salary_trends: SalaryPoint[];
  hot_skills: SkillDemand[];
  sample_jobs: JobPosting[];
  provider: string;
}

export async function fetchMarketInsights(
  targetRole: string,
  city = "上海",
  skills: string[] = [],
): Promise<MarketInsights> {
  // CareerPlannerAgent 已经把 market_insights 嵌入到 plan 输出
  // 这里调用 career-plan/generate 拿到最新市场快照 (轻量)
  try {
    const res = await fetchAPI<{ plan?: { market_insights?: MarketInsights } }>(
      "/api/career-plan/generate",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_role: targetRole,
          city,
          skills,
        }),
        retries: 1,
      },
    );
    return (
      res.plan?.market_insights ?? {
        salary_trends: [],
        hot_skills: [],
        sample_jobs: [],
        provider: "unknown",
      }
    );
  } catch (e) {
    if (e instanceof ApiError) {
      // 兜底 — 返回空结构,UI 走空态
      return {
        salary_trends: [],
        hot_skills: [],
        sample_jobs: [],
        provider: "error",
      };
    }
    throw e;
  }
}

export async function searchJobs(
  keyword: string,
  city?: string,
  pageSize = 20,
): Promise<JobPosting[]> {
  // 后端真实端点未直接暴露 /job-market/* (统一在 career-plan 中聚合),
  // 这里走 career-plan/generate 的 sample_jobs 字段
  const mi = await fetchMarketInsights(keyword, city);
  return mi.sample_jobs.slice(0, pageSize);
}

export async function fetchSalaryTrend(
  role: string,
  city = "上海",
): Promise<SalaryPoint[]> {
  const mi = await fetchMarketInsights(role, city);
  return mi.salary_trends;
}

export async function fetchHotSkills(role?: string): Promise<SkillDemand[]> {
  const mi = await fetchMarketInsights(role || "Python 后端");
  return mi.hot_skills;
}