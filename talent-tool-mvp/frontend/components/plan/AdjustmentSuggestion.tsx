"use client";

/**
 * v8.1 T3606 — AdjustmentSuggestion
 *
 * 智能调整建议: shrink_scope / add_bonus.
 */

import * as React from "react";
import { Lightbulb } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface AdjustmentSuggestion {
  kind: "shrink_scope" | "add_bonus";
  item: string;
  suggestion: string;
  priority?: "low" | "medium" | "high";
}

export interface AdjustmentSuggestionListProps {
  suggestions: AdjustmentSuggestion[];
  className?: string;
}

const PRIORITY_COLOR = {
  high: "border-red-300 bg-red-50",
  medium: "border-yellow-300 bg-yellow-50",
  low: "border-green-300 bg-green-50",
} as const;

const KIND_LABEL = {
  shrink_scope: "缩小范围",
  add_bonus: "加 Bonus",
} as const;

export function AdjustmentSuggestionList({
  suggestions,
  className,
}: AdjustmentSuggestionListProps) {
  if (suggestions.length === 0) {
    return (
      <Card className={cn("p-4 text-sm text-slate-500", className)}>
        暂无调整建议 — 继续按计划执行
      </Card>
    );
  }
  return (
    <div className={cn("space-y-2", className)}>
      {suggestions.map((s, idx) => (
        <Card
          key={idx}
          className={cn(
            "p-3 border",
            PRIORITY_COLOR[s.priority ?? "low"],
          )}
        >
          <div className="flex items-start gap-2">
            <Lightbulb className="w-4 h-4 text-amber-500 mt-1" aria-hidden="true" />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  {KIND_LABEL[s.kind]}
                </Badge>
                <span className="text-sm font-medium text-slate-800">
                  {s.item}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-700">{s.suggestion}</p>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

export default AdjustmentSuggestionList;