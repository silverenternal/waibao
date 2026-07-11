"use client";

import * as React from "react";
import { CheckCircle2, CircleDashed, AlertCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export type FieldStatus = "filled" | "empty" | "weak";

export interface ProfileField {
  /** Stable id (used by parent to focus an input or open the "ask me" drawer). */
  key: string;
  /** Display label shown to the user. */
  label: string;
  status: FieldStatus;
  /** Optional helper text shown beneath the field label. */
  hint?: string;
  /** Optional short preview of the value to confirm it's actually populated. */
  preview?: string;
  /** Weight (defaults to 1). Higher weights count more in the completion %. */
  weight?: number;
}

export interface ProfileCompletenessProps {
  fields: ProfileField[];
  /** Click handler when the user taps a missing field — usually opens an "ask me" drawer. */
  onFieldClick?: (field: ProfileField) => void;
  /** Show the full field list beneath the ring. Default true. */
  showFieldList?: boolean;
  /** Title shown in the card header. Default "档案完整度". */
  title?: string;
  className?: string;
}

function statusColor(s: FieldStatus): string {
  switch (s) {
    case "filled":
      return "text-emerald-600";
    case "weak":
      return "text-amber-600";
    default:
      return "text-muted-foreground";
  }
}

function statusLabel(s: FieldStatus): string {
  switch (s) {
    case "filled":
      return "已填写";
    case "weak":
      return "建议补充";
    default:
      return "待补充";
  }
}

/**
 * Circular progress ring + weighted field checklist.
 * Pure SVG so it renders consistently across browsers without extra deps.
 */
export function ProfileCompleteness({
  fields,
  onFieldClick,
  showFieldList = true,
  title = "档案完整度",
  className,
}: ProfileCompletenessProps) {
  const totalWeight = fields.reduce(
    (sum, f) => sum + (f.weight ?? 1),
    0,
  );
  const earned = fields.reduce((sum, f) => {
    const w = f.weight ?? 1;
    if (f.status === "filled") return sum + w;
    if (f.status === "weak") return sum + w * 0.5;
    return sum;
  }, 0);
  const pct = totalWeight === 0 ? 0 : Math.round((earned / totalWeight) * 100);

  const filledCount = fields.filter((f) => f.status === "filled").length;
  const weakCount = fields.filter((f) => f.status === "weak").length;
  const emptyCount = fields.filter((f) => f.status === "empty").length;

  const ringSize = 120;
  const stroke = 10;
  const radius = (ringSize - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = (pct / 100) * circumference;

  const ringColor =
    pct >= 80
      ? "stroke-emerald-500"
      : pct >= 50
      ? "stroke-amber-500"
      : "stroke-rose-500";

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Ring + summary */}
        <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-center sm:gap-6">
          <div
            className="relative grid place-items-center"
            style={{ width: ringSize, height: ringSize }}
            role="img"
            aria-label={`档案完整度 ${pct}%`}
          >
            <svg
              width={ringSize}
              height={ringSize}
              viewBox={`0 0 ${ringSize} ${ringSize}`}
              className="-rotate-90"
            >
              <circle
                cx={ringSize / 2}
                cy={ringSize / 2}
                r={radius}
                strokeWidth={stroke}
                className="stroke-muted fill-none"
              />
              <circle
                cx={ringSize / 2}
                cy={ringSize / 2}
                r={radius}
                strokeWidth={stroke}
                strokeLinecap="round"
                fill="none"
                className={cn("transition-all duration-500", ringColor)}
                style={{
                  strokeDasharray: `${dash} ${circumference - dash}`,
                }}
              />
            </svg>
            <div className="absolute inset-0 grid place-items-center">
              <div className="text-center">
                <div className="text-2xl font-semibold tabular-nums">{pct}%</div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  complete
                </div>
              </div>
            </div>
          </div>

          <div className="flex-1 space-y-2">
            <Progress value={pct} aria-label="档案完整度进度" />
            <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <CheckCircle2 className="size-3.5 text-emerald-500" />
                已填写 {filledCount}
              </span>
              <span className="inline-flex items-center gap-1">
                <AlertCircle className="size-3.5 text-amber-500" />
                建议补充 {weakCount}
              </span>
              <span className="inline-flex items-center gap-1">
                <CircleDashed className="size-3.5 text-rose-500" />
                待补充 {emptyCount}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {pct >= 80
                ? "档案很完整,可以开始匹配了!"
                : pct >= 50
                ? "再补几个关键字段,匹配会更精准。"
                : "先补几个核心信息,我们就能推荐合适的工作。"}
            </p>
          </div>
        </div>

        {/* Field list */}
        {showFieldList && (
          <ul className="divide-y rounded-lg ring-1 ring-border">
            {fields.map((f) => {
              const isMissing = f.status === "empty";
              const isWeak = f.status === "weak";
              return (
                <li key={f.key}>
                  <button
                    type="button"
                    onClick={() => onFieldClick?.(f)}
                    className={cn(
                      "flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors",
                      "hover:bg-muted/60 focus-visible:outline-none focus-visible:bg-muted/60",
                      isMissing && "bg-rose-50/60 hover:bg-rose-50",
                      isWeak && "bg-amber-50/40 hover:bg-amber-50/70",
                    )}
                    aria-label={`${f.label} - ${statusLabel(f.status)}`}
                  >
                    <FieldStatusDot status={f.status} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            "text-sm font-medium",
                            isMissing && "text-rose-700",
                          )}
                        >
                          {f.label}
                        </span>
                        <span
                          className={cn(
                            "text-[10px] uppercase tracking-wide",
                            statusColor(f.status),
                          )}
                        >
                          {statusLabel(f.status)}
                        </span>
                      </div>
                      {f.preview ? (
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                          {f.preview}
                        </p>
                      ) : f.hint ? (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {f.hint}
                        </p>
                      ) : null}
                    </div>
                    {isMissing && (
                      <span className="shrink-0 rounded-md bg-rose-100 px-2 py-0.5 text-[10px] font-medium text-rose-700">
                        一键补问
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
            {fields.length === 0 && (
              <li className="px-3 py-4 text-center text-sm text-muted-foreground">
                暂无字段
              </li>
            )}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function FieldStatusDot({ status }: { status: FieldStatus }) {
  if (status === "filled") return <CheckCircle2 className="mt-0.5 size-4 text-emerald-500" />;
  if (status === "weak") return <AlertCircle className="mt-0.5 size-4 text-amber-500" />;
  return <CircleDashed className="mt-0.5 size-4 text-rose-500" />;
}