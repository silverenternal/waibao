"use client";

/**
 * v8.1 T3602 — ActionItemTracker
 *
 * 显示 action_items v2 的状态机:
 *   pending / in_progress / done / abandoned
 *
 * 支持:
 *   - 单个状态切换
 *   - 完成质量评分 (0-10)
 *   - due_date reminder
 */

import * as React from "react";
import { Check, Clock, Pause, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type ActionStatus = "pending" | "in_progress" | "done" | "abandoned";

export interface ActionItem {
  id: string;
  title: string;
  detail?: string;
  status: ActionStatus;
  feasibility?: number;
  quality_score?: number | null;
  due_date?: string | null;
  role?: string;
  plan_item_title?: string | null;
}

const STATUS_LABEL: Record<ActionStatus, string> = {
  pending: "待办",
  in_progress: "进行中",
  done: "已完成",
  abandoned: "已放弃",
};

const STATUS_COLOR: Record<ActionStatus, string> = {
  pending: "bg-slate-100 text-slate-700",
  in_progress: "bg-blue-100 text-blue-700",
  done: "bg-green-100 text-green-700",
  abandoned: "bg-gray-100 text-gray-500",
};

const STATUS_ICON: Record<ActionStatus, React.ComponentType<{ className?: string }>> = {
  pending: Clock,
  in_progress: Pause,
  done: Check,
  abandoned: X,
};

export interface ActionItemTrackerProps {
  items: ActionItem[];
  onUpdate?: (id: string, patch: Partial<ActionItem>) => Promise<void> | void;
  className?: string;
}

export function ActionItemTracker({
  items,
  onUpdate,
  className,
}: ActionItemTrackerProps) {
  return (
    <div className={cn("space-y-2", className)}>
      {items.map((item) => (
        <ActionItemRow key={item.id} item={item} onUpdate={onUpdate} />
      ))}
    </div>
  );
}

function ActionItemRow({
  item,
  onUpdate,
}: {
  item: ActionItem;
  onUpdate?: ActionItemTrackerProps["onUpdate"];
}) {
  const Icon = STATUS_ICON[item.status] ?? Clock;
  const [quality, setQuality] = React.useState<string>(
    item.quality_score?.toString() ?? "",
  );
  return (
    <Card className="p-3 flex items-start gap-3">
      <div className="flex-shrink-0 mt-0.5">
        <Icon className="w-4 h-4 text-slate-600" aria-hidden="true" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <h4 className="text-sm font-medium text-slate-800">{item.title}</h4>
          <span
            className={cn(
              "px-2 py-0.5 rounded text-xs",
              STATUS_COLOR[item.status],
            )}
          >
            {STATUS_LABEL[item.status]}
          </span>
          {item.role ? (
            <Badge variant="outline" className="text-xs">
              {item.role}
            </Badge>
          ) : null}
          {item.plan_item_title ? (
            <Badge variant="secondary" className="text-xs">
              🔗 {item.plan_item_title}
            </Badge>
          ) : null}
        </div>
        {item.detail ? (
          <p className="mt-1 text-xs text-slate-600">{item.detail}</p>
        ) : null}
        {item.due_date ? (
          <p className="mt-1 text-xs text-slate-500">
            截止: {new Date(item.due_date).toLocaleString()}
          </p>
        ) : null}
        {item.status === "done" ? (
          <div className="mt-2 flex items-center gap-2">
            <Input
              type="number"
              min="0"
              max="10"
              step="0.5"
              value={quality}
              onChange={(e) => setQuality(e.target.value)}
              className="w-20 h-7 text-xs"
              placeholder="质量分"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                onUpdate?.(item.id, {
                  quality_score: parseFloat(quality) || 0,
                })
              }
            >
              保存
            </Button>
          </div>
        ) : null}
      </div>
      <div className="flex flex-col gap-1">
        {item.status === "pending" ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onUpdate?.(item.id, { status: "in_progress" })}
          >
            开始
          </Button>
        ) : null}
        {item.status === "in_progress" ? (
          <>
            <Button
              size="sm"
              variant="default"
              onClick={() => onUpdate?.(item.id, { status: "done" })}
            >
              完成
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onUpdate?.(item.id, { status: "abandoned" })}
            >
              放弃
            </Button>
          </>
        ) : null}
      </div>
    </Card>
  );
}

export default ActionItemTracker;