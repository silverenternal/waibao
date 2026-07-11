"use client";

/**
 * EmployerContradictionList (T602)
 *
 * Card listing the conflicts surfaced by the employer clarifier agent.
 * Supports two shapes coming back from the LLM:
 *   - structured `Contradiction[]`  ({source_a, source_b, explanation})
 *   - free-text `string[]`          (legacy or fallback)
 *
 * Severity-coded with `conflict_flags` from the structured contract: when
 * the explanation mentions "法律"/"歧视"/"性别"/"年龄", the row renders
 * in red. Otherwise amber.
 *
 * Reused for the role/talent-image page and any future employer-side
 * dashboards that show stakeholder disagreement.
 */

import * as React from "react";
import { AlertTriangle, Info, ZapOff } from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

import type { Contradiction } from "@/lib/api-clarification";

export interface EmployerContradictionListProps {
  conflicts?: Contradiction[] | string[] | null;
  className?: string;
  title?: string;
}

const LEGAL_KEYWORDS = [
  "法律",
  "歧视",
  "性别",
  "年龄",
  "婚育",
  "民族",
  "宗教",
  "残障",
  "籍贯",
  "户口",
  "英语",
  "形象",
  "颜值",
];

export function EmployerContradictionList({
  conflicts,
  className,
  title = "多方观点冲突",
}: EmployerContradictionListProps) {
  const items = normalise(conflicts);

  if (items.length === 0) {
    return (
      <Card className={cn("border-emerald-200 bg-emerald-50/40", className)}>
        <CardContent className="flex items-center gap-2 py-6 text-sm text-emerald-700">
          <Info className="size-4" />
          当前没有发现明显的内部冲突。
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <ZapOff className="size-4 text-amber-500" />
          {title}
          <Badge variant="outline" className="ml-auto text-[10px]">
            {items.length} 项
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((c, i) => {
          const legal = hasLegal(c.explanation);
          return (
            <div
              key={i}
              className={cn(
                "rounded-lg border bg-white p-3",
                legal
                  ? "border-rose-200 bg-rose-50/40"
                  : "border-amber-200 bg-amber-50/30",
              )}
            >
              <div className="flex items-start gap-2">
                <span
                  className={cn(
                    "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full",
                    legal
                      ? "bg-rose-100 text-rose-700"
                      : "bg-amber-100 text-amber-700",
                  )}
                >
                  <AlertTriangle className="size-3.5" />
                </span>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {c.source_a && c.source_b && c.source_a !== "—" ? (
                      <span className="text-xs font-medium text-slate-700">
                        {c.source_a}
                        <span className="mx-1 text-slate-400">↔</span>
                        {c.source_b}
                      </span>
                    ) : (
                      <span className="text-xs font-medium text-slate-700">
                        立场冲突
                      </span>
                    )}
                    {legal && (
                      <Badge
                        variant="outline"
                        className="border-rose-300 bg-rose-100 text-[10px] text-rose-700"
                      >
                        可能涉及法律风险
                      </Badge>
                    )}
                  </div>
                  <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-700">
                    {c.explanation}
                  </p>
                  {c.fields && c.fields.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {c.fields.map((f) => (
                        <Badge
                          key={f}
                          variant="outline"
                          className="border-slate-200 bg-slate-50 text-[10px] text-slate-600"
                        >
                          {f}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalise(
  conflicts: Contradiction[] | string[] | null | undefined,
): Contradiction[] {
  if (!conflicts || !Array.isArray(conflicts)) return [];
  return conflicts
    .map((c): Contradiction | null => {
      if (typeof c === "string") {
        return {
          source_a: "—",
          source_b: "—",
          explanation: c,
        };
      }
      if (typeof c === "object") {
        return {
          source_a: c.source_a ?? "—",
          source_b: c.source_b ?? "—",
          explanation: c.explanation ?? "",
          fields: c.fields ?? [],
        };
      }
      return null;
    })
    .filter((c): c is Contradiction => c !== null);
}

function hasLegal(text: string): boolean {
  if (!text) return false;
  return LEGAL_KEYWORDS.some((k) => text.includes(k));
}
