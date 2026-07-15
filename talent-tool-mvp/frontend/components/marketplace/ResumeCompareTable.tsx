"use client";

/**
 * T6108 — Resume side-by-side compare table.
 *
 * Renders 2-5 resumes as a candidate-as-column matrix aligned across the
 * HR's five decision dimensions: 基本信息 / 技能 / 学历 / 经验 / 匹配度.
 * The first column lists the dimension rows; one column per candidate.
 * Top-3 diff highlights (largest cross-candidate spread) are surfaced as a
 * compact summary above the table.
 */
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  CompareItem,
  CompareResult,
  DimensionScore,
  DiffDimension,
} from "@/lib/api-hr-assistant";

// friendly labels for the canonical comparison dimensions
const DIMENSION_LABELS: Record<string, string> = {
  basic: "基本信息",
  skill: "技能",
  skills: "技能",
  education: "学历",
  experience: "经验",
  match: "匹配度",
  salary: "薪资",
};

function dimLabel(dim: string): string {
  return DIMENSION_LABELS[dim] ?? dim;
}

function scoreColor(score: number): string {
  if (score >= 75) return "text-emerald-600";
  if (score >= 50) return "text-amber-600";
  return "text-rose-600";
}

function diffLabel(diff: DiffDimension): string {
  const label = dimLabel(diff.dimension);
  const vals = Object.values(diff.values);
  if (!vals.length) return label;
  const hi = Math.max(...vals);
  const lo = Math.min(...vals);
  return `${label} (差距 ${Math.round(hi - lo)})`;
}

export interface ResumeCompareTableProps {
  result: CompareResult;
  className?: string;
}

export function ResumeCompareTable({
  result,
  className,
}: ResumeCompareTableProps) {
  const items = result.items ?? [];
  const dimensions = result.dimensions?.length
    ? result.dimensions
    : Array.from(
        new Set(items.flatMap((it) => Object.keys(it.dimensions ?? {})))
      );
  const highlights = result.highlights ?? [];

  if (!items.length) {
    return (
      <Card className={className}>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          暂无对比数据。请选择 2-5 份简历后点击「开始对比」。
        </CardContent>
      </Card>
    );
  }

  return (
    <div className={className}>
      {highlights.length > 0 ? (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">差异高亮 (Top {highlights.length})</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {highlights.map((h, idx) => (
              <Badge key={`${h.dimension}-${idx}`} variant="secondary">
                {diffLabel(h)}
              </Badge>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{result.title ?? "简历对比"}</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-32">维度</TableHead>
                {items.map((it) => (
                  <TableHead key={it.id} className="min-w-[160px]">
                    <div className="font-medium">
                      {it.name || `候选人 ${it.id.slice(0, 6)}`}
                    </div>
                    <div className="text-xs font-normal text-muted-foreground">
                      {it.id.slice(0, 8)}
                    </div>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {dimensions.map((dim) => (
                <TableRow key={dim}>
                  <TableCell className="font-medium">{dimLabel(dim)}</TableCell>
                  {items.map((it) => (
                    <DimensionCell
                      key={`${it.id}-${dim}`}
                      score={it.dimensions?.[dim]}
                    />
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function DimensionCell({ score }: { score?: DimensionScore }) {
  if (!score) {
    return <TableCell className="text-muted-foreground">—</TableCell>;
  }
  const value =
    typeof score.score === "number"
      ? score.score
      : null;
  const detail =
    score.label ??
    (typeof score.detail === "string" ? score.detail : null);
  if (value === null) {
    return (
      <TableCell>
        {detail ? (
          <span className="text-sm">{String(detail)}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
    );
  }
  return (
    <TableCell>
      <div className="flex items-center gap-2">
        <Progress value={value} className="w-20" />
        <span className={`text-sm font-medium ${scoreColor(value)}`}>
          {Math.round(value)}
        </span>
      </div>
      {detail ? (
        <div className="mt-1 text-xs text-muted-foreground">
          {String(detail)}
        </div>
      ) : null}
    </TableCell>
  );
}

export type { CompareItem };
