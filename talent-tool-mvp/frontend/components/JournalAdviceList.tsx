"use client";

/**
 * JournalAdviceList (T606)
 *
 * Renders the AI-generated advice captured by the daily-journal agent
 * (the `ai_advice` column on each row). Two layouts are supported:
 *   - compact (default): one-line preview with the date + rating chip
 *   - expanded (toggle): shows the full advice text + warnings list
 *
 * Filtered to a single rating on demand (parents can pre-filter the
 * `entries` array, or pass `ratingFilter` to limit here).
 */

import * as React from "react";
import {
  Lightbulb,
  AlertTriangle,
  ChevronDown,
  Quote,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export type JournalRating = "excellent" | "good" | "warning" | string | null;

export interface JournalAdviceEntry {
  id: string;
  journal_date: string;
  content: string;
  mood_score: number | null;
  ai_rating: JournalRating;
  ai_advice: string | null;
  ai_warnings?: string[];
}

export interface JournalAdviceListProps {
  entries: JournalAdviceEntry[];
  /** Restrict to entries matching this rating. */
  ratingFilter?: JournalRating | "all";
  /** Default behaviour: show compact preview; users click "展开" to see detail. */
  defaultExpanded?: boolean;
  className?: string;
  title?: string;
  description?: string;
}

const RATING_LABEL: Record<string, string> = {
  excellent: "极佳",
  good: "稳定",
  warning: "需关注",
};

const RATING_COLOR: Record<string, string> = {
  excellent: "border-emerald-300 bg-emerald-50 text-emerald-700",
  good: "border-blue-300 bg-blue-50 text-blue-700",
  warning: "border-amber-300 bg-amber-50 text-amber-700",
};

export function JournalAdviceList({
  entries,
  ratingFilter = "all",
  defaultExpanded = false,
  className,
  title = "智能体建议历史",
  description,
}: JournalAdviceListProps) {
  const filtered = React.useMemo(() => {
    if (ratingFilter === "all") return entries;
    return entries.filter((e) => (e.ai_rating ?? null) === ratingFilter);
  }, [entries, ratingFilter]);

  if (filtered.length === 0) {
    return (
      <Card className={cn("border-dashed", className)}>
        <CardContent className="flex items-center gap-2 py-6 text-xs text-slate-500">
          <Lightbulb className="size-4 text-slate-400" />
          暂无符合条件的建议。
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Lightbulb className="size-4 text-amber-500" />
          {title}
          <Badge variant="outline" className="ml-auto text-[10px]">
            {filtered.length} 条
          </Badge>
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {filtered.map((e) => (
            <AdviceItem key={e.id} entry={e} defaultExpanded={defaultExpanded} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function AdviceItem({
  entry,
  defaultExpanded,
}: {
  entry: JournalAdviceEntry;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);
  const tone =
    RATING_COLOR[entry.ai_rating ?? ""] ??
    "border-slate-200 bg-slate-50 text-slate-700";
  return (
    <li className={cn("rounded-lg border bg-white p-3 text-xs", tone)}>
      <header className="flex items-center gap-2">
        <span className="text-[10px] tabular-nums text-slate-500">
          {entry.journal_date}
        </span>
        {entry.ai_rating && (
          <Badge variant="outline" className={cn("text-[10px]", tone)}>
            {RATING_LABEL[entry.ai_rating] ?? entry.ai_rating}
          </Badge>
        )}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="ml-auto inline-flex items-center gap-1 text-[11px] text-blue-700 hover:underline"
        >
          {expanded ? "收起" : "展开"}
          <ChevronDown
            className={cn("size-3 transition-transform", expanded && "rotate-180")}
          />
        </button>
      </header>

      {!expanded && entry.ai_advice ? (
        <p className="mt-1 line-clamp-2 text-slate-700">{entry.ai_advice}</p>
      ) : null}

      {expanded && (
        <div className="mt-2 space-y-2 text-slate-700">
          {entry.content && (
            <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
              <p className="mb-1 inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-slate-500">
                <Quote className="size-3" />
                日记原文
              </p>
              <p className="whitespace-pre-wrap">{entry.content}</p>
            </div>
          )}
          {entry.ai_advice && (
            <div>
              <p className="mb-1 inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-amber-700">
                <Lightbulb className="size-3" />
                智能体建议
              </p>
              <p className="whitespace-pre-wrap">{entry.ai_advice}</p>
            </div>
          )}
          {entry.ai_warnings && entry.ai_warnings.length > 0 && (
            <div>
              <p className="mb-1 inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-rose-700">
                <AlertTriangle className="size-3" />
                警告
              </p>
              <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-rose-700">
                {entry.ai_warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
