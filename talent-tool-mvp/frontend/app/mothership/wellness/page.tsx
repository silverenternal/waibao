"use client";

/**
 * v8.1 T3604 — HR Mothership wellness dashboard
 */

import * as React from "react";

import { Card } from "@/components/ui/card";

interface Summary {
  total_tickets: number;
  open_tickets: number;
  by_level: Record<string, number>;
  resource_categories: number;
  resources_total: number;
}

interface Ticket {
  id: string;
  user_id: string;
  level: string;
  risk_level: string;
  primary_emotion: string;
  trigger_text?: string;
  hr_notified?: boolean;
  created_at?: string;
}

export default function WellnessDashboardPage() {
  const [summary, setSummary] = React.useState<Summary | null>(null);
  const [tickets, setTickets] = React.useState<Ticket[]>([]);

  React.useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const s = await fetch("/api/v8_1/emotion/care/dashboard").then((r) =>
          r.json(),
        );
        const t = await fetch("/api/v8_1/emotion/care/tickets").then((r) =>
          r.json(),
        );
        if (mounted) {
          setSummary(s);
          setTickets(t.tickets ?? []);
        }
      } catch {
        if (mounted) {
          setSummary(null);
          setTickets([]);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="container mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold">Wellness Dashboard</h1>
      <p className="text-sm text-slate-600">
        求职者情绪关怀全景 — HR Mothership 视图
      </p>

      {summary ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Stat label="总 ticket" value={summary.total_tickets} />
          <Stat label="未关闭" value={summary.open_tickets} />
          <Stat label="轻度" value={summary.by_level.light ?? 0} />
          <Stat label="中度" value={summary.by_level.medium ?? 0} />
          <Stat label="重度" value={summary.by_level.heavy ?? 0} />
        </div>
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {tickets.slice(0, 20).map((t) => (
          <Card
            key={t.id}
            className={
              "p-4 " +
              (t.level === "heavy"
                ? "bg-rose-50 border-rose-200"
                : t.level === "medium"
                ? "bg-orange-50 border-orange-200"
                : "bg-yellow-50 border-yellow-200")
            }
          >
            <div className="text-xs text-slate-500">
              {new Date(t.created_at ?? "").toLocaleString()}
            </div>
            <div className="font-medium text-sm mt-1">
              {t.primary_emotion} ({t.risk_level})
            </div>
            <p className="text-xs italic mt-1">"{t.trigger_text}"</p>
            {t.hr_notified ? (
              <span className="text-xs text-rose-700 mt-2 inline-block">
                ⚠️ HR 已通知
              </span>
            ) : null}
          </Card>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
    </Card>
  );
}