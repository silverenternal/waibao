/**
 * JD API client (T604).
 *
 * Wraps three classes of endpoints:
 *   - GET    /api/jd-templates/list             → template library (filters)
 *   - GET    /api/jd-templates/{template_id}    → single template (full body)
 *   - POST   /api/job-spec/submit               → generate / re-generate JD
 *                                                 (returns over_spec_flags)
 *   - GET    /api/roles/{role_id}               → fetch the role being edited
 *   - PATCH  /api/roles/{role_id}               → save JD updates
 *   - GET    /api/roles/{role_id}/jd-versions   → list JD versions (history)
 *
 * The version-history endpoint isn't on the backend yet — it's expected to
 * land alongside the migration in `supabase/migrations/008_jd_versions.sql`.
 * For T604 the helper gracefully returns `[]` when the endpoint is absent
 * so the page can still render against local state.
 */

import { createClient } from "@/lib/supabase";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface JDTemplateSummary {
  id: string;
  industry: string;
  title: string;
  description: string;
  salary_band?: {
    currency?: string;
    min_k?: number;
    max_k?: number;
    period?: string;
    note?: string;
  } | null;
  responsibility_count: number;
  hard_requirement_count: number;
  nice_to_have_count: number;
  over_spec_warnings: string[];
}

export interface JDTemplateFull extends JDTemplateSummary {
  responsibilities: string[];
  hard_requirements: Array<{
    category: string;
    value: string;
    min_years?: number;
  }>;
  nice_to_haves: string[];
  team_culture?: Record<string, string>;
}

export interface OverSpecFlag {
  flag: string;
  level?: "red" | "amber" | "green";
  rationale?: string;
}

export interface JDVersion {
  id: string;
  version_no: number;
  description: string;
  over_spec_flags: string[];
  created_at: string;
  created_by?: string;
}

/** A single role row (subset we touch in T604). */
export interface RoleRecord {
  id: string;
  title: string;
  description?: string;
  required_skills?: Array<Record<string, unknown>>;
  preferred_skills?: Array<Record<string, unknown>>;
  seniority?: string | null;
  industry?: string | null;
  salary_band?: Record<string, unknown> | null;
  location?: string | null;
  remote_policy?: string;
  status?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// HTTP plumbing
// ---------------------------------------------------------------------------

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function authHeaders(): Promise<HeadersInit> {
  try {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) return { Authorization: `Bearer ${token}` };
  } catch {
    /* fall through */
  }
  if (typeof window !== "undefined") {
    const legacy = window.localStorage.getItem("sb_token");
    if (legacy) return { Authorization: `Bearer ${legacy}` };
  }
  return {};
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((await authHeaders()) as Record<string, string>),
    ...((init.headers as Record<string, string>) ?? {}),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new Error(
      `JD API ${res.status} ${res.statusText}: ${JSON.stringify(body)}`,
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const out = sp.toString();
  return out ? `?${out}` : "";
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export const jdApi = {
  /** GET /api/jd-templates/list */
  templates(opts: { industry?: string; search?: string } = {}): Promise<{
    templates: JDTemplateSummary[];
    total: number;
    industries: string[];
  }> {
    return request(`/api/jd-templates/list${qs(opts)}`, {
      cache: "no-store",
    });
  },

  /** GET /api/jd-templates/{id} */
  template(id: string): Promise<{ template: JDTemplateFull }> {
    return request(`/api/jd-templates/${encodeURIComponent(id)}`, {
      cache: "no-store",
    });
  },

  /** GET /api/jd-templates/industries/all */
  industries(): Promise<{ industries: string[] }> {
    return request(`/api/jd-templates/industries/all`, { cache: "no-store" });
  },

  /** POST /api/job-spec/submit — also returns over_spec_flags inside `artifacts`. */
  submitSpec(body: {
    text: string;
    roleId?: string;
  }): Promise<{
    text: string;
    draft_jd?: string;
    artifacts?: {
      responsibilities?: string[];
      hard_requirements?: Array<{ category: string; value: string }>;
      nice_to_haves?: string[];
      team_culture?: Record<string, string>;
      draft_jd?: string;
      over_spec_flags?: string[];
      tech_stack?: string[];
      reporting_line?: string;
      travel_required?: string;
    };
  }> {
    return request("/api/job-spec/submit", {
      method: "POST",
      body: JSON.stringify({
        text: body.text,
        role_id: body.roleId || undefined,
      }),
    });
  },

  /** GET /api/roles/{role_id} */
  getRole(roleId: string): Promise<RoleRecord> {
    return request(`/api/roles/${encodeURIComponent(roleId)}`, {
      cache: "no-store",
    });
  },

  /** PATCH /api/roles/{role_id} */
  updateRole(roleId: string, patch: Record<string, unknown>): Promise<RoleRecord> {
    return request(`/api/roles/${encodeURIComponent(roleId)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  /** GET /api/roles/{role_id}/jd-versions — graceful fallback to []. */
  async versions(roleId: string): Promise<JDVersion[]> {
    try {
      const resp = await request<{ versions: JDVersion[] }>(
        `/api/roles/${encodeURIComponent(roleId)}/jd-versions`,
        { cache: "no-store" },
      );
      return resp.versions ?? [];
    } catch {
      return [];
    }
  },
};

// ---------------------------------------------------------------------------
// Helpers — over-spec heuristics used by `OverSpecWarning`
// ---------------------------------------------------------------------------

export type OverSpecSeverity = "red" | "amber" | "green";

const HARD_FLAG_KEYWORDS = [
  "歧视",
  "性别",
  "年龄",
  "婚育",
  "未婚",
  "形象",
  "颜值",
  "户口",
  "民族",
  "宗教",
  "院校",
  "985",
  "211",
];

const MEDIUM_FLAG_KEYWORDS = [
  "薪资",
  "薪酬",
  "经验",
  "要求过高",
  "难招",
  "不匹配",
  "稀缺",
  "建议拆分",
  "考虑分级",
  "难兼得",
];

/** Classify one flag string into red / amber / green. */
export function classifyOverSpec(flag: string): OverSpecSeverity {
  const t = flag.toLowerCase();
  if (HARD_FLAG_KEYWORDS.some((k) => t.includes(k.toLowerCase()))) return "red";
  if (MEDIUM_FLAG_KEYWORDS.some((k) => t.includes(k.toLowerCase()))) return "amber";
  return "amber"; // default to amber (warn) — safer to over-warn.
}

/** Aggregated severity for the whole batch. */
export function classifyBatch(flags: string[]): OverSpecSeverity {
  if (flags.length === 0) return "green";
  if (flags.some((f) => classifyOverSpec(f) === "red")) return "red";
  if (flags.some((f) => classifyOverSpec(f) === "amber")) return "amber";
  return "green";
}

export const TONE: Record<OverSpecSeverity, { wrap: string; bar: string; label: string; icon: string }> = {
  green: {
    wrap: "border-emerald-200 bg-emerald-50/50",
    bar: "bg-emerald-500",
    label: "需求合理",
    icon: "text-emerald-500",
  },
  amber: {
    wrap: "border-amber-200 bg-amber-50/50",
    bar: "bg-amber-500",
    label: "建议复核",
    icon: "text-amber-500",
  },
  red: {
    wrap: "border-rose-200 bg-rose-50/50",
    bar: "bg-rose-500",
    label: "请立即修改",
    icon: "text-rose-500",
  },
};

export type JDClient = typeof jdApi;
