"use client";

/**
 * PolicyDetail (T601)
 *
 * Renders a single policy document with category metadata, effective
 * date, and a clause-by-clause breakdown (driven by `PolicyClause[]`).
 * Falls back to a paragraph view when no clauses are present.
 *
 * Used inside `app/(employer)/policy/[id]/page.tsx`. Pure presentation.
 */

import * as React from "react";
import {
  ArrowLeft,
  CalendarClock,
  FileText,
  Loader2,
  Tag,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import {
  POLICY_CATEGORY_LABEL,
  riskLevelFromScore,
  type PolicyClause,
  type PolicyDoc,
} from "@/lib/api-policy";
import { LegalRiskBadge } from "./LegalRiskBadge";

export interface PolicyDetailProps {
  doc: PolicyDoc | null;
  clauses?: PolicyClause[];
  loading?: boolean;
  error?: string | null;
  onBack?: () => void;
  className?: string;
}

export function PolicyDetail({
  doc,
  clauses,
  loading,
  error,
  onBack,
  className,
}: PolicyDetailProps) {
  if (loading) {
    return (
      <Card className={className}>
        <CardHeader>
          <Skeleton className="h-6 w-1/2" />
          <Skeleton className="mt-2 h-3 w-1/4" />
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="h-3 w-2/3" />
        </CardContent>
      </Card>
    );
  }
  if (error) {
    return (
      <Card className={cn("border-rose-200 bg-rose-50/60", className)}>
        <CardContent className="flex items-center gap-2 py-4 text-sm text-rose-700">
          <Loader2 className="hidden" />
          <span>{error}</span>
        </CardContent>
      </Card>
    );
  }
  if (!doc) return null;

  const categoryLabel =
    POLICY_CATEGORY_LABEL[doc.category as keyof typeof POLICY_CATEGORY_LABEL] ??
    doc.category;

  const clauseList = clauses ?? [];
  const overallRiskScore = aggregateRisk(clauseList);

  return (
    <div className={cn("space-y-4", className)}>
      {onBack && (
        <Button variant="ghost" size="sm" onClick={onBack} className="gap-1">
          <ArrowLeft className="size-4" />
          返回列表
        </Button>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="text-xs">
              <Tag className="mr-1 size-3" />
              {categoryLabel}
            </Badge>
            <LegalRiskBadge
              score={overallRiskScore}
              label={
                clauseList.length > 0
                  ? `整体 · ${(overallRiskScore * 100).toFixed(0)} 分`
                  : undefined
              }
            />
            {doc.effective_from && (
              <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                <CalendarClock className="size-3.5" />
                生效 {new Date(doc.effective_from).toLocaleDateString("en-GB")}
              </span>
            )}
          </div>
          <CardTitle className="mt-2 text-xl">{doc.title}</CardTitle>
          {doc.content && (
            <CardDescription className="whitespace-pre-wrap text-sm">
              {doc.content.slice(0, 320)}
              {doc.content.length > 320 ? "…" : ""}
            </CardDescription>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Clause breakdown */}
          {clauseList.length > 0 ? (
            <ol className="space-y-3">
              {clauseList.map((c, idx) => {
                const risk = c.risk_score ?? 0;
                const level = c.risk_level ?? riskLevelFromScore(risk);
                return (
                  <li
                    key={c.id ?? idx}
                    className={cn(
                      "rounded-lg border border-slate-200 bg-white p-4 shadow-sm",
                      level === "high" && "border-rose-200 bg-rose-50/40",
                      level === "medium" && "border-amber-200 bg-amber-50/30",
                    )}
                  >
                    <div className="flex items-start gap-2">
                      <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-slate-100 text-[10px] font-semibold text-slate-600">
                        {idx + 1}
                      </span>
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-sm font-semibold text-slate-900">
                            {c.title ?? `条款 ${idx + 1}`}
                          </h4>
                          <LegalRiskBadge level={level} size="sm" />
                          {c.effective_from && (
                            <span className="text-[10px] text-slate-400">
                              生效 {new Date(c.effective_from).toLocaleDateString("en-GB")}
                            </span>
                          )}
                        </div>
                        {c.text && (
                          <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-700">
                            {c.text}
                          </p>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : doc.content ? (
            <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-4 text-sm text-slate-800">
              {doc.content}
            </pre>
          ) : (
            <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-6 text-center text-xs text-slate-500">
              <FileText className="mx-auto mb-2 size-4 text-slate-400" />
              暂无详细内容
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Pick the maximum risk score across clauses as the "overall" signal. */
function aggregateRisk(clauses: PolicyClause[]): number {
  if (clauses.length === 0) return 0;
  return clauses.reduce((acc, c) => Math.max(acc, c.risk_score ?? 0), 0);
}
