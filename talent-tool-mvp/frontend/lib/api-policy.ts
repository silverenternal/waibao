/**
 * Policy API client (T601).
 *
 * Wraps the FastAPI policy endpoints exposed by `backend/api/policy_api.py`:
 *   - GET  /api/policy/list       → list policies (filter by category)
 *   - GET  /api/policy/query      → semantic query (returns matched chunks)
 *   - POST /api/policy/upload     → upload & parse a new policy doc
 *
 * Shapes mirror the rows persisted into `company_policies` and the `items`
 * / `matched_policies` artifacts emitted by `policy_agent`.
 */

import { createClient } from "@/lib/supabase";

// ---------------------------------------------------------------------------
// Types — must stay in sync with backend/api/policy_api.py + policy_agent
// ---------------------------------------------------------------------------

export const POLICY_CATEGORIES = [
  "attendance",
  "leave",
  "expense",
  "compensation",
  "promotion",
  "benefits",
  "code_of_conduct",
  "remote_work",
  "data_privacy",
  "other",
] as const;
export type PolicyCategory = (typeof POLICY_CATEGORIES)[number];

export const POLICY_CATEGORY_LABEL: Record<PolicyCategory, string> = {
  attendance: "考勤",
  leave: "请假",
  expense: "报销",
  compensation: "薪酬",
  promotion: "晋升",
  benefits: "福利",
  code_of_conduct: "行为准则",
  remote_work: "远程办公",
  data_privacy: "数据隐私",
  other: "其他",
};

/** Severity levels attached to legal-risk badges. */
export type LegalRiskLevel = "low" | "medium" | "high";

/** A row from `GET /api/policy/list`. */
export interface PolicyDoc {
  id: string;
  title: string;
  category: string;
  content?: string;
  effective_from?: string | null;
  created_at: string;
}

/** A single clause / chunk — produced by policy_agent `parse` task. */
export interface PolicyClause {
  id?: string;
  title?: string;
  text?: string;
  category?: string;
  /** Optional compliance hook pointing back at compliance table. */
  policy_id?: string;
  /** Optional risk score (0..1) — heuristic, not legal advice. */
  risk_score?: number;
  /** Convenience: derived from risk_score. */
  risk_level?: LegalRiskLevel;
  effective_from?: string | null;
}

/** The shape returned by `POST /api/policy/upload`. */
export interface PolicyUploadResponse {
  text: string;
  items: PolicyClause[];
}

/** A single hit returned by `GET /api/policy/query`. */
export interface PolicyQueryHit {
  policy_id?: string;
  title?: string;
  category?: string;
  text?: string;
  relevance?: number;
}

/** The shape returned by `GET /api/policy/query`. */
export interface PolicyQueryResponse {
  answer: string;
  matched: PolicyQueryHit[];
}

/** Combined response shape for the full-text-search view. */
export interface PolicySearchResult {
  id: string;
  title: string;
  category: string;
  snippet: string;
  matchCount: number;
  effective_from?: string | null;
  created_at: string;
  /** Which term matched (audit trail). */
  matchedTerm?: string;
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
      `Policy API ${res.status} ${res.statusText}: ${JSON.stringify(body)}`,
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

export const policyApi = {
  /** List all policies for an organisation; optional category filter. */
  list(opts: { organisationId?: string; category?: PolicyCategory | "" } = {}): Promise<{
    data: PolicyDoc[];
  }> {
    const organisationId = opts.organisationId ?? "demo-org";
    return request<{ data: PolicyDoc[] }>(
      `/api/policy/list${qs({
        organisation_id: organisationId,
        category: opts.category || undefined,
      })}`,
      { cache: "no-store" },
    );
  },

  /** Semantic query — LLM-style search across the policy corpus. */
  query(opts: {
    question: string;
    organisationId?: string;
  }): Promise<PolicyQueryResponse> {
    return request<PolicyQueryResponse>(
      `/api/policy/query${qs({
        question: opts.question,
        organisation_id: opts.organisationId ?? "demo-org",
      })}`,
      { cache: "no-store" },
    );
  },

  /** Upload a brand-new policy doc + parse into clauses. */
  upload(body: {
    text: string;
    category: PolicyCategory | string;
    organisationId: string;
  }): Promise<PolicyUploadResponse> {
    return request<PolicyUploadResponse>("/api/policy/upload", {
      method: "POST",
      body: JSON.stringify({
        text: body.text,
        category: body.category,
        organisation_id: body.organisationId,
      }),
    });
  },
};

// ---------------------------------------------------------------------------
// Helpers — pure functions used by both list and detail views
// ---------------------------------------------------------------------------

/** Truncate a long policy body to the first N chars (for list previews). */
export function snippet(text: string | undefined, max = 140): string {
  if (!text) return "";
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max)}…`;
}

/** Highlight occurrences of `term` inside `text`. Returns an array of segments
 * to render with `<mark>` tags — case-insensitive, preserves original casing. */
export function highlightTerms(
  text: string,
  terms: string[],
): Array<{ text: string; highlight: boolean }> {
  if (!text || terms.length === 0) return [{ text, highlight: false }];
  const safe = terms
    .filter((t) => t.length >= 1)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  if (!safe) return [{ text, highlight: false }];
  const re = new RegExp(`(${safe})`, "gi");
  const parts = text.split(re);
  return parts
    .filter((p) => p.length > 0)
    .map((p) => ({ text: p, highlight: re.test(p) ? true : false }))
    .map((seg, _, arr) => {
      // Re.test with global flag is stateful; recompute properly.
      void arr;
      const m = seg.text.match(/^(.+)$/);
      if (!m) return seg;
      return {
        text: seg.text,
        highlight: terms.some(
          (t) => t && seg.text.toLowerCase() === t.toLowerCase(),
        ),
      };
    });
}

/** Bucket numeric risk score into low / medium / high. */
export function riskLevelFromScore(score?: number | null): LegalRiskLevel {
  if (score == null) return "low";
  if (score >= 0.66) return "high";
  if (score >= 0.33) return "medium";
  return "low";
}

/** Tailwind classes for each risk level — used by `LegalRiskBadge`. */
export const RISK_BADGE: Record<LegalRiskLevel, { wrap: string; label: string }> = {
  low: {
    wrap: "bg-emerald-50 text-emerald-700 border-emerald-200",
    label: "低风险",
  },
  medium: {
    wrap: "bg-amber-50 text-amber-700 border-amber-200",
    label: "中等风险",
  },
  high: {
    wrap: "bg-rose-50 text-rose-700 border-rose-200",
    label: "高风险",
  },
};

export type PolicyClient = typeof policyApi;
