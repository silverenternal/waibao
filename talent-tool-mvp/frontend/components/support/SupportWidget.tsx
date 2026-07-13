"use client";

/**
 * T2604 — In-app Support Widget.
 *
 * Floating bottom-right bubble that lets an authenticated user:
 *  - create a new ticket (1 click → opens composer with auto-attached tenant/user)
 *  - view ticket history
 *  - reopen a ticket thread + reply
 *
 * UI:
 *   • idle     → round button (lifebuoy icon) anchored bottom-right
 *   • open     → expandable panel w/ composer or list view
 *
 * Server contract: `POST /api/support/tickets`, `GET /api/support/tickets`,
 * `POST /api/support/tickets/{id}/replies` (see backend/api/support.py).
 */

import * as React from "react";
import {
  LifeBuoy,
  Plus,
  RefreshCcw,
  Send,
  X,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Clock,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

type TicketStatus = "open" | "pending" | "solved" | "closed";

export interface SupportTicketSummary {
  id: string;
  public_id: string;
  subject: string;
  status: TicketStatus;
  url?: string | null;
  updated_at?: string | null;
}

export interface SupportWidgetProps {
  /** Optional override of the API base path. Defaults to `/api/support`. */
  apiBase?: string;
  /** Optional error-log payload forwarded to the server (e.g. last error). */
  initialErrorLog?: string;
  /** Optional tags to attach (e.g. feature flag id, page route). */
  defaultTags?: string[];
  /** Optional global extra context for every ticket created from here. */
  defaultContext?: Record<string, unknown>;
}

type View = "list" | "create" | "thread";

const STATUS_BADGE: Record<TicketStatus, string> = {
  open: "bg-amber-100 text-amber-800",
  pending: "bg-indigo-100 text-indigo-800",
  solved: "bg-emerald-100 text-emerald-800",
  closed: "bg-slate-200 text-slate-700",
};

const STATUS_ICON: Record<TicketStatus, React.ReactNode> = {
  open: <AlertTriangle className="h-3 w-3" aria-hidden />,
  pending: <Clock className="h-3 w-3" aria-hidden />,
  solved: <CheckCircle2 className="h-3 w-3" aria-hidden />,
  closed: <X className="h-3 w-3" aria-hidden />,
};

export function SupportWidget({
  apiBase = "/api/support",
  initialErrorLog,
  defaultTags,
  defaultContext,
}: SupportWidgetProps) {
  const [open, setOpen] = React.useState(false);
  const [view, setView] = React.useState<View>("list");
  const [tickets, setTickets] = React.useState<SupportTicketSummary[]>([]);
  const [activeTicket, setActiveTicket] = React.useState<SupportTicketSummary | null>(null);
  const [subject, setSubject] = React.useState("");
  const [body, setBody] = React.useState("");
  const [reply, setReply] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [loading, setLoading] = React.useState(false);

  const fetchTickets = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/tickets`, { credentials: "include" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as { tickets: SupportTicketSummary[] };
      setTickets(json.tickets ?? []);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  React.useEffect(() => {
    if (open) {
      void fetchTickets();
    }
  }, [open, fetchTickets]);

  const handleCreate = React.useCallback(async () => {
    if (!subject.trim() || !body.trim()) {
      setError("subject + body are required");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/tickets`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject: subject.trim(),
          body: body.trim(),
          tags: defaultTags ?? [],
          extra_context: defaultContext ?? {},
          error_logs: initialErrorLog ?? null,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
      }
      const created = (await res.json()) as SupportTicketSummary;
      setTickets((prev) => [created, ...prev]);
      setSubject("");
      setBody("");
      setView("list");
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSubmitting(false);
    }
  }, [apiBase, body, defaultContext, defaultTags, initialErrorLog, subject]);

  const handleReply = React.useCallback(async () => {
    if (!activeTicket || !reply.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/tickets/${activeTicket.id}/replies`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: reply.trim() }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
      }
      const updated = (await res.json()) as SupportTicketSummary;
      setActiveTicket(updated);
      setTickets((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
      setReply("");
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSubmitting(false);
    }
  }, [activeTicket, apiBase, reply]);

  return (
    <>
      {/* Floating trigger button */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close support widget" : "Open support widget"}
        className={cn(
          "fixed bottom-6 right-6 z-50 inline-flex h-14 w-14 items-center justify-center rounded-full shadow-lg transition",
          "bg-slate-900 text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
          open && "rotate-45 bg-slate-700",
        )}
      >
        {open ? <X className="h-6 w-6" /> : <LifeBuoy className="h-6 w-6" />}
      </button>

      {/* Widget panel */}
      {open && (
        <div
          role="dialog"
          aria-label="Support widget"
          className="fixed bottom-24 right-6 z-50 w-[360px] max-w-[92vw] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
        >
          <header className="flex items-center justify-between bg-slate-900 px-4 py-3 text-white">
            <h2 className="text-sm font-medium">waibao Support</h2>
            <button
              type="button"
              aria-label="Refresh tickets"
              onClick={() => void fetchTickets()}
              className="rounded-md p-1 hover:bg-slate-700"
            >
              <RefreshCcw className={cn("h-4 w-4", loading && "animate-spin")} />
            </button>
          </header>

          {/* Tabs */}
          <nav className="flex border-b border-slate-200 text-xs dark:border-slate-700">
            <Tab active={view === "list"} onClick={() => setView("list")}>My tickets</Tab>
            <Tab active={view === "create"} onClick={() => setView("create")}>New ticket</Tab>
            {view === "thread" && <Tab active onClick={() => setView("thread")}>Thread</Tab>}
          </nav>

          {error && (
            <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900 dark:text-red-100">
              {error}
            </div>
          )}

          <div className="max-h-96 overflow-y-auto px-4 py-3">
            {view === "list" && (
              <TicketList
                tickets={tickets}
                loading={loading}
                onOpen={(t) => {
                  setActiveTicket(t);
                  setView("thread");
                }}
                onCreate={() => setView("create")}
              />
            )}
            {view === "create" && (
              <Composer
                subject={subject}
                body={body}
                onSubject={setSubject}
                onBody={setBody}
                onSubmit={() => void handleCreate()}
                submitting={submitting}
                onCancel={() => setView("list")}
                errorLogAttached={Boolean(initialErrorLog)}
              />
            )}
            {view === "thread" && activeTicket && (
              <Thread
                ticket={activeTicket}
                reply={reply}
                onReply={setReply}
                onSend={() => void handleReply()}
                submitting={submitting}
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default SupportWidget;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Tab({ children, active, onClick }: { children: React.ReactNode; active?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-1 py-2 text-center transition",
        active ? "border-b-2 border-indigo-500 text-indigo-600" : "text-slate-500 hover:text-slate-700",
      )}
    >
      {children}
    </button>
  );
}

function TicketList({
  tickets,
  loading,
  onOpen,
  onCreate,
}: {
  tickets: SupportTicketSummary[];
  loading: boolean;
  onOpen: (t: SupportTicketSummary) => void;
  onCreate: () => void;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading tickets…
      </div>
    );
  }
  if (tickets.length === 0) {
    return (
      <div className="space-y-3 py-6 text-center">
        <p className="text-sm text-slate-500">No tickets yet.</p>
        <Button size="sm" onClick={onCreate}>
          <Plus className="mr-1 h-4 w-4" /> Open your first ticket
        </Button>
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {tickets.map((t) => (
        <li
          key={t.id}
          className="cursor-pointer rounded border border-slate-200 p-3 text-sm transition hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
          onClick={() => onOpen(t)}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-medium" title={t.subject}>{t.subject}</span>
            <span className={cn("inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs", STATUS_BADGE[t.status])}>
              {STATUS_ICON[t.status]} {t.status}
            </span>
          </div>
          <div className="mt-1 flex justify-between text-xs text-slate-500">
            <span>#{t.public_id}</span>
            <span>{t.updated_at ? new Date(t.updated_at).toLocaleString() : ""}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Composer({
  subject,
  body,
  onSubject,
  onBody,
  onSubmit,
  submitting,
  onCancel,
  errorLogAttached,
}: {
  subject: string;
  body: string;
  onSubject: (v: string) => void;
  onBody: (v: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  onCancel: () => void;
  errorLogAttached: boolean;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="space-y-3"
    >
      <label className="block">
        <span className="text-xs font-medium text-slate-600 dark:text-slate-300">Subject</span>
        <Input
          required
          minLength={3}
          value={subject}
          onChange={(e) => onSubject(e.target.value)}
          placeholder="What can we help with?"
          className="mt-1"
        />
      </label>
      <label className="block">
        <span className="text-xs font-medium text-slate-600 dark:text-slate-300">Message</span>
        <Textarea
          required
          minLength={10}
          rows={5}
          value={body}
          onChange={(e) => onBody(e.target.value)}
          placeholder="Describe the issue — tenant/user/error logs are attached automatically."
          className="mt-1"
        />
      </label>
      {errorLogAttached && (
        <p className="rounded bg-indigo-50 px-2 py-1 text-xs text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200">
          Latest error log will be attached automatically.
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button type="submit" size="sm" disabled={submitting}>
          {submitting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Send className="mr-1 h-4 w-4" />}
          Send
        </Button>
      </div>
    </form>
  );
}

function Thread({
  ticket,
  reply,
  onReply,
  onSend,
  submitting,
}: {
  ticket: SupportTicketSummary;
  reply: string;
  onReply: (v: string) => void;
  onSend: () => void;
  submitting: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded border border-slate-200 p-3 dark:border-slate-700">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium" title={ticket.subject}>{ticket.subject}</span>
          <span className={cn("inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs", STATUS_BADGE[ticket.status])}>
            {STATUS_ICON[ticket.status]} {ticket.status}
          </span>
        </div>
        <div className="mt-1 flex justify-between text-xs text-slate-500">
          <span>#{ticket.public_id}</span>
          <span>Updated {ticket.updated_at ? new Date(ticket.updated_at).toLocaleString() : "—"}</span>
        </div>
        {ticket.url && (
          <a className="mt-2 inline-block text-xs text-indigo-600 hover:underline" href={ticket.url} target="_blank" rel="noreferrer">
            Open in support portal ↗
          </a>
        )}
      </div>
      <Textarea
        rows={3}
        value={reply}
        onChange={(e) => onReply(e.target.value)}
        placeholder="Reply…"
      />
      <div className="flex justify-end">
        <Button size="sm" disabled={submitting || !reply.trim()} onClick={onSend}>
          {submitting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Send className="mr-1 h-4 w-4" />}
          Send reply
        </Button>
      </div>
    </div>
  );
}
