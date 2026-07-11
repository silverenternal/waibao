"use client";

/**
 * PolicyList (T601)
 *
 * Card grid that renders `PolicyDoc[]` returned by GET /api/policy/list.
 * The list page (`app/(employer)/policy/page.tsx`) owns the loader so the
 * component stays presentational and easy to drop into other shells
 * (e.g. an employer's onboarding pipeline).
 *
 * Empty state guides the user to either upload a policy doc or relax
 * the filter — important because many orgs will start with zero.
 */

import * as React from "react";
import {
  FileText,
  CalendarClock,
  Loader2,
  Filter as FilterIcon,
  Inbox,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import {
  snippet,
  POLICY_CATEGORY_LABEL,
  type PolicyDoc,
} from "@/lib/api-policy";
import { LegalRiskBadge } from "./LegalRiskBadge";

export interface PolicyListProps {
  docs: PolicyDoc[];
  loading?: boolean;
  /** Tap any card to navigate to detail page. */
  onSelect?: (doc: PolicyDoc) => void;
  /** Empty / error UX slot. */
  emptyState?: React.ReactNode;
  className?: string;
  /** Show how many docs are currently visible (used by header). */
  showCountBadge?: boolean;
  /** Optional risk score override per doc (e.g. when sourced from clauses). */
  riskById?: Record<string, number>;
}

export function PolicyList({
  docs,
  loading,
  onSelect,
  emptyState,
  className,
  showCountBadge = false,
  riskById,
}: PolicyListProps) {
  if (loading && docs.length === 0) {
    return <PolicyListSkeleton className={className} />;
  }
  if (!loading && docs.length === 0) {
    return (
      <div className={className}>
        {emptyState ?? <DefaultEmptyState />}
      </div>
    );
  }
  return (
    <ul
      className={cn(
        "grid gap-3 sm:grid-cols-2 xl:grid-cols-3",
        className,
      )}
      aria-busy={loading}
    >
      {showCountBadge && docs.length > 0 && (
        <li className="col-span-full flex items-center gap-2 text-xs text-slate-500">
          <FilterIcon className="size-3.5" />
          共 {docs.length} 项
          {loading && (
            <Loader2 className="size-3 animate-spin text-blue-500" />
          )}
        </li>
      )}
      {docs.map((doc) => (
        <li key={doc.id}>
          <PolicyCard
            doc={doc}
            onClick={onSelect ? () => onSelect(doc) : undefined}
            riskScore={riskById?.[doc.id] ?? null}
          />
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function PolicyCard({
  doc,
  onClick,
  riskScore,
}: {
  doc: PolicyDoc;
  onClick?: () => void;
  riskScore: number | null;
}) {
  const categoryLabel =
    POLICY_CATEGORY_LABEL[doc.category as keyof typeof POLICY_CATEGORY_LABEL] ??
    doc.category;
  const isClickable = Boolean(onClick);
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!isClickable}
      className={cn(
        "group relative flex w-full flex-col rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition",
        isClickable && "hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
        !isClickable && "cursor-default",
      )}
    >
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-600">
          <FileText className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px]">
              {categoryLabel}
            </Badge>
            <LegalRiskBadge score={riskScore} size="sm" />
          </div>
          <h3 className="mt-1.5 line-clamp-2 text-sm font-semibold text-slate-900">
            {doc.title}
          </h3>
        </div>
      </div>

      {doc.content && (
        <p className="mt-3 line-clamp-3 text-xs text-slate-600">
          {snippet(doc.content, 160)}
        </p>
      )}

      <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-2 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1">
          <CalendarClock className="size-3" />
          {new Date(doc.created_at).toLocaleDateString("en-GB", {
            day: "2-digit",
            month: "short",
            year: "numeric",
          })}
        </span>
        {isClickable && (
          <span className="font-medium text-blue-600 opacity-0 transition group-hover:opacity-100">
            阅读全文 →
          </span>
        )}
      </div>
    </button>
  );
}

function PolicyListSkeleton({ className }: { className?: string }) {
  return (
    <ul className={cn("grid gap-3 sm:grid-cols-2 xl:grid-cols-3", className)}>
      {Array.from({ length: 6 }).map((_, i) => (
        <li key={i}>
          <Card>
            <CardContent className="space-y-2 py-4">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-5 w-4/5" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-3/4" />
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function DefaultEmptyState() {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <Inbox className="size-8 text-slate-400" />
        <h3 className="text-sm font-medium text-slate-700">
          暂无匹配的制度
        </h3>
        <p className="max-w-md text-xs text-slate-500">
          试试切换类别、清空筛选,或先到 HR 后台上传第一篇制度文档,
          智能体会自动拆分成可检索的条款。
        </p>
        <Button size="sm" variant="outline">
          去上传制度
        </Button>
      </CardContent>
    </Card>
  );
}
