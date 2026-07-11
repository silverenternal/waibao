"use client";

/**
 * TicketTimeline (T207).
 *
 * Renders the merged status-history + comment stream returned by
 * `GET /api/tickets/{id}/timeline`. Kinds:
 *
 *   - status   → state-machine transition (icon: arrow-right between two dots)
 *   - comment  → free-form message authored by employee / hr / system
 *
 * The component is purely presentational — the page wires it to data via
 * props. It also renders an inline comment composer at the bottom so the
 * detail page can drop it in directly.
 *
 *   ┌─ Vertical timeline (icon rail + content card) ──────────────┐
 *   │  status   ▎  open → in_progress                              │
 *   │           ▎  by Sarah Chen · 12m ago · "由 HR 接管"            │
 *   │  comment  ▎  (employee) 需求已收到,流程确认中...              │
 *   │  comment  ▎  (hr)        已和财务核实,下周到账。              │
 *   │  status   ▎  in_progress → resolved                          │
 *   └──────────────────────────────────────────────────────────────┘
 */

import * as React from "react";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  CornerDownRight,
  Loader2,
  Lock,
  Send,
  User as UserIcon,
  Users,
} from "lucide-react";

import { cn, formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  type TimelineEvent,
  type TicketStatus,
  type Ticket,
  AUTHOR_TYPE_LABEL,
  STATUS_LABEL,
  STATUS_COLOR,
  slaState,
} from "@/lib/api-tickets";

// ---------------------------------------------------------------------------
// Visual primitives
// ---------------------------------------------------------------------------

const AUTHOR_ICON: Record<"employee" | "hr" | "system", React.ComponentType<{ className?: string }>> = {
  employee: UserIcon,
  hr: Users,
  system: Bot,
};

const AUTHOR_COLOR: Record<"employee" | "hr" | "system", string> = {
  employee: "bg-blue-100 text-blue-700 ring-blue-200",
  hr: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  system: "bg-violet-100 text-violet-700 ring-violet-200",
};

function StatusIcon({ status, className }: { status: TicketStatus; className?: string }) {
  switch (status) {
    case "open":
      return <ArrowRight className={cn("size-3", className)} />;
    case "in_progress":
      return <Loader2 className={cn("size-3", className)} />;
    case "awaiting_user":
      return <CornerDownRight className={cn("size-3", className)} />;
    case "resolved":
      return <CheckCircle2 className={cn("size-3", className)} />;
    case "closed":
      return <Lock className={cn("size-3", className)} />;
  }
}

function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <Badge variant="outline" className={cn("gap-1 border", STATUS_COLOR[status])}>
      <StatusIcon status={status} />
      {STATUS_LABEL[status]}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface TicketTimelineProps {
  events: TimelineEvent[];
  ticket: Ticket;
  /** Submit a new comment; pass undefined to hide the composer. */
  onSubmitComment?: (body: string, isInternal: boolean) => Promise<void> | void;
  /** Show internal-note toggle in the composer (HR-only). */
  allowInternal?: boolean;
  className?: string;
}

export function TicketTimeline({
  events,
  ticket,
  onSubmitComment,
  allowInternal = false,
  className,
}: TicketTimelineProps) {
  const sorted = React.useMemo(
    () =>
      [...events].sort((a, b) =>
        (a.at || "").localeCompare(b.at || ""),
      ),
    [events],
  );

  const state = slaState(ticket);

  return (
    <section
      data-slot="ticket-timeline"
      className={cn("flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xs", className)}
    >
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            处理时间线
          </h2>
          <p className="text-xs text-slate-500">
            状态变更 · 评论 · 智能体回复
          </p>
        </div>
        <SlaInlineStatus state={state} slaDueAt={ticket.sla_due_at} />
      </header>

      {/* Timeline rail */}
      <ol className="relative ml-2 space-y-4 border-l border-slate-200 pl-5">
        {sorted.length === 0 && (
          <li className="text-sm text-slate-400">暂无事件 — 等待创建。</li>
        )}
        {sorted.map((ev, i) => (
          <TimelineRow key={`${ev.kind}-${ev.at}-${i}`} event={ev} />
        ))}
      </ol>

      {/* Composer */}
      {onSubmitComment && (
        <CommentComposer onSubmit={onSubmitComment} allowInternal={allowInternal} />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Individual row
// ---------------------------------------------------------------------------

function TimelineRow({ event }: { event: TimelineEvent }) {
  if (event.kind === "status") {
    return <StatusRow event={event} />;
  }
  return <CommentRow event={event} />;
}

function StatusRow({
  event,
}: {
  event: Extract<TimelineEvent, { kind: "status" }>;
}) {
  const { from_status, to_status, reason } = event.payload;
  const authorType = "system" as const; // status changes bubble through the system
  const Icon = AUTHOR_ICON[authorType];
  return (
    <li className="relative">
      <span
        className={cn(
          "absolute -left-[27px] flex size-7 items-center justify-center rounded-full ring-4 ring-white",
          AUTHOR_COLOR[authorType],
        )}
      >
        <Icon className="size-3.5" />
      </span>
      <div className="rounded-md border border-slate-100 bg-slate-50/60 p-3">
        <div className="flex flex-wrap items-center gap-2">
          {from_status ? <StatusBadge status={from_status} /> : <span className="text-xs text-slate-400">(初始)</span>}
          <ArrowRight className="size-3.5 text-slate-400" />
          <StatusBadge status={to_status} />
          <span className="ml-auto text-[11px] text-slate-500">
            {event.at ? formatRelativeTime(event.at) : ""}
          </span>
        </div>
        {reason && (
          <p className="mt-2 text-xs text-slate-600">
            <span className="font-medium text-slate-700">原因:</span> {reason}
          </p>
        )}
      </div>
    </li>
  );
}

function CommentRow({
  event,
}: {
  event: Extract<TimelineEvent, { kind: "comment" }>;
}) {
  const { body, author_type, is_internal } = event.payload;
  const Icon = AUTHOR_ICON[author_type];
  return (
    <li className="relative">
      <span
        className={cn(
          "absolute -left-[27px] flex size-7 items-center justify-center rounded-full ring-4 ring-white",
          AUTHOR_COLOR[author_type],
        )}
      >
        <Icon className="size-3.5" />
      </span>

      <div
        className={cn(
          "rounded-md border p-3",
          is_internal
            ? "border-amber-200 bg-amber-50/60"
            : "border-slate-200 bg-white",
        )}
      >
        <div className="mb-1 flex items-center gap-2 text-xs">
          <span className="font-medium text-slate-700">
            {AUTHOR_TYPE_LABEL[author_type]}
          </span>
          {is_internal && (
            <Badge variant="outline" className="border-amber-300 bg-amber-100 text-amber-700">
              <Lock className="size-2.5" />
              内部备注
            </Badge>
          )}
          <span className="ml-auto text-[11px] text-slate-500">
            {event.at ? formatRelativeTime(event.at) : ""}
          </span>
        </div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
          {body}
        </p>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Comment composer — controlled, async-friendly, optional internal toggle.
// ---------------------------------------------------------------------------

export interface CommentComposerProps {
  onSubmit: (body: string, isInternal: boolean) => Promise<void> | void;
  allowInternal?: boolean;
  placeholder?: string;
}

export function CommentComposer({
  onSubmit,
  allowInternal = false,
  placeholder = "回复员工或留下内部备注...",
}: CommentComposerProps) {
  const [body, setBody] = React.useState("");
  const [isInternal, setIsInternal] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);

  const trimmed = body.trim();
  const canSubmit = trimmed.length > 0 && !submitting;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await onSubmit(trimmed, isInternal);
      setBody("");
      setIsInternal(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-3">
      <Textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={placeholder}
        rows={3}
        className="resize-y bg-white"
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            handleSubmit();
          }
        }}
      />
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs text-slate-500">
          {allowInternal && (
            <label className="inline-flex cursor-pointer items-center gap-1.5">
              <input
                type="checkbox"
                className="size-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                checked={isInternal}
                onChange={(e) => setIsInternal(e.target.checked)}
              />
              <Lock className="size-3 text-amber-600" />
              内部备注 (仅 HR 可见)
            </label>
          )}
          <span className="hidden text-[11px] text-slate-400 sm:inline">
            ⌘/Ctrl + Enter 快速发送
          </span>
        </div>
        <Button
          type="button"
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="gap-1.5"
        >
          {submitting ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Send className="size-3.5" />
          )}
          发送
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tiny sub-component — current SLA inline badge for the timeline header.
// ---------------------------------------------------------------------------

function SlaInlineStatus({
  state,
  slaDueAt,
}: {
  state: ReturnType<typeof slaState>;
  slaDueAt: string | null;
}) {
  if (state === "met") {
    return (
      <Badge variant="outline" className="gap-1 border-emerald-300 bg-emerald-50 text-emerald-700">
        <CheckCircle2 className="size-3" /> 已解决
      </Badge>
    );
  }
  if (state === "unknown" || !slaDueAt) {
    return (
      <Badge variant="outline" className="gap-1 border-slate-200 bg-slate-50 text-slate-500">
        无 SLA
      </Badge>
    );
  }
  const ms = new Date(slaDueAt).getTime() - Date.now();
  const text =
    state === "overdue"
      ? `已逾期 ${formatRelativeTime(slaDueAt)}`
      : `剩 ${formatRelativeTime(slaDueAt)}`;
  const palette: Record<string, string> = {
    overdue: "border-rose-300 bg-rose-50 text-rose-700",
    soon: "border-amber-300 bg-amber-50 text-amber-700",
    ok: "border-emerald-300 bg-emerald-50 text-emerald-700",
    met: "border-emerald-300 bg-emerald-50 text-emerald-700",
    unknown: "border-slate-200 bg-slate-50 text-slate-500",
  };
  return (
    <Badge variant="outline" className={cn("gap-1 tabular-nums", palette[state])}>
      <Clock className="size-3" />
      {text}
    </Badge>
  );
}
