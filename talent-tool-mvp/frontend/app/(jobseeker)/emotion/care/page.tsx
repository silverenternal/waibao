"use client";

/**
 * v8.1 T3604 — 情绪关怀页面 (求职者侧)
 */

import * as React from "react";

import { Card } from "@/components/ui/card";
import { EmotionCareCard } from "@/components/emotion/EmotionCareCard";

interface Ticket {
  id: string;
  user_id: string;
  level: "light" | "medium" | "heavy";
  risk_level: string;
  primary_emotion: string;
  trigger_text?: string;
  hr_notified?: boolean;
  created_at?: string;
  closed_at?: string | null;
}

interface Action {
  action_id: string;
  action_type: string;
  payload: Record<string, unknown>;
}

export default function EmotionCarePage() {
  const [tickets, setTickets] = React.useState<Ticket[]>([]);
  const [actions, setActions] = React.useState<Record<string, Action[]>>({});
  const userId = "demo-user";

  React.useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const r = await fetch(`/api/v8_1/emotion/care/tickets?user_id=${userId}`);
        const j = await r.json();
        if (!mounted) return;
        const ts = j.tickets ?? [];
        setTickets(ts);
        for (const t of ts) {
          const ar = await fetch(`/api/v8_1/emotion/care/tickets/${t.id}/actions`);
          const aj = await ar.json();
          if (mounted) {
            setActions((prev) => ({ ...prev, [t.id]: aj.actions ?? [] }));
          }
        }
      } catch {
        // dev fallback
        if (mounted) {
          setTickets([
            {
              id: "demo",
              user_id: userId,
              level: "light",
              risk_level: "mild",
              primary_emotion: "anxiety",
              trigger_text: "今天有点焦虑",
              created_at: new Date().toISOString(),
            } as Ticket,
          ]);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="container mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold">情绪关怀</h1>
      <p className="text-sm text-slate-600">
        当系统检测到你情绪有波动,会自动启动关怀 workflow. 你也可以在这里查看历史记录.
      </p>
      {tickets.length === 0 ? (
        <Card className="p-6 text-center text-sm text-slate-500">
          暂无关怀记录
        </Card>
      ) : (
        tickets.map((t) => (
          <EmotionCareCard
            key={t.id}
            ticket={t as any}
            actions={(actions[t.id] ?? []) as any}
            onClose={async () => {
              await fetch(`/api/v8_1/emotion/care/tickets/${t.id}/close`, {
                method: "POST",
              });
              setTickets((prev) =>
                prev.map((p) =>
                  p.id === t.id
                    ? { ...p, closed_at: new Date().toISOString() }
                    : p,
                ),
              );
            }}
          />
        ))
      )}
    </div>
  );
}