"use client";

/**
 * JournalWarningTimeline (T606)
 *
 * Vertical timeline that surfaces every warning string the journal agent
 * flagged (`ai_warnings[]`) across the user's diary history. Each row:
 *   - date + rating chip on the left
 *   - warning bullet(s) on the right
 *
 * Lets the user spot recurring issues (eg weekly meetings draining
 * energy) at a glance.
 */

import * as React from "react";
import {
  AlertTriangle,
  Calendar,
  Quote,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export interface JournalWarningRow {
  id: string;
  journal_date: string;
  ai_rating: string | null;
  ai_warnings: string[];
  content?: string;
}

export interface JournalWarningTimelineProps {
  rows: JournalWarningRow[];
  className?: string;
  title?: string;
}

const RATING_COLOR: Record<string, string> = {
  excellent: "bg-emerald-500",
  good: "bg-blue-500",
  warning: "bg-rose-500",
};

export function JournalWarningTimeline({
  rows,
  className,
  title = "日记警告时间线",
}: JournalWarningTimelineProps) {
  if (rows.length === 0) {
    return (
      <Card className={cn("border-dashed", className)}>
        <CardContent className="flex items-center gap-2 py-6 text-xs text-slate-500">
          <AlertTriangle className="size-4 text-slate-400" />
          近期日记无明显警告,继续保持!
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <AlertTriangle className="size-4 text-rose-500" />
          {title}
          <Badge variant="outline" className="ml-auto text-[10px]">
            {rows.length} 条警告
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="relative ml-2 space-y-4 border-l border-slate-200 pl-5">
          {rows.map((row) => (
            <li key={row.id} className="relative">
              <span
                aria-hidden
                className={cn(
                  "absolute -left-[27px] grid size-5 place-items-center rounded-full text-white shadow-sm ring-2 ring-white",
                  RATING_COLOR[row.ai_rating ?? ""] ?? "bg-slate-400",
                )}
              >
                <AlertTriangle className="size-3" />
              </span>
              <header className="mb-1 flex items-center gap-2 text-xs text-slate-600">
                <Calendar className="size-3.5" />
                <span className="tabular-nums">{row.journal_date}</span>
                {row.ai_rating && (
                  <Badge variant="outline" className="text-[10px]">
                    {row.ai_rating}
                  </Badge>
                )}
              </header>
              <ul className="space-y-1 rounded-md border border-rose-200 bg-rose-50/40 p-2 text-[11px] text-rose-700">
                {row.ai_warnings.map((w, i) => (
                  <li key={i} className="flex items-start gap-1">
                    <span className="mt-0.5 size-1.5 shrink-0 rounded-full bg-rose-400" />
                    <span className="whitespace-pre-wrap">{w}</span>
                  </li>
                ))}
              </ul>
              {row.content && (
                <details className="mt-1 text-[11px] text-slate-500">
                  <summary className="inline-flex cursor-pointer items-center gap-1">
                    <Quote className="size-3" />
                    查看上下文
                  </summary>
                  <p className="mt-1 line-clamp-3 whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-2 text-[11px] text-slate-600">
                    {row.content}
                  </p>
                </details>
              )}
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
