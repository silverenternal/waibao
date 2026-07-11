"use client";

/**
 * Employee self-service tickets — /my-tickets (T207).
 *
 * Two-part page:
 *   1. Top — "我的工单" list grouped by status, cards with SLA badge,
 *      linked to detail. Data comes from GET /api/tickets/me.
 *   2. Bottom — "新建工单" inline form posting to POST /api/tickets.
 *
 * Both sections refetch / re-render together so the user sees their new
 * ticket appear in the list immediately.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Plus,
  Send,
  Sparkles,
  Ticket as TicketIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { TicketCard } from "@/components/tickets/TicketCard";

import {
  ticketsApi,
  type Ticket,
  type TicketCreatePayload,
  type TicketPriority,
  type TicketCategory,
  TICKET_PRIORITIES,
  TICKET_CATEGORIES,
  PRIORITY_LABEL,
  PRIORITY_COLOR,
  CATEGORY_LABEL,
  STATUS_LABEL,
  STATUS_COLOR,
} from "@/lib/api-tickets";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; tickets: Ticket[] }
  | { kind: "error"; message: string };

export default function MyTicketsPage() {
  const router = useRouter();
  const [state, setState] = React.useState<LoadState>({ kind: "loading" });
  const [creating, setCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<TicketCreatePayload>({
    title: "",
    description: "",
    priority: "normal",
    category: "hr",
  });

  const load = React.useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const resp = await ticketsApi.myTickets({ limit: 100 });
      setState({ kind: "ready", tickets: resp.items });
    } catch (e: unknown) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : "加载失败",
      });
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim()) {
      setCreateError("请填写工单标题");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await ticketsApi.create({
        ...form,
        title: form.title.trim(),
      });
      setForm({ title: "", description: "", priority: "normal", category: "hr" });
      await load();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setCreating(false);
    }
  }

  // Group tickets by status so we can render sectioned lists.
  const grouped = React.useMemo(() => {
    if (state.kind !== "ready") return null;
    const buckets: Record<string, Ticket[]> = {};
    for (const t of state.tickets) {
      buckets[t.status] = buckets[t.status] ?? [];
      buckets[t.status].push(t);
    }
    return buckets;
  }, [state]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => router.push("/jobseeker")}
              aria-label="返回"
            >
              <ArrowLeft className="size-4" />
            </Button>
            <div>
              <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
                <TicketIcon className="size-5 text-blue-500" />
                我的工单
              </h1>
              <p className="text-xs text-muted-foreground">
                提问 HR · 查看处理进度 · SLA 倒计时实时刷新
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-6">
        {/* Create */}
        <Card>
          <CardContent className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Plus className="size-4 text-blue-500" />
                提交新工单
              </h2>
              <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">
                <Sparkles className="size-3" />
                智能体也会自动建单
              </Badge>
            </div>

            <form onSubmit={handleCreate} className="space-y-3">
              <Input
                value={form.title}
                onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
                placeholder="一句话描述你的问题,例如:请假流程不清楚 / 薪资条异常"
                maxLength={200}
                required
              />
              <Textarea
                value={form.description}
                onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
                placeholder="详细背景 (选填):时间、相关政策编号、期望的解决方案..."
                rows={3}
                maxLength={10000}
                className="resize-y"
              />

              <div className="flex flex-wrap items-center gap-3">
                <Select
                  label="类别"
                  value={form.category}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, category: v as TicketCategory }))
                  }
                  options={TICKET_CATEGORIES.map((c) => ({
                    value: c,
                    label: CATEGORY_LABEL[c] ?? c,
                  }))}
                />
                <Select
                  label="优先级"
                  value={form.priority}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, priority: v as TicketPriority }))
                  }
                  options={TICKET_PRIORITIES.map((p) => ({
                    value: p,
                    label: PRIORITY_LABEL[p],
                  }))}
                />
                <div className="ml-auto flex items-center gap-3">
                  {createError && (
                    <span className="text-xs text-rose-600">{createError}</span>
                  )}
                  <Button type="submit" disabled={creating || !form.title.trim()} className="gap-1.5">
                    {creating ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Send className="size-3.5" />
                    )}
                    提交工单
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* List */}
        <section>
          <h2 className="mb-3 text-sm font-semibold text-slate-800">我的工单历史</h2>

          {state.kind === "loading" && (
            <Card>
              <CardContent className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
                <Loader2 className="size-4 animate-spin text-blue-500" />
                加载中...
              </CardContent>
            </Card>
          )}

          {state.kind === "error" && (
            <Card className="border-rose-200 bg-rose-50">
              <CardContent className="flex items-center gap-2 py-6 text-sm text-rose-700">
                <AlertCircle className="size-4" />
                {state.message}
                <Button variant="outline" size="sm" className="ml-auto" onClick={load}>
                  重试
                </Button>
              </CardContent>
            </Card>
          )}

          {state.kind === "ready" && state.tickets.length === 0 && (
            <Card>
              <CardContent className="flex flex-col items-center gap-2 py-12 text-center text-sm text-slate-500">
                <CheckCircle2 className="size-5 text-emerald-500" />
                还没有工单,有问题随时来找 HR。
              </CardContent>
            </Card>
          )}

          {state.kind === "ready" && state.tickets.length > 0 && grouped && (
            <div className="space-y-6">
              {(["open", "in_progress", "awaiting_user", "resolved", "closed"] as const).map(
                (status) => {
                  const list = grouped[status] ?? [];
                  if (list.length === 0) return null;
                  return (
                    <div key={status}>
                      <div className="mb-2 flex items-center gap-2">
                        <Badge variant="outline" className={cn("border", STATUS_COLOR[status])}>
                          {STATUS_LABEL[status]}
                        </Badge>
                        <span className="text-xs text-slate-500">
                          ({list.length})
                        </span>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {list.map((t) => (
                          <button
                            key={t.id}
                            type="button"
                            onClick={() => router.push(`/my-tickets/${t.id}`)}
                            className="block w-full cursor-pointer rounded-lg text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                          >
                            <TicketCard ticket={t} compact showAssignee={false} />
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                },
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tiny native <select/> wrapped so it matches the rest of the form look.
// ---------------------------------------------------------------------------

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string | undefined;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-slate-600">
      <span className="text-slate-500">{label}:</span>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-800 focus:border-blue-400 focus:outline-none"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
