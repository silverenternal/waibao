/**
 * Strategy / Vision API client (T205).
 *
 * Wraps the FastAPI vision endpoints exposed by `backend/api/vision.py`:
 *   - POST /api/vision/submit              → run vision_agent + persist 4-layer
 *   - GET  /api/vision/strategy-map        → fetch grouped active strategy
 *   - GET  /api/vision/history             → (client-side helper) every
 *                                            company_strategy row, optionally
 *                                            filtered by status — the backend
 *                                            doesn't expose this yet, so the UI
 *                                            layers it over strategy-map.
 *
 * Shapes below mirror the dataclasses returned by
 * `backend/agents/employer/vision_agent.py` and the rows in
 * `company_strategy` (supabase/migrations/005_company_knowledge.sql).
 */

import { createClient } from "@/lib/supabase";

// ---------------------------------------------------------------------------
// Constants — keep in lock-step with the schema CHECK constraints.
// ---------------------------------------------------------------------------

export const STRATEGY_LEVELS = [
  "vision",
  "planning",
  "strategy",
  "tactic",
] as const;
export type StrategyLevel = (typeof STRATEGY_LEVELS)[number];

export const STRATEGY_STATUSES = ["draft", "active", "archived"] as const;
export type StrategyStatus = (typeof STRATEGY_STATUSES)[number];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A row from the `company_strategy` table. */
export interface StrategyItem {
  id: string;
  organisation_id: string;
  level: StrategyLevel;
  horizon: string | null;
  title: string;
  description: string;
  owner_role: string;
  owner_user_id: string | null;
  parent_id: string | null;
  status: StrategyStatus;
  created_at: string;
  updated_at: string;
}

/** Decoded section from `vision_agent` — what the LLM produces. */
export interface DecodedSection {
  statement?: string;
  horizon?: string;
}

export interface DecodedTactic {
  title?: string;
  horizon?: string;
  owner?: string;
}

export interface VisionArtifacts {
  vision?: DecodedSection;
  planning?: DecodedSection;
  strategy?: DecodedSection;
  tactic?: DecodedTactic[];
  gaps?: string[];
  follow_up_questions?: string[];
}

/** Response of POST /api/vision/submit. */
export interface VisionSubmitResponse {
  text: string;
  artifacts: VisionArtifacts;
}

/** Response of GET /api/vision/strategy-map. */
export interface StrategyMapResponse {
  strategy_map: Record<StrategyLevel, StrategyItem[]>;
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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
      `Strategy API ${res.status} ${res.statusText}: ${JSON.stringify(body)}`,
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

export const strategyApi = {
  /**
   * Submit freeform vision/planning/strategy/tactic text and run the
   * vision_agent. Returns the agent's plain-text reply plus the structured
   * 4-layer artifacts (and identified gaps / follow-up questions).
   */
  submit(text: string): Promise<VisionSubmitResponse> {
    return request<VisionSubmitResponse>("/api/vision/submit", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },

  /**
   * Fetch the org's current active strategy grouped by level. The backend
   * returns `[]` arrays for levels with no active rows.
   */
  strategyMap(organisationId: string): Promise<StrategyMapResponse> {
    return request<StrategyMapResponse>(
      `/api/vision/strategy-map${qs({ organisation_id: organisationId })}`,
      { cache: "no-store" },
    );
  },
};

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const LEVEL_LABEL: Record<StrategyLevel, string> = {
  vision: "愿景",
  planning: "规划",
  strategy: "战略",
  tactic: "战术",
};

export const LEVEL_DESCRIPTION: Record<StrategyLevel, string> = {
  vision: "3-5 年想成为什么",
  planning: "未来 1 年的规划",
  strategy: "本年度的战略重点",
  tactic: "本季度的可执行动作",
};

/** Icon hint for each level — lucide icons are referenced by name so the
 * component decides what to render (keeps this file framework-agnostic). */
export const LEVEL_ICON: Record<StrategyLevel, string> = {
  vision: "Telescope",
  planning: "CalendarRange",
  strategy: "Compass",
  tactic: "Zap",
};

export const STATUS_LABEL: Record<StrategyStatus, string> = {
  draft: "草稿",
  active: "生效中",
  archived: "已归档",
};

export const STATUS_COLOR: Record<StrategyStatus, string> = {
  draft: "bg-slate-100 text-slate-600 border-slate-200",
  active: "bg-emerald-100 text-emerald-700 border-emerald-200",
  archived: "bg-amber-100 text-amber-700 border-amber-200",
};

/** Horizontal order in which the levels should be displayed (top to bottom). */
export const LEVEL_ORDER: StrategyLevel[] = [
  "vision",
  "planning",
  "strategy",
  "tactic",
];

/** Compute per-level "presence" — true if the level has ≥ 1 active item. */
export function levelHasContent(
  map: StrategyMapResponse["strategy_map"] | null | undefined,
  level: StrategyLevel,
): boolean {
  if (!map) return false;
  const items = map[level];
  return Array.isArray(items) && items.length > 0;
}

/** Flatten the grouped map into a sorted-by-time list (newest first). */
export function flattenStrategyMap(
  map: StrategyMapResponse["strategy_map"] | null | undefined,
): StrategyItem[] {
  if (!map) return [];
  const all: StrategyItem[] = [];
  for (const lvl of LEVEL_ORDER) {
    const items = map[lvl];
    if (Array.isArray(items)) all.push(...items);
  }
  all.sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  return all;
}

/** Build a "follow-up question" list, preferring agent output then gaps. */
export function followUpQuestions(art: VisionArtifacts | null | undefined): string[] {
  if (!art) return [];
  const qs = Array.isArray(art.follow_up_questions) ? art.follow_up_questions : [];
  const gaps = Array.isArray(art.gaps) ? art.gaps : [];
  return [...qs, ...gaps].filter(Boolean);
}

/** Group timeline items by calendar date (yyyy-mm-dd) for the timeline view. */
export function groupByDate(
  items: StrategyItem[],
): Array<{ date: string; items: StrategyItem[] }> {
  const map = new Map<string, StrategyItem[]>();
  for (const item of items) {
    const d = new Date(item.created_at);
    const key = isNaN(d.getTime()) ? "未知" : d.toISOString().slice(0, 10);
    const arr = map.get(key) ?? [];
    arr.push(item);
    map.set(key, arr);
  }
  return Array.from(map.entries())
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([date, items]) => ({ date, items }));
}

/** Build a textual diff between two flat lists of strategy items. */
export interface StrategyDiff {
  added: StrategyItem[];
  removed: StrategyItem[];
  changed: Array<{ before: StrategyItem; after: StrategyItem }>;
}

export function diffStrategyLists(
  before: StrategyItem[],
  after: StrategyItem[],
): StrategyDiff {
  const beforeByKey = new Map<string, StrategyItem>();
  const afterByKey = new Map<string, StrategyItem>();

  const keyOf = (it: StrategyItem) =>
    `${it.level}::${it.title.trim().toLowerCase()}`;

  for (const it of before) beforeByKey.set(keyOf(it), it);
  for (const it of after) afterByKey.set(keyOf(it), it);

  const added: StrategyItem[] = [];
  const removed: StrategyItem[] = [];
  const changed: Array<{ before: StrategyItem; after: StrategyItem }> = [];

  for (const [k, b] of beforeByKey) {
    const a = afterByKey.get(k);
    if (!a) removed.push(b);
    else if (
      a.description !== b.description ||
      a.horizon !== b.horizon ||
      a.status !== b.status
    )
      changed.push({ before: b, after: a });
  }
  for (const [k, a] of afterByKey) {
    if (!beforeByKey.has(k)) added.push(a);
  }

  return { added, removed, changed };
}

export type StrategyClient = typeof strategyApi;