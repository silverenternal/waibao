/**
 * A/B 实验管理 API client (T805).
 *
 * Endpoint base: ${NEXT_PUBLIC_API_URL}/api/admin/ab.
 */

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

async function authHeaders(token: string | null) {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

async function getToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("sb_token") || null;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ExperimentStatus = "draft" | "running" | "stopped" | "completed";

export interface VariantPayload {
  name: string;
  weight: number;
  config?: Record<string, unknown>;
}

export interface ExperimentRow {
  id: string;
  name: string;
  description: string;
  status: ExperimentStatus;
  primary_metric: string;
  variants: VariantPayload[];
  metadata?: Record<string, unknown>;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResultsVariant {
  name: string;
  mean: number;
  stddev: number;
  n: number;
  lift_vs_baseline: number;
  p_value: number;
  is_baseline: boolean;
}

export interface ResultsSummary {
  experiment_id: string;
  metric_name: string;
  baseline: string | null;
  variants: ResultsVariant[];
  confidence: number;
  significant: boolean;
  n_total: number;
}

export interface BuiltinMetricInfo {
  metrics: string[];
  hash_salt_preview: string;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const abApi = {
  async listBuiltinMetrics(): Promise<BuiltinMetricInfo> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/ab/metrics`, {
      headers: await authHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Failed to list metrics: ${res.status}`);
    return res.json();
  },

  async listExperiments(status?: ExperimentStatus): Promise<ExperimentRow[]> {
    const token = await getToken();
    const url = new URL(`${API_BASE}/api/admin/ab/experiments`);
    if (status) url.searchParams.set("status", status);
    const res = await fetch(url.toString(), {
      headers: await authHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Failed to list experiments: ${res.status}`);
    const json = (await res.json()) as { data: ExperimentRow[] };
    return json.data || [];
  },

  async getExperiment(id: string): Promise<ExperimentRow> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/ab/experiments/${id}`, {
      headers: await authHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Failed to fetch experiment: ${res.status}`);
    const json = (await res.json()) as { data: ExperimentRow };
    return json.data;
  },

  async createExperiment(body: {
    name: string;
    description?: string;
    primary_metric?: string;
    variants: VariantPayload[];
  }): Promise<ExperimentRow> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/ab/experiments`, {
      method: "POST",
      headers: await authHeaders(token),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`Failed to create: ${res.status} ${txt}`);
    }
    const json = (await res.json()) as { data: ExperimentRow };
    return json.data;
  },

  async updateExperiment(
    id: string,
    patch: Partial<Pick<ExperimentRow, "description" | "primary_metric" | "variants" | "status" | "metadata">>
  ): Promise<ExperimentRow> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/ab/experiments/${id}`, {
      method: "PATCH",
      headers: await authHeaders(token),
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error(`Failed to update: ${res.status}`);
    const json = (await res.json()) as { data: ExperimentRow };
    return json.data;
  },

  async startExperiment(id: string): Promise<ExperimentRow> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/ab/experiments/${id}/start`, {
      method: "POST",
      headers: await authHeaders(token),
    });
    if (!res.ok) throw new Error(`Failed to start: ${res.status}`);
    const json = (await res.json()) as { data: ExperimentRow };
    return json.data;
  },

  async stopExperiment(id: string): Promise<ExperimentRow> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/ab/experiments/${id}/stop`, {
      method: "POST",
      headers: await authHeaders(token),
    });
    if (!res.ok) throw new Error(`Failed to stop: ${res.status}`);
    const json = (await res.json()) as { data: ExperimentRow };
    return json.data;
  },

  async deleteExperiment(id: string): Promise<number> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/ab/experiments/${id}`, {
      method: "DELETE",
      headers: await authHeaders(token),
    });
    if (!res.ok) throw new Error(`Failed to delete: ${res.status}`);
    const json = (await res.json()) as { deleted: number };
    return json.deleted;
  },

  async getResults(id: string, metricName?: string): Promise<ResultsSummary> {
    const token = await getToken();
    const url = new URL(`${API_BASE}/api/admin/ab/experiments/${id}/results`);
    if (metricName) url.searchParams.set("metric_name", metricName);
    const res = await fetch(url.toString(), {
      headers: await authHeaders(token),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Failed to fetch results: ${res.status}`);
    const json = (await res.json()) as { data: ResultsSummary };
    return json.data;
  },

  async recordMetric(body: {
    experiment_id: string;
    variant: string;
    metric_name: string;
    value: number;
    user_id?: string;
  }): Promise<void> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/ab/record-metric`, {
      method: "POST",
      headers: await authHeaders(token),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Failed to record metric: ${res.status}`);
  },

  async previewAssignment(body: {
    user_id: string;
    name?: string;
    variants: VariantPayload[];
    status?: ExperimentStatus;
  }): Promise<{ user_id: string; variant: string }> {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/api/admin/ab/assign-preview`, {
      method: "POST",
      headers: await authHeaders(token),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Failed to preview: ${res.status}`);
    return res.json();
  },
};
