"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v8.1 T3603 — 通知列表页面
 */

import * as React from "react";

import { ProactiveToast } from "@/components/notifications/ProactiveToast";

interface PushLog {
  id: string;
  user_id: string;
  trigger: string;
  status: string;
  reason?: string;
  channels?: string[];
  created_at: string;
}

export default function NotificationsPage() {
  const [logs, setLogs] = React.useState<PushLog[]>([]);
  const userId = "demo-user";

  React.useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const r = await fetch(`/api/v8_1/proactive/logs?user_id=${userId}`);
        const j = await r.json();
        if (mounted) setLogs(j.logs ?? []);
      } catch {
        if (mounted) setLogs([]);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 space-y-4">
        <h1 className="text-2xl font-bold">通知</h1>
        <p className="text-sm text-slate-600">智能体主动推送的消息历史</p>
        <ProactiveToast logs={logs} />
      </div>)</ErrorBoundary>
  );
}