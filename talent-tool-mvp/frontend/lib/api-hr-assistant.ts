/**
 * T6108 — HR Assistant API client (resume compare + interview questions).
 *
 * Talks to /api/hr-assistant/* on the FastAPI backend. Authenticated
 * employer (client) / admin only.
 */

import { fetchAPI } from "@/lib/api";
import { createClient } from "@/lib/supabase";

const BASE = "/api/hr-assistant";

// ---------------------------------------------------------------------------
// compare types (mirror ComparisonService DiffResult)
// ---------------------------------------------------------------------------

export interface DimensionScore {
  score: number;
  label?: string;
  detail?: Record<string, unknown>;
}

export interface CompareItem {
  id: string;
  name?: string;
  dimensions: Record<string, DimensionScore>;
}

export interface DiffDimension {
  dimension: string;
  spread: number;
  values: Record<string, number>;
}

export interface CompareResult {
  items: CompareItem[];
  dimensions: string[];
  diff_dimensions: DiffDimension[];
  highlights: DiffDimension[];
  title: string;
  role_id?: string | null;
  export_path?: string;
}

export interface CompareInput {
  candidate_ids: string[];
  role_id?: string;
  title?: string;
}

// ---------------------------------------------------------------------------
// interview question types (mirror QuestionBank Question)
// ---------------------------------------------------------------------------

export interface InterviewQuestion {
  id: string;
  title: string;
  prompt: string;
  expected_points: string[];
  skills: string[];
  difficulty: string;
  type: string;
  duration_sec: number;
  weights: Record<string, number>;
}

export interface InterviewQuestionTemplate {
  role: string;
  title: string;
  count: number;
  difficulty: string | null;
  estimated_minutes: number;
  questions: InterviewQuestion[];
}

export interface InterviewQuestionsInput {
  role: string;
  count?: number;
  difficulty?: string;
  title?: string;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function compareResumes(
  input: CompareInput
): Promise<CompareResult> {
  return fetchAPI<CompareResult>(`${BASE}/compare`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function generateInterviewQuestions(
  input: InterviewQuestionsInput
): Promise<InterviewQuestionTemplate> {
  return fetchAPI<InterviewQuestionTemplate>(`${BASE}/interview-questions`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/**
 * Build the export URL for a compare report. Uses a direct fetch (with the
 * Supabase access token) so the browser downloads the binary instead of
 * parsing it as JSON.
 */
export async function exportCompareReport(
  compareId: string,
  format: "txt" | "docx" | "pdf"
): Promise<Blob> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token ?? null;

  const url = `${process.env.NEXT_PUBLIC_API_URL ?? ""}${BASE}/compare/${compareId}/export?format=${format}`;
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw new Error(`导出失败: ${res.status} ${res.statusText}`);
  }
  return res.blob();
}
