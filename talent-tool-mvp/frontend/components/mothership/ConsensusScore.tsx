"use client";

/**
 * ConsensusScore (T602)
 *
 * Animated progress bar showing the multi-persona consensus (0..100 %).
 * Drives from `clarification.consensus_score` (0..1). Pure presentation.
 *
 * Visual language:
 *   <40 %  → red bar + "需要协调"
 *   40-70 % → amber bar + "部分一致"
 *   >70 %  → emerald bar + "高度一致"
 */

import * as React from "react";
import {
  Handshake,
  AlertTriangle,
  CheckCircle2,
  Sparkles,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

export type ConsensusBand = "low" | "medium" | "high";

export interface ConsensusScoreProps {
  /** 0..1 — the same value the agent stores as `consensus_score`. */
  score?: number | null;
  /** Optional cap subtitle. */
  caption?: string;
  /** Show the breakdown chip set. */
  showBreakdown?: boolean;
  className?: string;
}

const BAND_CONFIG: Record<
  ConsensusBand,
  {
    wrap: string;
    bar: string;
    text: string;
    icon: React.ComponentType<{ className?: string }>;
    label: string;
    description: string;
  }
> = {
  low: {
    wrap: "border-rose-200 bg-rose-50/40",
    bar: "bg-rose-500",
    text: "text-rose-700",
    icon: AlertTriangle,
    label: "需要协调",
    description: "多方意见分歧较大,建议安排对齐会议",
  },
  medium: {
    wrap: "border-amber-200 bg-amber-50/40",
    bar: "bg-amber-500",
    text: "text-amber-700",
    icon: Handshake,
    label: "部分一致",
    description: "核心诉求接近,可在分歧点上做额外讨论",
  },
  high: {
    wrap: "border-emerald-200 bg-emerald-50/40",
    bar: "bg-emerald-500",
    text: "text-emerald-700",
    icon: CheckCircle2,
    label: "高度一致",
    description: "四类角色已基本对齐,可进入画像生成阶段",
  },
};

export function ConsensusScore({
  score,
  caption,
  showBreakdown = true,
  className,
}: ConsensusScoreProps) {
  const valuePct = clampPct((score ?? 0) * 100);
  const band = bandFor(valuePct);
  const cfg = BAND_CONFIG[band];
  const Icon = cfg.icon;
  const segments = [25, 50, 75, 100];

  return (
    <Card className={cn(cfg.wrap, className)}>
      <CardContent className="space-y-3 py-4">
        <header className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex size-7 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-black/5",
                cfg.text,
              )}
            >
              <Icon className="size-4" />
            </span>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                多方共识度
              </h3>
              <p className="text-[11px] text-slate-500">
                {cfg.description}
              </p>
            </div>
          </div>
          <div className="text-right">
            <div className={cn("text-2xl font-bold tabular-nums", cfg.text)}>
              {Math.round(valuePct)}
              <span className="ml-0.5 text-sm font-medium">%</span>
            </div>
            <span className={cn("text-[10px] font-medium", cfg.text)}>
              {cfg.label}
            </span>
          </div>
        </header>

        {/* Track */}
        <div
          role="progressbar"
          aria-valuenow={Math.round(valuePct)}
          aria-valuemin={0}
          aria-valuemax={100}
          className="relative h-3 overflow-hidden rounded-full bg-slate-200/70 shadow-inner"
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-700 ease-out",
              cfg.bar,
            )}
            style={{ width: `${valuePct}%` }}
          />
          {/* Tick markers */}
          {segments.map((s) => (
            <span
              key={s}
              aria-hidden
              className="absolute inset-y-0 w-px bg-white/70"
              style={{ left: `${s}%` }}
            />
          ))}
        </div>

        {showBreakdown && (
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
            <span className="inline-flex items-center gap-1">
              <Sparkles className="size-3 text-violet-500" />
              老板 · HR · 部门 · 行政
            </span>
            {caption && (
              <span className="ml-auto rounded-full bg-white px-2 py-0.5 text-slate-500 shadow-sm ring-1 ring-slate-200">
                {caption}
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clampPct(v: number): number {
  if (Number.isNaN(v)) return 0;
  return Math.max(0, Math.min(100, v));
}

function bandFor(pct: number): ConsensusBand {
  if (pct < 40) return "low";
  if (pct < 70) return "medium";
  return "high";
}
