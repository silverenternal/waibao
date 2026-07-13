"use client";

/**
 * v8.1 T3601/T3603 — 主动关怀卡片
 *
 * 数据来源:
 *   /api/v8_1/outreach/reach_out  (single)
 *   /api/v8_1/proactive/run       (batch)
 *   /api/v8_1/proactive/logs      (history)
 */

import * as React from "react";
import { Bell, Calendar, Heart, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface ProactiveCardProps {
  title: string;
  body: string;
  cta?: string | null;
  ctaUrl?: string | null;
  reason?: string;
  priority?: "low" | "normal" | "high";
  onDismiss?: () => void;
  className?: string;
}

const PRIORITY_STYLES = {
  low: "bg-slate-50 border-slate-200",
  normal: "bg-blue-50 border-blue-200",
  high: "bg-rose-50 border-rose-200",
} as const;

const PRIORITY_ICON = {
  low: Heart,
  normal: Bell,
  high: Sparkles,
} as const;

export function ProactiveCard({
  title,
  body,
  cta,
  ctaUrl,
  reason,
  priority = "normal",
  onDismiss,
  className,
}: ProactiveCardProps) {
  const Icon = PRIORITY_ICON[priority] ?? Bell;
  return (
    <Card
      className={cn(
        "p-4 border",
        PRIORITY_STYLES[priority],
        className,
      )}
      role="article"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-9 h-9 rounded-full bg-white/80 flex items-center justify-center shadow-sm">
          <Icon className="w-4 h-4 text-slate-700" aria-hidden="true" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
          <p className="mt-1 text-sm text-slate-700 whitespace-pre-line">
            {body}
          </p>
          {reason ? (
            <p className="mt-2 flex items-center gap-1 text-xs text-slate-500">
              <Calendar className="w-3 h-3" aria-hidden="true" />
              触发原因: {reason}
            </p>
          ) : null}
          <div className="mt-3 flex items-center gap-2">
            {cta && ctaUrl ? (
              <Button asChild size="sm" variant="default">
                <a href={ctaUrl}>{cta}</a>
              </Button>
            ) : null}
            {onDismiss ? (
              <Button size="sm" variant="ghost" onClick={onDismiss}>
                知道了
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </Card>
  );
}

export default ProactiveCard;