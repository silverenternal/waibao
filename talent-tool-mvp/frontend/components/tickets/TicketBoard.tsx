"use client";

/**
 * TicketBoard (T207).
 *
 * Kanban-style layout with four columns — open / in_progress / awaiting_user /
 * resolved. "closed" is folded into an "All closed" tab pill above the board
 * rather than occupying column real estate (it's a terminal state).
 *
 *   ┌─ Filter bar (priority + assignee + refresh + view-mode) ─┐
 *   ├─ Column headings (status + count + colour stripe) ──────┤
 *   ├─ Vertical card list (overflow-y scroll, max-height) ───┤
 *   └─────────────────────────────────────────────────────────┘
 *
 * Selecting a card bubbles up via `onSelect(ticket)` so the parent can
 * drive navigation (e.g. router.push(`/tickets/${ticket.id}`)). This keeps
 * the board itself presentational and trivially embeddable.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  CircleDot,
  Loader2,
  PauseCircle,
  CheckCircle2,
  Archive,
  AlertOctagon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { TicketCard } from "@/components/tickets/TicketCard";
import { Badge } from "@/components/ui/badge";
import {
  type Ticket,
  type TicketStatus,
  type TicketPriority,
  STATUS_LABEL,
  STATUS_COLOR,
  PRIORITY_LABEL,
} from "@/lib/api-tickets";

interface Column {
  status: TicketStatus;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
}

const COLUMNS: Column[] = [
  {
    status: "open",
    label: STATUS_LABEL.open,
    description: "新收到,等待分配",
    icon: CircleDot,
    accent: "border-t-blue-500",
  },
  {
    status: "in_progress",
    label: STATUS_LABEL.in_progress,
    description: "HR 处理中",
    icon: Loader2,
    accent: "border-t-amber-500",
  },
  {
    status: "awaiting_user",
    label: STATUS_LABEL.awaiting_user,
    description: "等待员工补充信息",
    icon: PauseCircle,
    accent: "border-t-purple-500",
  },
  {
    status: "resolved",
    label: STATUS_LABEL.resolved,
    description: "已解决,可关闭",
    icon: CheckCircle2,
    accent: "border-t-emerald-500",
  },
];

export interface TicketBoardProps {
  tickets: Ticket[];
  /** Hide the assignee column (used on the employee self-view). */
  hideAssignee?: boolean;
  /** Currently selected ticket id (highlighted). */
  selectedId?: string;
  /** Called when the user clicks a card. Defaults to router.push('/tickets/<id>'). */
  onSelect?: (ticket: Ticket) => void;
  /** When true, hides the closed tickets toggle. */
  showClosedToggle?: boolean;
  className?: string;
}

type PriorityFilter = "all" | TicketPriority;

export function TicketBoard({
  tickets,
  hideAssignee = false,
  selectedId,
  onSelect,
  showClosedToggle = true,
  className,
}: TicketBoardProps) {
  const router = useRouter();
  const [priority, setPriority] = React.useState<PriorityFilter>("all");
  const [showClosed, setShowClosed] = React.useState(false);
  const [search, setSearch] = React.useState("");

  const filtered = React.useMemo(() => {
    let out = tickets;
    if (priority !== "all") out = out.filter((t) => t.priority === priority);
    const q = search.trim().toLowerCase();
    if (q) {
      out = out.filter(
        (t) =>
          t.title.toLowerCase().includes(q) ||
          (t.description || "").toLowerCase().includes(q) ||
          (t.tags || []).some((tag) => tag.toLowerCase().includes(q)),
      );
    }
    return out;
  }, [tickets, priority, search]);

  const grouped = React.useMemo(() => {
    const map: Record<TicketStatus, Ticket[]> = {
      open: [],
      in_progress: [],
      awaiting_user: [],
      resolved: [],
      closed: [],
    };
    for (const t of filtered) map[t.status]?.push(t);
    return map;
  }, [filtered]);

  const closedCount = grouped.closed.length;
  const visibleColumns = showClosedToggle
    ? COLUMNS
    : COLUMNS;

  function handleSelect(t: Ticket) {
    if (onSelect) onSelect(t);
    else router.push(`/tickets/${t.id}`);
  }

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {/* ---------- Filter bar ---------- */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
        <div className="flex items-center gap-1 text-xs text-slate-500">
          优先级:
        </div>
        <div className="flex flex-wrap gap-1">
          {(["all", "urgent", "high", "normal", "low"] as PriorityFilter[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPriority(p)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs transition",
                priority === p
                  ? "border-blue-300 bg-blue-50 text-blue-700"
                  : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
              )}
            >
              {p === "all" ? "全部" : PRIORITY_LABEL[p]}
            </button>
          ))}
        </div>

        <div className="mx-2 h-5 w-px bg-slate-200" />

        <input
          type="search"
          placeholder="搜索标题、描述、标签..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 flex-1 min-w-[180px] rounded-md border border-slate-200 bg-white px-2 text-sm focus:border-blue-400 focus:outline-none"
        />

        {showClosedToggle && closedCount > 0 && (
          <button
            type="button"
            onClick={() => setShowClosed((s) => !s)}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs",
              showClosed
                ? "border-slate-400 bg-slate-100 text-slate-700"
                : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50",
            )}
          >
            <Archive className="size-3" />
            已关闭 ({closedCount})
          </button>
        )}
      </div>

      {/* ---------- KPI strip ---------- */}
      <KpiStrip tickets={tickets} />

      {/* ---------- Columns ---------- */}
      <div className="grid gap-4 lg:grid-cols-4 md:grid-cols-2">
        {visibleColumns.map((col) => {
          const list = grouped[col.status];
          return (
            <section
              key={col.status}
              aria-label={col.label}
              className={cn(
                "flex flex-col rounded-xl border border-slate-200 bg-slate-50/60",
                "border-t-4",
                col.accent,
              )}
            >
              <header className="flex items-start justify-between gap-2 px-3 pt-3 pb-2">
                <div className="flex items-center gap-2">
                  <col.icon
                    className={cn(
                      "size-4",
                      col.status === "open" && "text-blue-600",
                      col.status === "in_progress" && "text-amber-600",
                      col.status === "awaiting_user" && "text-purple-600",
                      col.status === "resolved" && "text-emerald-600",
                    )}
                  />
                  <div>
                    <div className="flex items-center gap-1.5">
                      <h2 className="text-sm font-semibold text-slate-800">
                        {col.label}
                      </h2>
                      <Badge
                        variant="outline"
                        className={cn("border", STATUS_COLOR[col.status])}
                      >
                        {list.length}
                      </Badge>
                    </div>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {col.description}
                    </p>
                  </div>
                </div>
              </header>

              <div
                className={cn(
                  "flex flex-col gap-2 px-3 pb-3",
                  "max-h-[calc(100vh-280px)] min-h-[120px] overflow-y-auto",
                )}
              >
                {list.length === 0 ? (
                  <div className="rounded-md border border-dashed border-slate-200 bg-white/60 py-6 text-center text-xs text-slate-400">
                    暂无工单
                  </div>
                ) : (
                  list.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => handleSelect(t)}
                      className={cn(
                        "block w-full cursor-pointer rounded-lg text-left transition",
                        "focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                        selectedId === t.id && "ring-2 ring-blue-500",
                      )}
                    >
                      <TicketCard
                        ticket={t}
                        compact
                        showAssignee={!hideAssignee}
                        className="cursor-pointer"
                      />
                    </button>
                  ))
                )}
              </div>
            </section>
          );
        })}
      </div>

      {/* ---------- Closed tray ---------- */}
      {showClosedToggle && showClosed && closedCount > 0 && (
        <details className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium text-slate-700">
            <Archive className="size-4 text-slate-500" />
            已关闭 ({closedCount})
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {grouped.closed.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => handleSelect(t)}
                className="block w-full cursor-pointer rounded-lg text-left"
              >
                <TicketCard ticket={t} compact showAssignee={!hideAssignee} />
              </button>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: small KPI strip summarising the queue.
// ---------------------------------------------------------------------------

function KpiStrip({ tickets }: { tickets: Ticket[] }) {
  const total = tickets.length;
  const overdue = tickets.filter((t) => {
    if (t.status === "resolved" || t.status === "closed") return false;
    if (!t.sla_due_at) return false;
    return new Date(t.sla_due_at).getTime() < Date.now();
  }).length;
  const urgent = tickets.filter((t) => t.priority === "urgent").length;
  const waiting = tickets.filter((t) => t.status === "awaiting_user").length;

  const items: { label: string; value: number; icon: React.ComponentType<{ className?: string }>; tone: string }[] = [
    {
      label: "活跃工单",
      value: total - tickets.filter((t) => t.status === "closed").length,
      icon: CircleDot,
      tone: "text-blue-600",
    },
    { label: "已逾期", value: overdue, icon: AlertOctagon, tone: overdue > 0 ? "text-rose-600" : "text-slate-400" },
    { label: "紧急", value: urgent, icon: AlertOctagon, tone: urgent > 0 ? "text-rose-600" : "text-slate-400" },
    { label: "等待员工", value: waiting, icon: PauseCircle, tone: "text-purple-600" },
  ];

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {items.map((it) => (
        <div
          key={it.label}
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2"
        >
          <it.icon className={cn("size-4", it.tone)} />
          <div>
            <div className="text-xs text-slate-500">{it.label}</div>
            <div className="text-lg font-semibold tabular-nums text-slate-900">
              {it.value}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
