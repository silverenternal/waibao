"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * HR ticket Kanban — /tickets (T207).
 *
 * - Bootstraps from GET /api/tickets (HR scope).
 * - Hands the data to <TicketBoard/> which handles grouping + filtering.
 * - Polls / re-fetches every 30 s so SLA badges stay current without a
 *   websocket plumbing dependency.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, RefreshCcw, Loader2, AlertCircle, Ticket as TicketIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import { TicketBoard } from "@/components/tickets/TicketBoard";
import { ticketsApi, type Ticket } from "@/lib/api-tickets";

const REFRESH_MS = 30_000;

export default function HrTicketsPage() {
  const router = useRouter();
  const [tickets, setTickets] = React.useState<Ticket[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);

  const load = React.useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const resp = await ticketsApi.list({ limit: 200 });
      setTickets(resp.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载工单失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  React.useEffect(() => {
    load();
    const id = window.setInterval(() => load(), REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <ErrorBoundary>(<div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
        {/* Header */}
        <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => router.push("/employer")}
                aria-label="返回"
              >
                <ArrowLeft className="size-4" />
              </Button>
              <div>
                <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
                  <TicketIcon className="size-5 text-blue-500" />
                  HR 工单看板
                </h1>
                <p className="text-xs text-muted-foreground">
                  open · in_progress · awaiting · resolved 四列分流; SLA 倒计时实时刷新
                </p>
              </div>
            </div>

            <Button
              variant="outline"
              onClick={() => load(true)}
              disabled={refreshing}
              className="gap-2"
            >
              {refreshing ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCcw className="size-4" />
              )}
              刷新
            </Button>
          </div>
        </header>
        {/* Body */}
        <main className="mx-auto max-w-7xl px-6 py-6">
          {loading && <LoadingState />}
          {error && !loading && <ErrorState message={error} onRetry={() => load(true)} />}

          {!loading && !error && (
            <TicketBoard
              tickets={tickets}
              hideAssignee={false}
              onSelect={(t) => router.push(`/tickets/${t.id}`)}
            />
          )}
        </main>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
        <Loader2 className="size-4 animate-spin text-blue-500" />
        加载工单中...
      </CardContent>
    </Card>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="border-rose-200 bg-rose-50">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-sm text-rose-700">
        <AlertCircle className="size-5" />
        <span>{message}</span>
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      </CardContent>
    </Card>
  );
}

export { cn as _cn };
