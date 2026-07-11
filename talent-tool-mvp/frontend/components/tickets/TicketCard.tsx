"use client";

/**
 * TicketCard (T207).
 *
 * Compact card used in the Kanban board and the "my tickets" list. Renders:
 *   - title + category icon
 *   - priority badge
 *   - SLA countdown / status badge (the headline element)
 *   - requester + assignee initials
 *   - tags + updated-at relative time
 *
 * Designed to be embedded as a clickable surface — the parent <button> /
 * <Link> wrapper decides the navigation target.
 */

import * as React from "react";
import {
  AlertTriangle,
  Clock,
  CheckCircle2,
  Tag,
  User as UserIcon,
} from "lucide-react";

import { cn, formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  type Ticket,
  type SlaState,
  PRIORITY_COLOR,
  PRIORITY_LABEL,
  STATUS_COLOR,
  STATUS_LABEL,
  CATEGORY_LABEL,
  slaState,
  msUntil,
  formatDuration,
} from "@/lib/api-tickets";

export interface TicketCardProps {
  ticket: Ticket;
  /** Compact mode strips the description, used in the Kanban column. */
  compact?: boolean;
  /** Hide the assignee column when it's not relevant (employee view). */
  showAssignee?: boolean;
  className?: string;
}

const CATEGORY_ICON: Record<string, string> = {
  hr: "👥",
  onboarding: "🚀",
  offboarding: "📤",
  policy: "📜",
  payroll: "💰",
  benefits: "🎁",
  training: "📚",
  complaint: "⚠️",
  it: "💻",
  other: "📌",
};

function SlaBadge({ ticket }: { ticket: Ticket }) {
  const state: SlaState = slaState(ticket);
  const ms = msUntil(ticket.sla_due_at);
  const text =
    state === "met"
      ? "已解决"
      : state === "overdue"
        ? ms !== null
          ? `逾期 ${formatDuration(ms)}`
          : "已逾期"
        : state === "soon"
          ? ms !== null
            ? `剩 ${formatDuration(ms)}`
            : "快到期"
          : state === "ok"
            ? ms !== null
              ? `剩 ${formatDuration(ms)}`
              : "SLA 正常"
            : "无 SLA";

  const Icon =
    state === "overdue"
      ? AlertTriangle
      : state === "soon"
        ? Clock
        : state === "met"
          ? CheckCircle2
          : Clock;

  const palette: Record<SlaState, string> = {
    overdue: "border-rose-300 bg-rose-50 text-rose-700",
    soon: "border-amber-300 bg-amber-50 text-amber-700",
    ok: "border-emerald-300 bg-emerald-50 text-emerald-700",
    met: "border-slate-300 bg-slate-50 text-slate-600",
    unknown: "border-slate-200 bg-slate-50 text-slate-500",
  };

  return (
    <Badge variant="outline" className={cn("gap-1 font-mono tabular-nums", palette[state])}>
      <Icon className="size-3" />
      {text}
    </Badge>
  );
}

function priorityBadge(p: Ticket["priority"]) {
  return (
    <Badge variant="outline" className={cn("border", PRIORITY_COLOR[p])}>
      {PRIORITY_LABEL[p]}
    </Badge>
  );
}

function statusBadge(s: Ticket["status"]) {
  return (
    <Badge variant="outline" className={cn("border", STATUS_COLOR[s])}>
      {STATUS_LABEL[s]}
    </Badge>
  );
}

export function TicketCard({
  ticket,
  compact = false,
  showAssignee = true,
  className,
}: TicketCardProps) {
  const categoryKey = ticket.category ?? "other";
  const icon = CATEGORY_ICON[categoryKey] ?? "📌";
  const categoryLabel = CATEGORY_LABEL[categoryKey] ?? categoryKey;

  return (
    <div
      data-slot="ticket-card"
      className={cn(
        "group relative rounded-lg border border-slate-200 bg-white p-3 shadow-xs transition",
        "hover:border-blue-300 hover:shadow-md focus-within:border-blue-400",
        className,
      )}
    >
      {/* Top row: priority + SLA + status */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {priorityBadge(ticket.priority)}
          <SlaBadge ticket={ticket} />
        </div>
        {statusBadge(ticket.status)}
      </div>

      {/* Title */}
      <h3 className="mt-2 line-clamp-2 text-sm font-medium leading-snug text-slate-900">
        {ticket.title}
      </h3>

      {/* Category + tags row */}
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1">
          <span aria-hidden>{icon}</span>
          <span>{categoryLabel}</span>
        </span>
        {ticket.tags?.slice(0, 2).map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-0.5 rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-500"
          >
            <Tag className="size-2.5" />
            {t}
          </span>
        ))}
      </div>

      {/* Description — only in expanded mode */}
      {!compact && ticket.description && (
        <p className="mt-2 line-clamp-2 text-xs text-slate-600">
          {ticket.description}
        </p>
      )}

      {/* Bottom row: assignee + timestamps */}
      <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500">
        {showAssignee ? (
          <span className="inline-flex items-center gap-1">
            <UserIcon className="size-3" />
            <span className="max-w-[120px] truncate">
              {ticket.assignee_id ? "已分配" : "未分配"}
            </span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1">
            <UserIcon className="size-3" />
            <span className="max-w-[140px] truncate">
              {ticket.user_id.slice(0, 8)}
            </span>
          </span>
        )}
        <time dateTime={ticket.updated_at}>{formatRelativeTime(ticket.updated_at)}</time>
      </div>
    </div>
  );
}

/** Re-export so other modules don't need a second import. */
export { SlaBadge, priorityBadge, statusBadge };
