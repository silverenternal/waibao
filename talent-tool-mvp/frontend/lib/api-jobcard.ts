/**
 * T6107 — Job card API client.
 *
 * Wraps the talent-market job detail endpoint and exposes the 4-part
 * 甲方岗位卡 contract:
 *   1. 职责 (responsibilities)
 *   2. 硬条件 (skills_required + education + certificates_required)
 *   3. 加分项 (nice_to_have / skills_preferred)
 *   4. 边界 (boundaries + work_schedule + travel_required + city/remote)
 *
 * Talks to: GET /api/talent-market/jobs/{id}
 */
import { fetchAPI } from "@/lib/api";

export interface JobCard {
  id: string;
  company: string;
  company_industry: string;
  title: string;
  city: string;
  salary_min_k: number | null;
  salary_max_k: number | null;
  skills_required: string[];
  skills_preferred: string[];
  seniority: string | null;
  education: string | null;
  experience_years: string | null;
  remote_policy: string;
  match_score: number;
  posted_at: string;
  certificates_required: string[];
}

export interface JobCardDetail extends JobCard {
  description: string | null;
  responsibilities: string[];
  requirements: string[];
  benefits: string[];
  headcount: number;
  nice_to_have: string[];
  boundaries: string[];
  work_schedule: string;
  travel_required: string;
}

/**
 * Fetch the full job card (4-part 甲方 contract).
 * Re-uses the existing talent-market job detail payload; the typed
 * JobCardDetail here is the canonical shape the JobCard page renders.
 */
export async function fetchJobCard(id: string): Promise<JobCardDetail> {
  return fetchAPI<JobCardDetail>(
    `/api/talent-market/jobs/${encodeURIComponent(id)}`,
  );
}

/** Build the 4 hard-condition chips from a job card (技能/学历/证书). */
export function buildHardConditions(job: JobCard): string[] {
  const out: string[] = [];
  if (job.skills_required.length > 0) {
    out.push(`技能: ${job.skills_required.join(" / ")}`);
  }
  if (job.education) {
    out.push(`学历: ${job.education}`);
  }
  if (job.experience_years) {
    out.push(`经验: ${job.experience_years}`);
  }
  if (job.certificates_required.length > 0) {
    out.push(`证书: ${job.certificates_required.join(" / ")}`);
  }
  return out;
}

/** Build the "加分项" list (preferred skills + nice_to_have, deduped). */
export function buildNiceToHave(job: JobCardDetail): string[] {
  const merged = [...(job.nice_to_have || [])];
  for (const s of job.skills_preferred || []) {
    if (!merged.some((m) => m.toLowerCase() === s.toLowerCase())) {
      merged.push(s);
    }
  }
  return merged;
}

/** Build the "边界" list (工作时间/地点/出差/不做什么). */
export function buildBoundaries(job: JobCardDetail): string[] {
  const out = [...(job.boundaries || [])];
  if (out.length === 0) {
    if (job.work_schedule) out.push(`工作时间: ${job.work_schedule}`);
    out.push(`工作地点: ${job.city}`);
    if (job.travel_required) out.push(`出差要求: ${job.travel_required}`);
  }
  return out;
}

export function remotePolicyLabel(policy: string): string {
  switch (policy) {
    case "remote":
      return "远程";
    case "hybrid":
      return "混合办公";
    case "onsite":
    default:
      return "坐班";
  }
}

export function formatSalary(min: number | null, max: number | null): string {
  if (min == null && max == null) return "薪资面议";
  if (min != null && max != null) return `${min}-${max}K`;
  return `${min ?? max}K`;
}
