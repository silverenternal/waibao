/**
 * T6106 — Hard-condition matching API client (甲方合同版).
 *
 * Talks to the T6105 backend endpoint:
 *   POST /api/matches/hard-filter/{role_id}   不淘汰只排序的硬条件匹配
 *
 * Returns a ranked list of MatchResultItem (match_score 0-100 + reasons +
 * gaps + risks + hard_conditions + high_priority).
 */
import { fetchAPI } from "@/lib/api";

export interface HardConditionDetail {
  name: string;
  satisfied: boolean;
  detail: Record<string, unknown>;
}

export interface MatchResultItem {
  candidate_id?: string | null;
  role_id?: string | null;
  match_score: number;
  match_reasons: string[];
  skill_gaps: string[];
  risks: string[];
  hard_conditions?: Record<string, HardConditionDetail>;
  high_priority?: Record<string, number>;
  passed_hard?: boolean;
}

export interface HardFilterResponse {
  role_id: string;
  total: number;
  passed_hard: number;
  items: MatchResultItem[];
}

export async function runHardFilterMatch(
  roleId: string,
  opts: { topK?: number } = {},
): Promise<HardFilterResponse> {
  const qs = opts.topK != null ? `?top_k=${opts.topK}` : "";
  return fetchAPI<HardFilterResponse>(
    `/api/matches/hard-filter/${encodeURIComponent(roleId)}${qs}`,
    { method: "POST" },
  );
}
