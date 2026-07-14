"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v8.1 T3606 — 规划执行追踪页面
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { AdjustmentSuggestionList } from "@/components/plan/AdjustmentSuggestion";
import { CheckinModal } from "@/components/plan/CheckinModal";
import { PlanGantt } from "@/components/plan/PlanGantt";

interface GanttData {
  plan_id?: string;
  tasks: {
    title: string;
    progress: number;
    completed: boolean;
    duration?: string;
    bucket: "short" | "mid" | "long";
    priority?: string;
  }[];
  milestones: {
    title: string;
    target_date: string;
    completed: boolean;
    progress?: number;
    notes?: string;
  }[];
  overall_progress: number;
}

interface Suggestion {
  kind: "shrink_scope" | "add_bonus";
  item: string;
  suggestion: string;
  priority?: string;
}

export default function PlanProgressPage() {
  const [data, setData] = React.useState<GanttData | null>(null);
  const [suggestions, setSuggestions] = React.useState<Suggestion[]>([]);
  const [openCheckin, setOpenCheckin] = React.useState(false);
  const userId = "demo-user";

  const refresh = React.useCallback(async () => {
    try {
      const g = await fetch(`/api/v8_1/plan/gantt?user_id=${userId}`).then((r) =>
        r.json(),
      );
      const s = await fetch(`/api/v8_1/plan/suggestions?user_id=${userId}`).then(
        (r) => r.json(),
      );
      setData(g);
      setSuggestions(s.suggestions ?? []);
    } catch {
      setData(null);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">规划进度</h1>
          <Button onClick={() => setOpenCheckin(true)}>每日打卡</Button>
        </div>
        {data ? (
          <>
            <Card className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-slate-700">
                  总进度 {Math.round(data.overall_progress * 100)}%
                </span>
              </div>
              <div className="h-2 bg-slate-100 rounded">
                <div
                  className="h-full bg-blue-500 rounded"
                  style={{ width: `${data.overall_progress * 100}%` }}
                />
              </div>
            </Card>
            <PlanGantt tasks={data.tasks} milestones={data.milestones} />
          </>
        ) : (
          <Card className="p-6 text-center text-sm text-slate-500">
            还没有规划 — 请先创建一份计划
          </Card>
        )}
        <div>
          <h2 className="text-lg font-semibold mb-2">智能调整建议</h2>
          <AdjustmentSuggestionList suggestions={suggestions as any} />
        </div>
        <CheckinModal
          open={openCheckin}
          onOpenChange={setOpenCheckin}
          items={(data?.tasks ?? []).map((t) => ({ title: t.title }))}
          onSubmit={async (title, note) => {
            await fetch(`/api/v8_1/plan/checkin`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ user_id: userId, item_title: title, note }),
            });
            refresh();
          }}
        />
      </div>)</ErrorBoundary>
  );
}