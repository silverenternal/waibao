"use client";

/**
 * T2304 — 智能建议卡片 (LLM 推荐).
 *
 * 显示 description + 一键 apply / dismiss.
 */

import * as React from "react";
import { Lightbulb, Check, X, Loader2, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export type SuggestionType =
  | "priority_reduce"
  | "category_disable"
  | "channel_change"
  | "frequency_change"
  | "quiet_hours_extend";

export interface SmartSuggestionItem {
  id: string;
  type: SuggestionType;
  description: string;
  suggestion: Record<string, unknown>;
  confidence: number;
  status?: "pending" | "applied" | "dismissed";
}

export interface SmartSuggestionProps {
  item: SmartSuggestionItem;
  onApply?: (id: string) => Promise<void> | void;
  onDismiss?: (id: string) => Promise<void> | void;
}

const TYPE_LABELS: Record<SuggestionType, string> = {
  priority_reduce: "降级优先级",
  category_disable: "关闭类别",
  channel_change: "通道变更",
  frequency_change: "调整频率",
  quiet_hours_extend: "延长静默",
};

const TYPE_COLOR: Record<SuggestionType, string> = {
  priority_reduce: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  category_disable: "bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200",
  channel_change: "bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200",
  frequency_change: "bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200",
  quiet_hours_extend: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200",
};

export function SmartSuggestion(props: SmartSuggestionProps) {
  const { item, onApply, onDismiss } = props;
  const [busy, setBusy] = React.useState<"apply" | "dismiss" | null>(null);

  const handleApply = async () => {
    if (!onApply) return;
    setBusy("apply");
    try {
      await onApply(item.id);
    } finally {
      setBusy(null);
    }
  };

  const handleDismiss = async () => {
    if (!onDismiss) return;
    setBusy("dismiss");
    try {
      await onDismiss(item.id);
    } finally {
      setBusy(null);
    }
  };

  const confidencePct = Math.round((item.confidence ?? 0) * 100);
  const isDone = item.status && item.status !== "pending";

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-lg border p-4 transition-colors",
        isDone
          ? "border-slate-200 bg-slate-50 opacity-60 dark:border-slate-800 dark:bg-slate-900"
          : "border-amber-200 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-950/30",
      )}
      data-testid={`smart-suggestion-${item.id}`}
      data-suggestion-type={item.type}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-amber-500" aria-hidden="true" />
          <Badge className={TYPE_COLOR[item.type]} variant="secondary">
            {TYPE_LABELS[item.type] ?? item.type}
          </Badge>
          <Badge variant="outline" className="text-xs">
            置信度 {confidencePct}%
          </Badge>
          {isDone && (
            <Badge variant="secondary" className="text-xs">
              {item.status === "applied" ? "已应用" : "已忽略"}
            </Badge>
          )}
        </div>
      </header>

      <div className="flex items-start gap-2">
        <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
        <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-200">
          {item.description}
        </p>
      </div>

      {!isDone && (onApply || onDismiss) && (
        <footer className="flex items-center justify-end gap-2">
          {onDismiss && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDismiss}
              disabled={busy !== null}
              data-testid={`suggestion-dismiss-${item.id}`}
            >
              {busy === "dismiss" ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <X className="mr-1 h-3 w-3" aria-hidden="true" />
              )}
              忽略
            </Button>
          )}
          {onApply && (
            <Button
              variant="default"
              size="sm"
              onClick={handleApply}
              disabled={busy !== null}
              data-testid={`suggestion-apply-${item.id}`}
            >
              {busy === "apply" ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <Check className="mr-1 h-3 w-3" aria-hidden="true" />
              )}
              一键应用
            </Button>
          )}
        </footer>
      )}
    </div>
  );
}

export default SmartSuggestion;