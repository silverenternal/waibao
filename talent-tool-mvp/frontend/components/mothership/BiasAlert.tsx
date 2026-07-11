"use client";

/**
 * BiasAlert (T603)
 *
 * Top-level alert card that surfaces the demographic + cognitive biases
 * detected by the talent_brief agent. Drives from a `BiasAnalysis` shape
 * that mirrors `backend/agents/llm_extractor.detect_biases()` —
 * the agent stuffs this into `artifacts.bias_analysis`.
 *
 *   - one banner line:  fairness score + count
 *   - per row:         bias type, evidence quote, concern, suggestion
 *   - 3 severity tones (low / medium / high)
 *
 * Designed to slot directly below the textarea on the talent brief
 * submit page (left column, sticky on desktop).
 */

import * as React from "react";
import {
  AlertTriangle,
  ShieldCheck,
  Sparkles,
  ChevronDown,
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

export type BiasSeverity = "low" | "medium" | "high";

export interface DemographicBias {
  type: string;
  evidence?: string;
  severity?: BiasSeverity | string;
  concern?: string;
  suggestion?: string;
}

export interface CognitiveBias {
  type: string;
  evidence?: string;
  concern?: string;
}

export interface LogicalGap {
  gap: string;
  question_to_clarify?: string;
}

export interface BiasAnalysis {
  demographic_bias?: DemographicBias[];
  cognitive_bias?: CognitiveBias[];
  logical_gaps?: LogicalGap[];
  implicit_requirements?: Array<{
    req: string;
    inferred_from?: string;
    confidence?: number;
  }>;
  /** Overall fairness 0..1 */
  fairness_score?: number;
  overall_assessment?: string;
}

export interface BiasAlertProps {
  analysis: BiasAnalysis | null;
  loading?: boolean;
  className?: string;
}

const SEVERITY_TONE: Record<
  BiasSeverity,
  { wrap: string; badge: string; label: string }
> = {
  low: {
    wrap: "border-amber-200 bg-amber-50/40",
    badge: "border-amber-300 bg-amber-100 text-amber-800",
    label: "低",
  },
  medium: {
    wrap: "border-orange-200 bg-orange-50/40",
    badge: "border-orange-300 bg-orange-100 text-orange-800",
    label: "中等",
  },
  high: {
    wrap: "border-rose-200 bg-rose-50/40",
    badge: "border-rose-300 bg-rose-100 text-rose-800",
    label: "高",
  },
};

export function BiasAlert({ analysis, loading, className }: BiasAlertProps) {
  const demo = analysis?.demographic_bias ?? [];
  const cog = analysis?.cognitive_bias ?? [];
  const gaps = analysis?.logical_gaps ?? [];
  const score = clampScore(analysis?.fairness_score ?? 1);
  const overallText = analysis?.overall_assessment?.trim() ?? "";

  const totalIssues = demo.length + cog.length;
  const band = bandFor(score);

  if (loading) {
    return (
      <Card className={className} aria-busy>
        <CardContent className="flex items-center gap-2 py-6 text-sm text-slate-500">
          <Sparkles className="size-4 animate-pulse text-violet-500" />
          智能体检索偏见中…
        </CardContent>
      </Card>
    );
  }

  return (
    <Card
      className={cn(
        "border-2",
        band === "high" && "border-emerald-300",
        band === "mid" && "border-amber-300",
        band === "low" && "border-rose-300",
        className,
      )}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <ShieldCheck
            className={cn(
              "size-4",
              band === "high" && "text-emerald-500",
              band === "mid" && "text-amber-500",
              band === "low" && "text-rose-500",
            )}
          />
          偏见与公平性检测
          <Badge
            variant="outline"
            className={cn(
              "ml-auto text-[10px]",
              band === "high" && "border-emerald-300 bg-emerald-50 text-emerald-700",
              band === "mid" && "border-amber-300 bg-amber-50 text-amber-700",
              band === "low" && "border-rose-300 bg-rose-50 text-rose-700",
            )}
          >
            公平度 {Math.round(score * 100)}%
          </Badge>
        </CardTitle>
        {overallText && (
          <CardDescription className="whitespace-pre-wrap">
            {overallText}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {totalIssues === 0 && (
          <p className="rounded-md border border-emerald-200 bg-emerald-50/70 p-3 text-xs text-emerald-700">
            ✓ 未发现明显的人口统计学或认知偏见,描述质量良好。
          </p>
        )}

        {demo.length > 0 && (
          <BiasSection
            title="人口统计学偏见"
            count={demo.length}
          >
            <ul className="space-y-2">
              {demo.map((b, i) => (
                <BiasRow
                  key={i}
                  type={b.type}
                  evidence={b.evidence}
                  concern={b.concern}
                  suggestion={b.suggestion}
                  severity={b.severity as BiasSeverity | undefined}
                />
              ))}
            </ul>
          </BiasSection>
        )}

        {cog.length > 0 && (
          <BiasSection title="认知偏见" count={cog.length}>
            <ul className="space-y-2">
              {cog.map((b, i) => (
                <BiasRow
                  key={i}
                  type={b.type}
                  evidence={b.evidence}
                  concern={b.concern}
                />
              ))}
            </ul>
          </BiasSection>
        )}

        {gaps.length > 0 && (
          <BiasSection title="逻辑空白" count={gaps.length}>
            <ul className="space-y-1.5">
              {gaps.map((g, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-blue-200 bg-blue-50/40 p-2"
                >
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-blue-600" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-slate-700">{g.gap}</p>
                    {g.question_to_clarify && (
                      <p className="mt-0.5 text-[11px] text-blue-700">
                        建议追问 · {g.question_to_clarify}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </BiasSection>
        )}

        {(analysis?.implicit_requirements ?? []).length > 0 && (
          <details className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2 text-xs">
            <summary className="flex cursor-pointer items-center gap-2 font-medium text-slate-700">
              <ChevronDown className="size-3.5" />
              隐性需求推断 ({(analysis?.implicit_requirements ?? []).length} 项)
            </summary>
            <ul className="mt-2 space-y-1 pl-4">
              {(analysis?.implicit_requirements ?? []).map((r, i) => (
                <li key={i} className="text-slate-600">
                  <span className="font-medium">{r.req}</span>
                  {r.inferred_from && (
                    <span className="ml-1 text-[11px] text-slate-400">
                      (依据: {r.inferred_from})
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function BiasSection({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section>
      <header className="mb-1.5 flex items-center gap-2 text-xs font-medium text-slate-600">
        <span>{title}</span>
        <Badge variant="outline" className="text-[10px]">
          {count}
        </Badge>
      </header>
      {children}
    </section>
  );
}

function BiasRow({
  type,
  evidence,
  concern,
  suggestion,
  severity,
}: {
  type: string;
  evidence?: string;
  concern?: string;
  suggestion?: string;
  severity?: BiasSeverity;
}) {
  const sev = (severity as BiasSeverity | undefined) ?? "medium";
  const cfg = SEVERITY_TONE[sev] ?? SEVERITY_TONE.medium;
  return (
    <li className={cn("rounded-md border bg-white p-3", cfg.wrap)}>
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-rose-500" />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-800">{type}</span>
            <Badge variant="outline" className={cn("text-[10px]", cfg.badge)}>
              风险 {cfg.label}
            </Badge>
          </div>
          {evidence && (
            <blockquote className="border-l-2 border-slate-300 bg-slate-50 px-2 py-1 text-[11px] italic text-slate-700">
              “{evidence}”
            </blockquote>
          )}
          {concern && (
            <p className="text-[11px] text-slate-700">
              <span className="font-medium">为什么有问题:</span> {concern}
            </p>
          )}
          {suggestion && (
            <p className="text-[11px] text-emerald-700">
              <span className="font-medium">建议改为:</span> {suggestion}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clampScore(v: number) {
  if (Number.isNaN(v)) return 1;
  return Math.max(0, Math.min(1, v));
}

function bandFor(score: number): "high" | "mid" | "low" {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "mid";
  return "low";
}
