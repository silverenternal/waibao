/**
 * Journal API client (T606).
 *
 * Wraps journal + action-item endpoints:
 *   - GET  /api/journal/timeline           → user diary history
 *   - GET  /api/journal/today              → today entry (if any)
 *   - POST /api/journal                    → submit new entry
 *   - GET  /api/action-items               → list user items
 *   - POST /api/action-items               → create new item
 *   - PATCH /api/action-items/{id}         → edit / state-machine move
 *   - POST /api/action-items/{id}/state    → state-machine shortcut
 *   - DELETE /api/action-items/{id}        → dismiss item
 *
 * Shapes mirror the row inserted by `agents/employer/daily_journal_agent.py`
 * and the action_items table created in supabase migration 008 (planned).
 */

import { createClient } from "@/lib/supabase";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type JournalRating = "excellent" | "good" | "warning" | string | null;

export interface JournalEntry {
  id: string;
  journal_date: string;
  content: string;
  mood_score: number | null;
  ai_rating: JournalRating;
  ai_advice: string | null;
  ai_warnings: string[];
  ai_action_items: string[];
  [key: string]: unknown;
}

export type ActionItemState = "open" | "in_progress" | "done" | "dismissed";

export interface ActionItem {
  id: string;
  user_id?: string;
  journal_id?: string | null;
  title: string;
  description?: string | null;
  state: ActionItemState;
  origin: "agent" | "user";
  due_date?: string | null;
  source_text?: string | null;
  created_at?: string;
  updated_at?: string;
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
      `Journal API ${res.status} ${res.statusText}: ${JSON.stringify(body)}`,
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
// Journal endpoints
// ---------------------------------------------------------------------------

export const journalApi = {
  /** GET /api/journal/timeline */
  timeline(opts: { days?: number } = {}): Promise<{
    data: JournalEntry[];
    total: number;
  }> {
    return request<{ data: JournalEntry[]; total: number }>(
      `/api/journal/timeline${qs(opts)}`,
      { cache: "no-store" },
    );
  },

  /** GET /api/journal/today */
  today(): Promise<JournalEntry | {}> {
    return request(`/api/journal/today`, { cache: "no-store" });
  },

  /** POST /api/journal */
  submit(body: {
    content: string;
    mood_score?: number | null;
  }): Promise<{
    text: string;
    artifacts: {
      rating?: JournalRating;
      advice?: string;
      warnings?: string[];
      action_items?: string[];
      mood_score?: number;
    };
    success?: boolean;
  }> {
    return request("/api/journal", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};

// ---------------------------------------------------------------------------
// Action item endpoints
// ---------------------------------------------------------------------------

export const actionItemsApi = {
  /** GET /api/action-items */
  list(opts: { state?: ActionItemState; limit?: number } = {}): Promise<{
    items: ActionItem[];
    fallback?: boolean;
  }> {
    return request<{ items: ActionItem[]; fallback?: boolean }>(
      `/api/action-items${qs(opts)}`,
      { cache: "no-store" },
    );
  },

  /** POST /api/action-items */
  create(body: {
    title: string;
    description?: string;
    due_date?: string;
    origin?: "agent" | "user";
    journal_id?: string;
    source_text?: string;
  }): Promise<{ item: ActionItem; created: boolean; fallback?: boolean }> {
    return request<{ item: ActionItem; created: boolean; fallback?: boolean }>(
      "/api/action-items",
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  /** PATCH /api/action-items/{id} */
  update(
    id: string,
    patch: {
      title?: string;
      description?: string;
      due_date?: string;
      state?: ActionItemState;
    },
  ): Promise<{ item: ActionItem; updated: boolean; fallback?: boolean }> {
    return request<{ item: ActionItem; updated: boolean; fallback?: boolean }>(
      `/api/action-items/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify(patch) },
    );
  },

  /** POST /api/action-items/{id}/state — shortcut to PATCH state. */
  setState(
    id: string,
    state: ActionItemState,
  ): Promise<{ item: ActionItem; updated: boolean; fallback?: boolean }> {
    return request<{ item: ActionItem; updated: boolean; fallback?: boolean }>(
      `/api/action-items/${encodeURIComponent(id)}/state`,
      { method: "POST", body: JSON.stringify({ state }) },
    );
  },

  /** DELETE /api/action-items/{id} — soft delete via `dismissed`. */
  dismiss(id: string): Promise<{ deleted: boolean; fallback?: boolean }> {
    return request<{ deleted: boolean; fallback?: boolean }>(
      `/api/action-items/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    );
  },
};

export type JournalClient = typeof journalApi;
export type ActionItemsClient = typeof actionItemsApi;
