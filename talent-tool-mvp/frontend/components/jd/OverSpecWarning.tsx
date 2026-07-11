"use client";

/**
 * OverSpecWarning (T604)
 *
 * Lists `over_spec_flags` returned by the job_spec agent. Each flag is
 * classified into red / amber / green by the helper in `api-jd.ts`; the
 * overall banner re-flashes the worst severity so the editor always knows
 * whether they can safely publish.
 *
 *   red   → "请立即修改" (likely compliance or fairness issue)
 *   amber → "建议复核"   (salary band / experience mismatch)
 *   green → "需求合理"   (no flags)
 *
 * Designed as a sidebar widget — sticks below the textarea on desktop,
 * stacks below on mobile.
 */

import * as React from "react";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Shield,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

import {
  classifyBatch,
  classifyOverSpec,
  TONE,
  type OverSpecSeverity,
} from "@/lib/api-jd";

export interface OverSpecWarningProps {
  flags?: string[];
  /** When true, shows a loading shimmer even when no flags yet. */
  loading?: boolean;
  className?: string;
}

const ICONS: Record<OverSpecSeverity, React.ComponentType<{ className?: string }>> = {
  red: AlertOctagon,
  amber: AlertTriangle,
  green: CheckCircle2,
};

export function OverSpecWarning({
  flags = [],
  loading,
  className,
}: OverSpecWarningProps) {
  const overall = classifyBatch(flags);
  const cfg = TONE[overall];
  const Icon = ICONS[overall];

  if (loading) {
    return (
      <Card className={cn("border-dashed", className)}>
        <CardContent className="flex items-center gap-2 py-4 text-xs text-slate-500">
          <Shield className="size-4 animate-pulse text-slate-400" />
          正在评估需求合理性…
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn(cfg.wrap, className)}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <span
            className={cn(
              "grid size-7 place-items-center rounded-full bg-white shadow-sm ring-1 ring-black/5",
              cfg.icon,
            )}
          >
            <Icon className="size-4" />
          </span>
          过度要求检测
          <Badge variant="outline" className={cn("ml-auto text-[10px]", cfg.bar, "text-white")}>
            {cfg.label}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {flags.length === 0 ? (
          <p className="rounded-md border border-emerald-200 bg-emerald-50/70 p-2 text-xs text-emerald-700">
            ✓ 未发现过度要求。当前描述在合理范围内,可以保存或发布。
          </p>
        ) : (
          <ul className="space-y-2">
            {flags.map((f, i) => {
              const sev = classifyOverSpec(f);
              const tone = TONE[sev];
              const LocalIcon = ICONS[sev];
              return (
                <li
                  key={i}
                  className={cn(
                    "flex items-start gap-2 rounded-md border bg-white p-2",
                    tone.wrap,
                  )}
                >
                  <LocalIcon className={cn("mt-0.5 size-3.5 shrink-0", tone.icon)} />
                  <p className="text-xs leading-relaxed text-slate-700">{f}</p>
                </li>
              );
            })}
          </ul>
        )}
        <p className="border-t border-slate-200/40 pt-2 text-[10px] text-slate-500">
          提示:检测基于关键词 + 历史招聘数据,可能存在误报。请用业务判断再确认。
        </p>
      </CardContent>
    </Card>
  );
}
