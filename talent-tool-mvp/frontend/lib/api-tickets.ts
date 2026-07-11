/**
 * Tickets API client (T207).
 *
 * Wraps the FastAPI ticket endpoints exposed by `backend/api/tickets.py`:
 *   - POST   /api/tickets                  → create (employee or HR)
 *   - GET    /api/tickets                  → list (HR/admin)
 *   - GET    /api/tickets/me               → list mine (employee)
 *   - GET    /api/tickets/overdue          → SLA-breach list (HR)
 *   - GET    /api/tickets/{id}             → fetch one
 *   - PATCH  /api/tickets/{id}             → update metadata
 *   - PATCH  /api/tickets/{id}/status      → state-machine transition
 *   - POST   /api/tickets/{id}/comments    → add comment
 *   - GET    /api/tickets/{id}/timeline    → merged status + comment stream
 *
 * Shapes below mirror the dataclass returned by `services/ticket_service.py`
 * (`Ticket.to_dict()`) and the timeline elements produced by `get_timeline()`.
 */

import { createClient } from "@/lib/supabase";

// ---------------------------------------------------------------------------
// Constants — keep in lock-step with ticket_service.py
// ---------------------------------------------------------------------------

export const TICKET_STATUSES = [
  "open",
  "in_progress",
  "awaiting_user",
  "resolved",
  "closed",
] as const;
export type TicketStatus = (typeof TICKET_STATUSES)[number];

export const TICKET_PRIORITIES = ["low", "normal", "high", "urgent"] as const;
export type TicketPriority = (typeof TICKET_PRIORITIES)[number];

export const TICKET_CATEGORIES = [
  "hr",
  "onboarding",
  "offboarding",
  "policy",
  "payroll",
  "benefits",
  "training",
  "complaint",
  "it",
  "other",
] as const;
export type TicketCategory = (typeof TICKET_CATEGORIES)[number];

/** Allowed state-machine transitions — mirrors ALLOWED_TRANSITIONS in the
 * backend service. Used for greying out invalid status buttons in the UI. */
export const ALLOWED_TRANSITIONS: Record<TicketStatus, TicketStatus[]> = {
  open: ["in_progress", "resolved", "closed"],
  in_progress: ["awaiting_user", "resolved", "closed"],
  awaiting_user: ["in_progress", "resolved", "closed"],
  resolved: ["closed", "in_progress"],
  closed: [],
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Mirrors `Ticket.to_dict()` from services/ticket_service.py. */
export interface Ticket {
  id: string;
  user_id: string;
  organisation_id: string | null;
  title: string;
  description: string;
  status: TicketStatus;
  priority: TicketPriority;
  category: string;
  assignee_id: string | null;
  sla_due_at: string | null;
  first_responded_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  metadata: Record<string, unknown>;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface TicketCreatePayload {
  title: string;
  description?: string;
  priority?: TicketPriority;
  category?: TicketCategory;
  assignee_id?: string | null;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface TicketStatusUpdatePayload {
  status: TicketStatus;
  reason?: string;
  assignee_id?: string;
  metadata?: Record<string, unknown>;
}

export interface TicketMetaUpdatePayload {
  title?: string;
  description?: string;
  priority?: TicketPriority;
  category?: TicketCategory;
  assignee_id?: string;
  tags?: string[];
}

export interface TicketCommentCreatePayload {
  body: string;
  is_internal?: boolean;
  attachments?: unknown[];
}

export interface TicketComment {
  id: string;
  ticket_id: string;
  author_id: string;
  author_type: "employee" | "hr" | "system";
  body: string;
  is_internal: boolean;
  attachments: unknown[];
  created_at: string;
}

/** A merged event from `GET /api/tickets/{id}/timeline`. */
export type TimelineEvent =
  | {
      kind: "status";
      at: string;
      actor: string;
      payload: {
        from_status: TicketStatus | null;
        to_status: TicketStatus;
        reason: string | null;
        metadata: Record<string, unknown>;
      };
    }
  | {
      kind: "comment";
      at: string;
      actor: string;
      payload: {
        body: string;
        author_type: "employee" | "hr" | "system";
        is_internal: boolean;
      };
    };

export interface TimelineResponse {
  ticket_id: string;
  events: TimelineEvent[];
  count: number;
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
      `Tickets API ${res.status} ${res.statusText}: ${JSON.stringify(body)}`,
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

export const ticketsApi = {
  // ---- Employee / any user ----

  /** Employee creates their own ticket. */
  create(payload: TicketCreatePayload): Promise<{ ticket: Ticket; success: boolean }> {
    return request<{ ticket: Ticket; success: boolean }>("/api/tickets", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /** Employee lists their own tickets. */
  myTickets(opts: { status?: TicketStatus; limit?: number; offset?: number } = {}): Promise<{
    items: Ticket[];
    count: number;
    limit: number;
    offset: number;
  }> {
    return request<{ items: Ticket[]; count: number; limit: number; offset: number }>(
      `/api/tickets/me${qs(opts)}`,
      { cache: "no-store" },
    );
  },

  // ---- HR / admin ----

  /** HR / admin list all tickets (filters available). */
  list(
    opts: {
      status?: TicketStatus;
      priority?: TicketPriority;
      user_id?: string;
      assignee_id?: string;
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<{ items: Ticket[]; count: number; limit: number; offset: number }> {
    return request<{ items: Ticket[]; count: number; limit: number; offset: number }>(
      `/api/tickets${qs(opts)}`,
      { cache: "no-store" },
    );
  },

  /** SLA-breached tickets (HR dashboard). */
  overdue(opts: { limit?: number } = {}): Promise<{ items: Ticket[]; count: number }> {
    return request<{ items: Ticket[]; count: number }>(
      `/api/tickets/overdue${qs(opts)}`,
      { cache: "no-store" },
    );
  },

  // ---- Single ticket ----

  get(id: string): Promise<Ticket> {
    return request<Ticket>(`/api/tickets/${encodeURIComponent(id)}`, {
      cache: "no-store",
    });
  },

  updateMeta(id: string, payload: TicketMetaUpdatePayload): Promise<{ ticket: Ticket; success: boolean }> {
    return request<{ ticket: Ticket; success: boolean }>(
      `/api/tickets/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    );
  },

  transitionStatus(
    id: string,
    payload: TicketStatusUpdatePayload,
  ): Promise<{ ticket: Ticket; success: boolean }> {
    return request<{ ticket: Ticket; success: boolean }>(
      `/api/tickets/${encodeURIComponent(id)}/status`,
      { method: "PATCH", body: JSON.stringify(payload) },
    );
  },

  addComment(id: string, payload: TicketCommentCreatePayload): Promise<{
    comment: TicketComment;
    success: boolean;
  }> {
    return request<{ comment: TicketComment; success: boolean }>(
      `/api/tickets/${encodeURIComponent(id)}/comments`,
      { method: "POST", body: JSON.stringify(payload) },
    );
  },

  timeline(id: string): Promise<TimelineResponse> {
    return request<TimelineResponse>(
      `/api/tickets/${encodeURIComponent(id)}/timeline`,
      { cache: "no-store" },
    );
  },
};

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const STATUS_LABEL: Record<TicketStatus, string> = {
  open: "待处理",
  in_progress: "处理中",
  awaiting_user: "等待员工",
  resolved: "已解决",
  closed: "已关闭",
};

export const STATUS_COLOR: Record<TicketStatus, string> = {
  open: "bg-blue-500/10 text-blue-700 border-blue-200",
  in_progress: "bg-amber-500/10 text-amber-700 border-amber-200",
  awaiting_user: "bg-purple-500/10 text-purple-700 border-purple-200",
  resolved: "bg-emerald-500/10 text-emerald-700 border-emerald-200",
  closed: "bg-slate-500/10 text-slate-600 border-slate-200",
};

export const PRIORITY_LABEL: Record<TicketPriority, string> = {
  low: "低",
  normal: "普通",
  high: "高",
  urgent: "紧急",
};

export const PRIORITY_COLOR: Record<TicketPriority, string> = {
  low: "bg-slate-100 text-slate-600 border-slate-200",
  normal: "bg-blue-100 text-blue-700 border-blue-200",
  high: "bg-amber-100 text-amber-700 border-amber-200",
  urgent: "bg-rose-100 text-rose-700 border-rose-200",
};

export const CATEGORY_LABEL: Record<string, string> = {
  hr: "HR",
  onboarding: "入职",
  offboarding: "离职",
  policy: "制度",
  payroll: "薪资",
  benefits: "福利",
  training: "培训",
  complaint: "投诉",
  it: "IT",
  other: "其他",
};

export const AUTHOR_TYPE_LABEL: Record<"employee" | "hr" | "system", string> = {
  employee: "员工",
  hr: "HR",
  system: "系统",
};

/** Parse an ISO timestamp + return ms from now (negative for future). */
export function msUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return t - Date.now();
}

export type SlaState = "ok" | "soon" | "overdue" | "met" | "unknown";

/**
 * Bucket a ticket's SLA state for the badge:
 *   - overdue : past due, not resolved/closed
 *   - soon    : < 4h remaining
 *   - ok      : has remaining time
 *   - met     : resolved/closed (don't show countdown)
 *   - unknown : no SLA due date set
 */
export function slaState(ticket: Pick<Ticket, "status" | "sla_due_at">): SlaState {
  if (ticket.status === "resolved" || ticket.status === "closed") return "met";
  const ms = msUntil(ticket.sla_due_at);
  if (ms === null) return "unknown";
  if (ms < 0) return "overdue";
  if (ms < 4 * 60 * 60 * 1000) return "soon";
  return "ok";
}

/** Format a duration in milliseconds as a compact Chinese string. */
export function formatDuration(ms: number): string {
  const abs = Math.abs(ms);
  const sign = ms < 0 ? "已超 " : "";
  const minutes = Math.floor(abs / 60_000);
  if (minutes < 60) return `${sign}${minutes} 分`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${sign}${hours} 小时`;
  const days = Math.floor(hours / 24);
  return `${sign}${days} 天`;
}

export type TicketsClient = typeof ticketsApi;
