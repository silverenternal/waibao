"use client";

/**
 * HR ticket detail — /tickets/[id] (T207).
 *
 * Layout:
 *   ┌─ Sticky header (title + back + status pill + SLA badge) ───┐
 *   ├─ Left col  — meta (requester · priority · tags · created) ─┤
 *   │              status transition widget (HR controls)        │
 *   ├─ Right col — description + TicketTimeline + composer       │
 *   └───────────────────────────────────────────────────────────┘
 *
 * Status updates go through `ticketsApi.transitionStatus`, comments via
 * `ticketsApi.addComment`. Each mutation does an inline refetch so the
 * UI is always consistent with the backend.
 */

import * as React from "react";
import { useRouter, useParams } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  Calendar,
  Clock,
  Hash,
  Loader2,
  Tag as TagIcon,
  Ticket as TicketIcon,
  User as UserIcon,
} from "lucide-react";

import { cn, formatDate, formatRelativeTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";

import { TicketTimeline } from "@/components/tickets/TicketTimeline";
import {
  ticketsApi,
  type Ticket,
  type TicketStatus,
  type TimelineEvent,
  ALLOWED_TRANSITIONS,
  PRIORITY_LABEL,
  PRIORITY_COLOR,
  STATUS_LABEL,
  STATUS_COLOR,
  CATEGORY_LABEL,
  slaState,
} from "@/lib/api-tickets";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; ticket: Ticket; events: TimelineEvent[] }
  | { kind: "error"; message: string };

export default function HrTicketDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const ticketId = params?.id;

  const [state, setState] = React.useState<LoadState>({ kind: "loading" });
  const [transitioning, setTransitioning] = React.useState<TicketStatus | null>(null);
  const [transitionError, setTransitionError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    if (!ticketId) return;
    setState({ kind: "loading" });
    try {
      const [ticket, timeline] = await Promise.all([
        ticketsApi.get(ticketId),
        ticketsApi.timeline(ticketId),
      ]);
      setState({ kind: "ready", ticket, events: timeline.events });
    } catch (e: unknown) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : "加载失败",
      });
    }
  }, [ticketId]);

  React.useEffect(() => {
    load();
  }, [load]);

  async function handleTransition(next: TicketStatus) {
    if (state.kind !== "ready") return;
    setTransitioning(next);
    setTransitionError(null);
    try {
      await ticketsApi.transitionStatus(state.ticket.id, { status: next });
      await load();
    } catch (e: unknown) {
      setTransitionError(e instanceof Error ? e.message : "状态更新失败");
    } finally {
      setTransitioning(null);
    }
  }

  async function handleAddComment(body: string, isInternal: boolean) {
    if (state.kind !== "ready") return;
    await ticketsApi.addComment(state.ticket.id, {
      body,
      is_internal: isInternal,
    });
    await load();
  }

  if (state.kind === "loading") {
    return (
      <Centered>
        <Loader2 className="size-5 animate-spin text-blue-500" />
        <span className="ml-2 text-sm text-slate-600">加载工单中...</span>
      </Centered>
    );
  }

  if (state.kind === "error") {
    return (
      <Centered>
        <AlertCircle className="size-5 text-rose-500" />
        <span className="ml-2 text-sm text-rose-700">{state.message}</span>
        <Button variant="outline" size="sm" className="ml-3" onClick={load}>
          重试
        </Button>
      </Centered>
    );
  }

  const { ticket, events } = state;
  const allowedNext = ALLOWED_TRANSITIONS[ticket.status] ?? [];
  const categoryKey = ticket.category ?? "other";
  const sla = slaState(ticket);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => router.push("/tickets")}
              aria-label="返回工单看板"
            >
              <ArrowLeft className="size-4" />
            </Button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <TicketIcon className="size-4 shrink-0 text-blue-500" />
                <h1 className="truncate text-base font-semibold text-foreground">
                  {ticket.title}
                </h1>
                <Badge variant="outline" className={cn("border", STATUS_COLOR[ticket.status])}>
                  {STATUS_LABEL[ticket.status]}
                </Badge>
                <Badge variant="outline" className={cn("border", PRIORITY_COLOR[ticket.priority])}>
                  优先级 {PRIORITY_LABEL[ticket.priority]}
                </Badge>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                工单 #{ticket.id.slice(0, 8)} · 创建于 {formatDate(ticket.created_at)}
              </p>
            </div>
          </div>

          <SlaInlineBadge state={sla} slaDueAt={ticket.sla_due_at} />
        </div>
      </header>

      {/* Body */}
      <main className="mx-auto grid max-w-7xl gap-6 px-6 py-6 lg:grid-cols-3">
        {/* Left: meta + status */}
        <aside className="space-y-6 lg:col-span-1">
          <Card>
            <CardContent className="space-y-3 p-4">
              <h2 className="text-sm font-semibold text-slate-800">工单元数据</h2>
              <MetaRow icon={<UserIcon className="size-4" />} label="提交人">
                <span className="font-mono text-xs">{ticket.user_id.slice(0, 8)}</span>
              </MetaRow>
              <MetaRow icon={<Hash className="size-4" />} label="类别">
                {CATEGORY_LABEL[categoryKey] ?? categoryKey}
              </MetaRow>
              <MetaRow icon={<Calendar className="size-4" />} label="SLA 截止">
                {ticket.sla_due_at
                  ? `${formatDate(ticket.sla_due_at)} (${formatRelativeTime(ticket.sla_due_at)})`
                  : "未设置"}
              </MetaRow>
              {ticket.assignee_id && (
                <MetaRow icon={<UserIcon className="size-4" />} label="分配给">
                  <span className="font-mono text-xs">{ticket.assignee_id.slice(0, 8)}</span>
                </MetaRow>
              )}
              {ticket.tags?.length > 0 && (
                <MetaRow icon={<TagIcon className="size-4" />} label="标签">
                  <div className="flex flex-wrap gap-1">
                    {ticket.tags.map((t) => (
                      <Badge key={t} variant="outline" className="border-slate-200 bg-slate-50 text-[10px]">
                        {t}
                      </Badge>
                    ))}
                  </div>
                </MetaRow>
              )}
              <MetaRow icon={<Clock className="size-4" />} label="最近更新">
                {formatRelativeTime(ticket.updated_at)}
              </MetaRow>
            </CardContent>
          </Card>

          {/* Status widget — HR can move across the state machine. */}
          <Card>
            <CardContent className="space-y-3 p-4">
              <h2 className="text-sm font-semibold text-slate-800">推进状态</h2>

              {allowedNext.length === 0 ? (
                <p className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
                  当前状态 ({STATUS_LABEL[ticket.status]}) 为终态,无法继续流转。
                </p>
              ) : (
                <>
                  <p className="text-xs text-slate-500">
                    可流转到:{allowedNext.map((s) => STATUS_LABEL[s]).join(" / ")}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {allowedNext.map((next) => (
                      <Button
                        key={next}
                        variant="outline"
                        size="sm"
                        disabled={transitioning !== null}
                        onClick={() => handleTransition(next)}
                        className={cn("border", STATUS_COLOR[next])}
                      >
                        {transitioning === next && (
                          <Loader2 className="mr-1 size-3 animate-spin" />
                        )}
                        → {STATUS_LABEL[next]}
                      </Button>
                    ))}
                  </div>
                </>
              )}

              {transitionError && (
                <p className="rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-700">
                  {transitionError}
                </p>
              )}
            </CardContent>
          </Card>
        </aside>

        {/* Right: description + timeline */}
        <section className="space-y-6 lg:col-span-2">
          {ticket.description && (
            <Card>
              <CardContent className="p-4">
                <h2 className="mb-2 text-sm font-semibold text-slate-800">描述</h2>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                  {ticket.description}
                </p>
              </CardContent>
            </Card>
          )}

          <TicketTimeline
            ticket={ticket}
            events={events}
            onSubmitComment={handleAddComment}
            allowInternal
          />
        </section>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetaRow({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <span className="mt-0.5 text-slate-400">{icon}</span>
      <div className="flex-1">
        <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
        <div className="text-slate-800">{children}</div>
      </div>
    </div>
  );
}

function SlaInlineBadge({
  state,
  slaDueAt,
}: {
  state: ReturnType<typeof slaState>;
  slaDueAt: string | null;
}) {
  const palette: Record<typeof state, string> = {
    overdue: "border-rose-300 bg-rose-50 text-rose-700",
    soon: "border-amber-300 bg-amber-50 text-amber-700",
    ok: "border-emerald-300 bg-emerald-50 text-emerald-700",
    met: "border-slate-300 bg-slate-50 text-slate-600",
    unknown: "border-slate-200 bg-slate-50 text-slate-500",
  };
  const label =
    state === "met"
      ? "已解决"
      : state === "overdue"
        ? `已逾期 ${slaDueAt ? formatRelativeTime(slaDueAt) : ""}`
        : state === "soon"
          ? `剩 ${slaDueAt ? formatRelativeTime(slaDueAt) : ""}`
          : state === "ok"
            ? `剩 ${slaDueAt ? formatRelativeTime(slaDueAt) : ""}`
            : "无 SLA";
  return (
    <Badge variant="outline" className={cn("gap-1 tabular-nums", palette[state])}>
      <Clock className="size-3" />
      {label}
    </Badge>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50">
      <Card>
        <CardContent className="flex items-center gap-2 py-12 px-12">{children}</CardContent>
      </Card>
    </div>
  );
}

// Re-export so the page can be referenced from layouts.
export { Textarea as _Textarea };
