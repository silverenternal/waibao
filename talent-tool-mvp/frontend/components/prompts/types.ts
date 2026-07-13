// T2704: Prompt v2 admin UI types — mirror backend services.platform.prompt_v2.

export type PromptStatus = "draft" | "active" | "retired";

export interface PromptVersion {
  id: string;
  tenant_id: string;
  name: string;
  agent: string;
  version: number;
  content: string;
  description: string;
  variables: string[];
  tags: string[];
  traffic_pct: number;
  status: PromptStatus;
  parent_version?: number | null;
  created_by: string;
  created_at: number;
  updated_at: number;
  retired_at?: number | null;
  metadata: Record<string, unknown>;
}

export interface PromptMetric {
  prompt_id: string;
  version: number;
  metric_name: string;
  value: number;
  sample_size: number;
  computed_at: number;
}

export interface PromptSummary {
  name: string;
  agent: string;
  versions: number;
  active: number;
  latest_version: number;
}

export interface EvalRun {
  id: string;
  prompt_id: string;
  version: number;
  case_count: number;
  judge_model: string;
  summary: {
    accuracy: number;
    fluency: number;
    safety: number;
    bias: number;
    overall: number;
  };
  started_at: number;
  finished_at?: number | null;
}

export interface PromptDiff {
  left: { id: string; version: number; status: PromptStatus };
  right: { id: string; version: number; status: PromptStatus };
  diff: string;
  changed: boolean;
  size_left: number;
  size_right: number;
}