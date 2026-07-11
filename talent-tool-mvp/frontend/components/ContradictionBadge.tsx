"use client";

/**
 * ContradictionBadge — surfaces where two data sources disagree about the
 * same field (e.g. CV says 5 yrs React, journal says "just started").
 *
 * The shape mirrors the `conflict_flags` column populated by
 * `clarifier_agent.py` (objects with `source_a`, `source_b`, `explanation`).
 */

import * as React from "react";
import { AlertTriangle, GitBranch, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  SOURCE_LABEL,
  type SourceLabel,
  type Contradiction,
} from "@/lib/api-clarification";
import { Badge } from "@/components/ui/badge";

function normaliseSource(raw: string): { label: string; tone: SourceLabel } {
  const key = raw.toLowerCase().trim();
  for (const candidate of Object.keys(SOURCE_LABEL) as SourceLabel[]) {
    if (candidate !== "unknown" && key.includes(candidate)) {
      return { label: SOURCE_LABEL[candidate], tone: candidate };
    }
  }
  return { label: raw || "未标明来源", tone: "unknown" };
}

export interface ContradictionBadgeProps {
  contradiction: Contradiction;
  /** When true, render a compact pill instead of a full row. */
  compact?: boolean;
  className?: string;
}

export function ContradictionBadge({
  contradiction,
  compact = false,
  className,
}: ContradictionBadgeProps) {
  const a = normaliseSource(contradiction.source_a ?? "");
  const b = normaliseSource(contradiction.source_b ?? "");

  if (compact) {
    return (
      <Badge
        variant="outline"
        className={cn(
          "gap-1 border-amber-300 bg-amber-50 text-amber-800",
          className,
        )}
        title={contradiction.explanation}
      >
        <AlertTriangle className="size-3" />
        {a.label} vs {b.label}
      </Badge>
    );
  }

  return (
    <div
      className={cn(
        "rounded-xl border border-amber-200 bg-amber-50/70 p-4 space-y-3",
        className,
      )}
      role="note"
      aria-label="数据冲突提示"
    >
      <div className="flex items-start gap-2">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-amber-200 text-amber-800">
          <AlertTriangle className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-900">
            <Sparkles className="size-3.5" />
            数据冲突
            {contradiction.fields?.length ? (
              <span className="text-xs font-normal text-amber-700">
                · 字段 {contradiction.fields.join(", ")}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-sm text-amber-900/90">
            {contradiction.explanation || "两个来源对同一信息给出了不同描述,请确认。"}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <SourceChip label={a.label} tone={a.tone} />
        <GitBranch className="size-3 text-amber-600" aria-hidden />
        <SourceChip label={b.label} tone={b.tone} />
      </div>
    </div>
  );
}

function SourceChip({ label, tone }: { label: string; tone: SourceLabel }) {
  const palette: Record<SourceLabel, string> = {
    profile: "border-blue-200 bg-blue-50 text-blue-700",
    journals: "border-emerald-200 bg-emerald-50 text-emerald-700",
    conversations: "border-violet-200 bg-violet-50 text-violet-700",
    emotion_history: "border-rose-200 bg-rose-50 text-rose-700",
    cv: "border-amber-200 bg-amber-50 text-amber-700",
    agent_inference: "border-fuchsia-200 bg-fuchsia-50 text-fuchsia-700",
    unknown: "border-slate-200 bg-slate-50 text-slate-600",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 font-medium",
        palette[tone],
      )}
    >
      {label}
    </span>
  );
}

export interface ContradictionListProps {
  contradictions: Contradiction[] | undefined | null;
  className?: string;
}

/** Renders a stacked list of `ContradictionBadge`s, or nothing if empty. */
export function ContradictionList({
  contradictions,
  className,
}: ContradictionListProps) {
  const items = contradictions ?? [];
  if (items.length === 0) return null;

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center gap-2 text-xs font-medium text-amber-700">
        <AlertTriangle className="size-3.5" />
        检测到 {items.length} 处数据冲突
      </div>
      <div className="space-y-2">
        {items.map((c, i) => (
          <ContradictionBadge key={i} contradiction={c} />
        ))}
      </div>
    </div>
  );
}