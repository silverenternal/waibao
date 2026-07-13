"use client";

/**
 * v8.1 T3603 — ProactiveToast
 *
 * 监听 /api/v8_1/proactive/logs 显示最新 push 通知.
 */

import * as React from "react";
import { Bell } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface ProactivePushLog {
  id: string;
  user_id: string;
  trigger: string;
  status: string;
  reason?: string;
  channels?: string[];
  created_at: string;
}

export interface ProactiveToastProps {
  logs: ProactivePushLog[];
  onClick?: (log: ProactivePushLog) => void;
  className?: string;
}

const STATUS_COLOR: Record<string, string> = {
  dispatched: "bg-green-100 text-green-700",
  skipped_quota: "bg-yellow-100 text-yellow-700",
  skipped_quiet: "bg-yellow-100 text-yellow-700",
  failed: "bg-red-100 text-red-700",
};

export function ProactiveToast({
  logs,
  onClick,
  className,
}: ProactiveToastProps) {
  if (logs.length === 0) {
    return (
      <Card className={cn("p-6 text-center text-sm text-slate-500", className)}>
        没有新的推送
      </Card>
    );
  }
  return (
    <div className={cn("space-y-2", className)}>
      {logs.slice(-5).reverse().map((log) => (
        <Card key={log.id} className="p-3 flex items-center gap-3">
          <Bell className="w-4 h-4 text-slate-600" aria-hidden="true" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-800">
                {log.trigger}
              </span>
              <span
                className={cn(
                  "px-2 py-0.5 rounded text-xs",
                  STATUS_COLOR[log.status] ?? "bg-slate-100",
                )}
              >
                {log.status}
              </span>
            </div>
            {log.reason ? (
              <p className="text-xs text-slate-500 mt-1">{log.reason}</p>
            ) : null}
          </div>
          {onClick ? (
            <Button size="sm" variant="ghost" onClick={() => onClick(log)}>
              查看
            </Button>
          ) : null}
        </Card>
      ))}
    </div>
  );
}

export default ProactiveToast;